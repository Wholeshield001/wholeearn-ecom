from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from functools import wraps
import sys
from django.http import HttpResponse
from .forms import (AdminLoginForm,
                    ForgotPasswordForm, 
                    VerifyOTPForm, 
                    ResetPasswordForm, 
                    ProductForm, 
                    ProductImageForm, 
                    CategoryForm,
                    BlogPostForm,
                    BlogCategoryForm,
                    AdminInviteForm,
                    AdminProfileForm,
                    AdminPasswordChangeForm,
                    RewardPointConfigForm,
                    PaymentProviderConfigForm)
from users.models import User, KYCSubmission, KYCSubmissionAuditLog
from django.core.mail import send_mail
from django.conf import settings
from django.http import JsonResponse
from .models import Product, Category, ProductImage, BlogPost, BlogCategory, DailyWebsiteVisit
from django.db.models import Count, Sum, Q
from django.db.models.functions import TruncMonth
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import secrets
from django.utils import timezone
from ecom.models import RewardPointConfig, PaymentProviderConfig, Order, WalletWithdrawalRequest
from ecom.services.wallets import WalletOperationError
from ecom.tasks import process_withdrawal_request_task
from users.emails import send_kyc_approved_email, send_kyc_rejected_email
from users.tasks import send_kyc_status_update_email_task


# Custom decorator to require admin role
def admin_required(view_func):
    """Decorator to ensure user is authenticated and has admin role"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'You must be logged in to access this page.')
            return redirect('admin_login')
        
        if request.user.role != User.ADMINISTRATOR:
            messages.error(request, 'You do not have permission to access this page. Admin access required.')
            return redirect('home')
        
        return view_func(request, *args, **kwargs)
    return wrapper





def admin_login(request):
    # Redirect if already logged in as admin
    if request.user.is_authenticated and request.user.role == User.ADMINISTRATOR:
        return redirect('admin_dashboard')
    
    if request.method == 'POST':
        form = AdminLoginForm(request=request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            
            # Handle remember me
            if not form.cleaned_data.get('remember_me'):
                request.session.set_expiry(0)
            
            messages.success(request, f'Welcome back, {user.first_name or user.email}!')
            
            # Redirect to next or dashboard
            next_url = request.GET.get('next', 'admin_dashboard')
            return redirect(next_url)
    else:
        form = AdminLoginForm()
    
    return render(request, 'admin_dashboard/admin_login.html', {'form': form})


def admin_logout(request):
    logout(request)
    messages.info(request, 'You have been logged out successfully.')
    return redirect('admin_login')


@admin_required
def admin_dashboard(request):
    """Admin dashboard with real data statistics"""
    from ecom.models import Order
    from django.db.models import Sum, Count, Q
    from datetime import datetime, timedelta
    
    # User is already verified as admin by @admin_required decorator
    
    # Get statistics
    total_orders = Order.objects.count()
    pending_orders = Order.objects.filter(status='pending').count()
    total_users = User.objects.count()
    total_revenue = Order.objects.filter(
        payment_status='completed'
    ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
    total_points_issued = User.objects.aggregate(total=Sum('reward_points'))['total'] or 0
    successful_referral_orders = Order.objects.filter(
        payment_status='completed',
        referrer__isnull=False,
    ).count()
    today_local = timezone.localdate()
    today_visit_stat = DailyWebsiteVisit.objects.filter(date=today_local).first()
    today_visits = today_visit_stat.total_visits if today_visit_stat else 0
    unique_visitors_today = today_visit_stat.unique_visitors if today_visit_stat else 0
    last_7_days_visits = DailyWebsiteVisit.objects.filter(
        date__gte=today_local - timedelta(days=6),
        date__lte=today_local,
    ).aggregate(total=Sum('total_visits'))['total'] or 0
    top_referrers = User.objects.annotate(
        referral_orders_count=Count('referred_orders', filter=Q(referred_orders__payment_status='completed')),
    ).filter(referral_orders_count__gt=0).order_by('-referral_orders_count', '-reward_points')[:5]
    
    # Get top selling products (based on order items)
    from ecom.models import OrderItem
    top_products = OrderItem.objects.values(
        'product__id',
        'product__name',
        'product__sku',
        'product__created_at'
    ).annotate(
        total_sold=Sum('quantity'),
        product_stock=Count('product__stock')
    ).order_by('-total_sold')[:5]
    
    # Calculate stock left for top products
    top_products_data = []
    for item in top_products:
        if item['product__id']:
            product = Product.objects.filter(id=item['product__id']).first()
            if product:
                top_products_data.append({
                    'product': product,
                    'total_sold': item['total_sold'],
                    'stock_left': product.stock or 0,
                })
    
    # Get monthly sales data for current year
    current_year = datetime.now().year
    monthly_sales_2025 = [0] * 12
    monthly_sales_2024 = [0] * 12
    
    # 2025 data
    sales_2025 = Order.objects.filter(
        created_at__year=current_year,
        payment_status='completed'
    ).annotate(
        month=TruncMonth('created_at')
    ).values('month').annotate(
        total=Sum('total_amount')
    ).order_by('month')
    
    for sale in sales_2025:
        month_index = sale['month'].month - 1
        monthly_sales_2025[month_index] = float(sale['total'] or 0)
    
    # 2024 data
    sales_2024 = Order.objects.filter(
        created_at__year=current_year - 1,
        payment_status='completed'
    ).annotate(
        month=TruncMonth('created_at')
    ).values('month').annotate(
        total=Sum('total_amount')
    ).order_by('month')
    
    for sale in sales_2024:
        month_index = sale['month'].month - 1
        monthly_sales_2024[month_index] = float(sale['total'] or 0)
    
    # Get last 7 days revenue
    today = datetime.now().date()
    last_7_days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    daily_revenue = []
    
    for day in last_7_days:
        revenue = Order.objects.filter(
            created_at__date=day,
            payment_status='completed'
        ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
        daily_revenue.append(float(revenue))
    
    # Get recent notifications (orders and tickets combined)
    from users.models import Ticket
    recent_orders = Order.objects.select_related('user').prefetch_related('items').order_by('-created_at')[:3]
    recent_tickets = Ticket.objects.select_related('user').filter(status__in=['open', 'in_progress']).order_by('-created_at')[:3]
    
    notifications = []
    
    # Add order notifications
    for order in recent_orders:
        first_item = order.items.first()
        if first_item:
            notifications.append({
                'type': 'order',
                'user': order.user,
                'product_name': first_item.product_name,
                'created_at': order.created_at,
                'order_id': order.id,
            })
    
    # Add ticket notifications
    for ticket in recent_tickets:
        notifications.append({
            'type': 'ticket',
            'user': ticket.user,
            'ticket_id': ticket.id,
            'subject': ticket.title,
            'priority': ticket.priority,
            'created_at': ticket.created_at,
        })
    
    # Sort all notifications by created_at
    notifications.sort(key=lambda x: x['created_at'], reverse=True)
    notifications = notifications[:5]  # Keep only top 5

    # ── Extra chart data ──────────────────────────────────────────────────────

    # Actual date labels for the last-7-days revenue chart
    daily_labels = [d.strftime('%b %d') for d in last_7_days]

    # Monthly order *counts* for current year (overlay line on Sales Details chart)
    monthly_orders_year = [0] * 12
    for o in Order.objects.filter(created_at__year=current_year).annotate(
        month=TruncMonth('created_at')
    ).values('month').annotate(count=Count('id')).order_by('month'):
        monthly_orders_year[o['month'].month - 1] = o['count']

    # Orders by status (doughnut chart)
    status_display_map = dict(Order.STATUS_CHOICES) if hasattr(Order, 'STATUS_CHOICES') else {}
    status_qs = Order.objects.values('status').annotate(count=Count('id')).order_by('-count')
    orders_by_status_labels = [
        status_display_map.get(sc['status'], sc['status'].replace('_', ' ').title())
        for sc in status_qs
    ]
    orders_by_status_data = [sc['count'] for sc in status_qs]

    # Revenue by user role (horizontal bar chart)
    role_display_map = dict(User.ROLE_CHOICES)
    role_rev_qs = (
        Order.objects.filter(payment_status='completed')
        .values('user__role')
        .annotate(total=Sum('total_amount'))
        .order_by('-total')
    )
    revenue_by_role_labels = [
        role_display_map.get(rr['user__role'] or '', rr['user__role'] or 'Unknown')
        for rr in role_rev_qs
    ]
    revenue_by_role_data = [float(rr['total'] or 0) for rr in role_rev_qs]

    # Last 30 days revenue + labels (for toggle on revenue trend chart)
    last_30_days_list = [today - timedelta(days=i) for i in range(29, -1, -1)]
    last_30_labels = [d.strftime('%b %d') for d in last_30_days_list]
    last_30_revenue = []
    for day in last_30_days_list:
        rev = Order.objects.filter(
            created_at__date=day, payment_status='completed'
        ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
        last_30_revenue.append(float(rev))

    # Month-over-month revenue change for the Sales Details subtitle
    import calendar
    this_month = datetime.now().month
    prev_month = this_month - 1 if this_month > 1 else 12
    prev_year = current_year if this_month > 1 else current_year - 1
    rev_this_month = Order.objects.filter(
        created_at__year=current_year, created_at__month=this_month, payment_status='completed'
    ).aggregate(t=Sum('total_amount'))['t'] or Decimal('0')
    rev_prev_month = Order.objects.filter(
        created_at__year=prev_year, created_at__month=prev_month, payment_status='completed'
    ).aggregate(t=Sum('total_amount'))['t'] or Decimal('0')
    if rev_prev_month > 0:
        mom_change = round(float((rev_this_month - rev_prev_month) / rev_prev_month * 100), 1)
    else:
        mom_change = None  # no previous month data

    # Top 5 products — bar chart (units sold)
    top_product_labels = [item['product'].name for item in top_products_data]
    top_product_sold   = [item['total_sold'] for item in top_products_data]
    top_product_stock  = [item['stock_left'] for item in top_products_data]

    # Orders by payment status — pie chart
    pay_status_qs = (
        Order.objects.values('payment_status')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    pay_status_label_map = {'pending': 'Pending', 'completed': 'Completed', 'failed': 'Failed', 'refunded': 'Refunded'}
    pay_status_labels = [pay_status_label_map.get(r['payment_status'], r['payment_status'].title()) for r in pay_status_qs]
    pay_status_data   = [r['count'] for r in pay_status_qs]

    context = {
        'user': request.user,
        'total_orders': total_orders,
        'pending_orders': pending_orders,
        'total_users': total_users,
        'total_revenue': total_revenue,
        'total_points_issued': total_points_issued,
        'successful_referral_orders': successful_referral_orders,
        'today_visits': today_visits,
        'unique_visitors_today': unique_visitors_today,
        'last_7_days_visits': last_7_days_visits,
        'top_referrers': top_referrers,
        'top_products': top_products_data,
        'monthly_sales_2025': json.dumps(monthly_sales_2025),
        'monthly_sales_2024': json.dumps(monthly_sales_2024),
        'monthly_orders_year': json.dumps(monthly_orders_year),
        'daily_revenue': json.dumps(daily_revenue),
        'daily_labels': json.dumps(daily_labels),
        'last_30_days_revenue': json.dumps(last_30_revenue),
        'last_30_days_labels': json.dumps(last_30_labels),
        'orders_by_status_labels': json.dumps(orders_by_status_labels),
        'orders_by_status_data': json.dumps(orders_by_status_data),
        'revenue_by_role_labels': json.dumps(revenue_by_role_labels),
        'revenue_by_role_data': json.dumps(revenue_by_role_data),
        'top_product_labels': json.dumps(top_product_labels),
        'top_product_sold': json.dumps(top_product_sold),
        'top_product_stock': json.dumps(top_product_stock),
        'pay_status_labels': json.dumps(pay_status_labels),
        'pay_status_data': json.dumps(pay_status_data),
        'mom_change': mom_change,
        'current_year': current_year,
        'notifications': notifications,
    }
    return render(request, 'admin_dashboard/dashboard.html', context)


@admin_required
def admin_admins(request):
    """Manage administrator accounts and invite new admins"""
    if request.user.role != User.ADMINISTRATOR or not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('admin_login')

    admins = User.objects.filter(role=User.ADMINISTRATOR, is_staff=True).order_by('-date_joined')
    if request.method == 'POST':
        form = AdminInviteForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            temp_password = secrets.token_urlsafe(12)
            user = User.objects.create_user(
                email=data['email'],
                password=temp_password,
                first_name=data.get('first_name') or '',
                last_name=data.get('last_name') or '',
                phone=data.get('phone') or '',
                role=User.ADMINISTRATOR,
                is_staff=True,
                is_active=True,
            )
            # Mark as verified since created by an existing admin
            user.email_verified = True
            user.save(update_fields=['email_verified'])

            login_url = request.build_absolute_uri(reverse('admin_login'))
            send_mail(
                subject='Your WholeShield admin access',
                message=(
                    f"Hello {user.get_full_name() or 'Admin'},\n\n"
                    f"An administrator created an account for you.\n\n"
                    f"Login email: {user.email}\n"
                    f"Temporary password: {temp_password}\n\n"
                    f"Login here: {login_url}\n"
                    "Please sign in and reset your password immediately."
                ),
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
                recipient_list=[user.email],
                fail_silently=True,
            )
            messages.success(request, f"Admin invite sent to {user.email}.")
            return redirect('admin_admins')
    else:
        form = AdminInviteForm()

    context = {
        'admins': admins,
        'form': form,
    }
    return render(request, 'admin_dashboard/admins.html', context)


@admin_required
def admin_profile(request):
    """Admin profile page with edit and password change"""
    if request.user.role != User.ADMINISTRATOR or not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('admin_login')

    profile_form = AdminProfileForm(instance=request.user)
    password_form = AdminPasswordChangeForm(user=request.user)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'update_profile':
            profile_form = AdminProfileForm(request.POST, instance=request.user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, 'Profile updated successfully.')
                return redirect('admin_profile')
        elif action == 'change_password':
            password_form = AdminPasswordChangeForm(user=request.user, data=request.POST)
            if password_form.is_valid():
                request.user.set_password(password_form.cleaned_data['new_password'])
                request.user.save()
                messages.success(request, 'Password changed successfully. Please log in again.')
                return redirect('admin_login')

    context = {
        'profile_form': profile_form,
        'password_form': password_form,
    }
    return render(request, 'admin_dashboard/admin_profile.html', context)


@admin_required
def reward_settings(request):
    """Admin page to configure points awarded for purchases and referrals."""
    config = RewardPointConfig.get_solo()

    if request.method == 'POST':
        form = RewardPointConfigForm(request.POST, instance=config)
        if form.is_valid():
            reward_config = form.save(commit=False)
            reward_config.updated_by = request.user
            reward_config.save()
            messages.success(request, 'Reward settings updated successfully.')
            return redirect('admin_reward_settings')
    else:
        form = RewardPointConfigForm(instance=config)

    context = {
        'page_title': 'Reward Settings',
        'form': form,
        'config': config,
        'users_with_points': User.objects.filter(reward_points__gt=0).count(),
        'total_points_issued': User.objects.aggregate(total=Sum('reward_points'))['total'] or 0,
        'total_referral_orders': Order.objects.filter(payment_status='completed', referrer__isnull=False).count(),
    }
    return render(request, 'admin_dashboard/reward_settings.html', context)


@admin_required
def payment_settings(request):
    """Admin page to switch active payment provider."""
    config = PaymentProviderConfig.get_solo()

    if request.method == 'POST':
        form = PaymentProviderConfigForm(request.POST, instance=config)
        if form.is_valid():
            provider_config = form.save(commit=False)
            provider_config.updated_by = request.user
            provider_config.save()
            messages.success(request, 'Payment provider updated successfully.')
            return redirect('admin_payment_settings')
    else:
        form = PaymentProviderConfigForm(instance=config)

    context = {
        'page_title': 'Payment Settings',
        'form': form,
        'config': config,
    }
    return render(request, 'admin_dashboard/payment_settings.html', context)


def forgot_password(request):
    if request.method == 'POST':
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            user = User.objects.get(email=email, role=User.ADMINISTRATOR, is_staff=True)
            
            # Generate OTP
            otp = user.generate_reset_otp()
            
            # Log OTP to terminal
            print("\n" + "="*50, flush=True)
            print(f"PASSWORD RESET OTP FOR {email}", flush=True)
            print(f"OTP: {otp}", flush=True)
            print(f"This code will expire in 10 minutes.", flush=True)
            print("="*50 + "\n", flush=True)
            sys.stdout.flush()
            
            messages.success(request, f'OTP has been generated. Check your terminal.')
            # Store email in session for next step
            request.session['reset_email'] = email
            return redirect('verify_otp')
    else:
        form = ForgotPasswordForm()
    
    return render(request, 'admin_dashboard/forgot_password.html', {'form': form})


def verify_otp(request):
    email = request.session.get('reset_email')
    if not email:
        messages.error(request, 'Please start the password reset process again.')
        return redirect('forgot_password')
    
    if request.method == 'POST':
        form = VerifyOTPForm(request.POST)
        if form.is_valid():
            otp = form.get_otp()
            print(f"\n[DEBUG] Attempting to verify OTP: {otp} for {email}", flush=True)
            try:
                user = User.objects.get(email=email)
                if user.verify_reset_otp(otp):
                    # Store token in session
                    request.session['reset_token'] = user.reset_token
                    print(f"[DEBUG] OTP verified successfully for {email}", flush=True)
                    messages.success(request, 'OTP verified successfully!')
                    return redirect('reset_password')
                else:
                    print(f"[DEBUG] OTP verification failed for {email}", flush=True)
                    messages.error(request, 'Invalid or expired OTP. Please try again.')
            except User.DoesNotExist:
                print(f"[DEBUG] User not found: {email}", flush=True)
                messages.error(request, 'User not found.')
                return redirect('forgot_password')
    else:
        form = VerifyOTPForm()
    
    context = {
        'form': form,
        'email': email
    }
    return render(request, 'admin_dashboard/verify_otp.html', context)


def resend_otp(request):
    email = request.session.get('reset_email')
    if not email:
        messages.error(request, 'Please start the password reset process again.')
        return redirect('forgot_password')
    
    try:
        user = User.objects.get(email=email, role=User.ADMINISTRATOR, is_staff=True)
        otp = user.generate_reset_otp()
        
        # Log OTP to terminal
        print("\n" + "="*50, flush=True)
        print(f"RESENT PASSWORD RESET OTP FOR {email}", flush=True)
        print(f"OTP: {otp}", flush=True)
        print(f"This code will expire in 10 minutes.", flush=True)
        print("="*50 + "\n", flush=True)
        sys.stdout.flush()
        
        messages.success(request, 'OTP has been resent. Check your terminal.')
    except Exception as e:
        print(f"[ERROR] Failed to resend OTP: {str(e)}", flush=True)
        messages.error(request, 'Failed to resend OTP.')
    
    return redirect('verify_otp')


def reset_password(request):
    reset_token = request.session.get('reset_token')
    email = request.session.get('reset_email')
    
    if not reset_token or not email:
        messages.error(request, 'Invalid password reset session.')
        return redirect('forgot_password')
    
    try:
        user = User.objects.get(email=email, reset_token=reset_token)
    except User.DoesNotExist:
        messages.error(request, 'Invalid password reset session.')
        return redirect('forgot_password')
    
    if request.method == 'POST':
        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            new_password = form.cleaned_data['new_password']
            user.set_password(new_password)
            user.clear_reset_data()
            
            # Clear session data
            del request.session['reset_token']
            del request.session['reset_email']
            
            print(f"[SUCCESS] Password successfully reset for {email}", flush=True)
            
            # Redirect to success page instead of login
            return redirect('password_reset_success')
    else:
        form = ResetPasswordForm()
    
    return render(request, 'admin_dashboard/reset_password.html', {'form': form})


def password_reset_success(request):
    return render(request, 'admin_dashboard/password_reset_success.html')


@admin_required
def notifications_page(request):
    """Display all notifications (orders and tickets)"""
    from ecom.models import Order
    from users.models import Ticket
    from django.db.models import Q
    
    # Get filter type
    filter_type = request.GET.get('type', 'all')
    
    # Get dismissed notifications from session
    dismissed_notifications = request.session.get('dismissed_notifications', [])
    
    # Get recent orders and tickets
    recent_orders = Order.objects.select_related('user').prefetch_related('items').order_by('-created_at')
    recent_tickets = Ticket.objects.select_related('user').order_by('-created_at')
    
    notifications = []
    
    # Add order notifications
    if filter_type in ['all', 'orders']:
        for order in recent_orders[:20]:
            notification_key = f"order-{str(order.id)}"
            if notification_key not in dismissed_notifications:
                first_item = order.items.first()
                if first_item:
                    notifications.append({
                        'type': 'order',
                        'user': order.user,
                        'product_name': first_item.product_name,
                        'created_at': order.created_at,
                        'order_id': order.id,
                        'status': order.status,
                        'total_amount': order.total_amount,
                    })
    
    # Add ticket notifications
    if filter_type in ['all', 'tickets']:
        for ticket in recent_tickets[:20]:
            notification_key = f"ticket-{str(ticket.id)}"
            if notification_key not in dismissed_notifications:
                notifications.append({
                    'type': 'ticket',
                    'user': ticket.user,
                    'ticket_id': ticket.id,
                    'subject': ticket.title,
                    'priority': ticket.priority,
                    'status': ticket.status,
                    'created_at': ticket.created_at,
                })
    
    # Sort all notifications by created_at
    notifications.sort(key=lambda x: x['created_at'], reverse=True)
    
    # Get counts
    total_notifications = len(notifications)
    orders_count = len([n for n in notifications if n['type'] == 'order'])
    tickets_count = len([n for n in notifications if n['type'] == 'ticket'])
    
    context = {
        'notifications': notifications,
        'total_notifications': total_notifications,
        'orders_count': orders_count,
        'tickets_count': tickets_count,
        'filter_type': filter_type,
    }
    return render(request, 'admin_dashboard/notifications.html', context)

@admin_required
def wholesalers_page(request):
    """Wholesalers management page"""
    from ecom.models import Order
    from django.db.models import Sum, Count, Q
    
    # Get filter and search parameters
    status_filter = request.GET.get('status', 'all')
    search_query = request.GET.get('q', '').strip()
    
    # Get all wholesalers
    wholesalers = User.objects.filter(role=User.WHOLESALER).annotate(
        total_orders=Count('orders'),
        total_spent=Sum('orders__total_amount')
    ).order_by('-date_joined')
    
    # Apply status filter
    if status_filter == 'active':
        wholesalers = wholesalers.filter(is_active=True)
    elif status_filter == 'inactive':
        wholesalers = wholesalers.filter(is_active=False)
    
    # Apply search filter
    if search_query:
        wholesalers = wholesalers.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(phone_number__icontains=search_query) |
            Q(company_name__icontains=search_query)
        )
    
    # Calculate statistics
    total_wholesalers = User.objects.filter(role=User.WHOLESALER).count()
    inactive_wholesalers = User.objects.filter(role=User.WHOLESALER, is_active=False).count()
    active_wholesalers = User.objects.filter(role=User.WHOLESALER, is_active=True).count()
    
    # Get total products distributed (sum of all order items quantities for wholesalers)
    from ecom.models import OrderItem
    products_distributed = OrderItem.objects.filter(
        order__user__role=User.WHOLESALER
    ).aggregate(total=Sum('quantity'))['total'] or 0
    
    context = {
        'page_title': 'Wholesalers',
        'wholesalers': wholesalers,
        'total_wholesalers': total_wholesalers,
        'inactive_wholesalers': inactive_wholesalers,
        'active_wholesalers': active_wholesalers,
        'products_distributed': products_distributed,
        'status_filter': status_filter,
        'search_query': search_query,
    }
    return render(request, 'admin_dashboard/wholesalers.html', context)


@admin_required
def export_wholesalers_csv(request):
    """Export wholesalers list to CSV respecting status filter"""
    import csv
    from django.db.models import Sum, Count

    status_filter = request.GET.get('status', 'all')
    qs = User.objects.filter(role=User.WHOLESALER).annotate(
        total_orders=Count('orders'),
        total_spent=Sum('orders__total_amount')
    ).order_by('-date_joined')
    if status_filter == 'active':
        qs = qs.filter(is_active=True)
    elif status_filter == 'inactive':
        qs = qs.filter(is_active=False)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="wholesalers.csv"'
    writer = csv.writer(response)
    writer.writerow(['ID', 'First Name', 'Last Name', 'Email', 'Phone', 'Role', 'Active', 'Joined', 'Total Orders', 'Total Spent', 'Unique Code', 'Referral Code', 'Reward Points'])
    for u in qs:
        writer.writerow([
            str(u.id), u.first_name, u.last_name, u.email, u.phone or '', 'wholesaler',
            'yes' if u.is_active else 'no', u.date_joined.strftime('%Y-%m-%d %H:%M'),
            int(u.total_orders or 0), float(u.total_spent or 0),
            u.unique_code or '', u.referral_code or '', u.reward_points,
        ])
    return response


@admin_required
def retailers_page(request):
    """Retailers management page"""
    from ecom.models import Order
    from django.db.models import Sum, Count, Q
    
    # Get filter and search parameters
    status_filter = request.GET.get('status', 'all')
    search_query = request.GET.get('q', '').strip()
    
    # Get all retailers
    retailers = User.objects.filter(role=User.RETAILER).annotate(
        total_orders=Count('orders'),
        total_spent=Sum('orders__total_amount')
    ).order_by('-date_joined')
    
    # Apply status filter
    if status_filter == 'active':
        retailers = retailers.filter(is_active=True)
    elif status_filter == 'inactive':
        retailers = retailers.filter(is_active=False)
    
    # Apply search filter
    if search_query:
        retailers = retailers.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(phone_number__icontains=search_query) |
            Q(company_name__icontains=search_query)
        )
    
    # Calculate statistics
    total_retailers = User.objects.filter(role=User.RETAILER).count()
    inactive_retailers = User.objects.filter(role=User.RETAILER, is_active=False).count()
    active_retailers = User.objects.filter(role=User.RETAILER, is_active=True).count()
    
    # Get total products distributed (sum of all order items quantities for retailers)
    from ecom.models import OrderItem
    products_distributed = OrderItem.objects.filter(
        order__user__role=User.RETAILER
    ).aggregate(total=Sum('quantity'))['total'] or 0
    
    context = {
        'page_title': 'Retailers',
        'retailers': retailers,
        'total_retailers': total_retailers,
        'inactive_retailers': inactive_retailers,
        'active_retailers': active_retailers,
        'products_distributed': products_distributed,
        'status_filter': status_filter,
        'search_query': search_query,
    }
    return render(request, 'admin_dashboard/retailers.html', context)


@admin_required
def export_retailers_csv(request):
    """Export retailers list to CSV respecting status filter"""
    import csv
    from django.db.models import Sum, Count

    status_filter = request.GET.get('status', 'all')
    qs = User.objects.filter(role=User.RETAILER).annotate(
        total_orders=Count('orders'),
        total_spent=Sum('orders__total_amount')
    ).order_by('-date_joined')
    if status_filter == 'active':
        qs = qs.filter(is_active=True)
    elif status_filter == 'inactive':
        qs = qs.filter(is_active=False)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="retailers.csv"'
    writer = csv.writer(response)
    writer.writerow(['ID', 'First Name', 'Last Name', 'Email', 'Phone', 'Role', 'Active', 'Joined', 'Total Orders', 'Total Spent', 'Unique Code', 'Referral Code', 'Reward Points'])
    for u in qs:
        writer.writerow([
            str(u.id), u.first_name, u.last_name, u.email, u.phone or '', 'retailer',
            'yes' if u.is_active else 'no', u.date_joined.strftime('%Y-%m-%d %H:%M'),
            int(u.total_orders or 0), float(u.total_spent or 0),
            u.unique_code or '', u.referral_code or '', u.reward_points,
        ])
    return response


@admin_required
def hospitals_page(request):
    """Hospitals management page"""
    from ecom.models import Order
    from django.db.models import Sum, Count, Q
    
    # Get filter and search parameters
    status_filter = request.GET.get('status', 'all')
    search_query = request.GET.get('q', '').strip()
    
    # Get all hospitals
    hospitals = User.objects.filter(role=User.HOSPITAL).annotate(
        total_orders=Count('orders'),
        total_spent=Sum('orders__total_amount')
    ).order_by('-date_joined')
    
    # Apply status filter
    if status_filter == 'active':
        hospitals = hospitals.filter(is_active=True)
    elif status_filter == 'inactive':
        hospitals = hospitals.filter(is_active=False)
    
    # Apply search filter
    if search_query:
        hospitals = hospitals.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(phone_number__icontains=search_query) |
            Q(company_name__icontains=search_query)
        )
    
    # Calculate statistics
    total_hospitals = User.objects.filter(role=User.HOSPITAL).count()
    inactive_hospitals = User.objects.filter(role=User.HOSPITAL, is_active=False).count()
    active_hospitals = User.objects.filter(role=User.HOSPITAL, is_active=True).count()
    
    # Get total products ordered (sum of all order items quantities for hospitals)
    from ecom.models import OrderItem
    total_products_ordered = OrderItem.objects.filter(
        order__user__role=User.HOSPITAL
    ).aggregate(total=Sum('quantity'))['total'] or 0
    
    context = {
        'page_title': 'Hospitals',
        'hospitals': hospitals,
        'total_hospitals': total_hospitals,
        'inactive_hospitals': inactive_hospitals,
        'active_hospitals': active_hospitals,
        'total_products_ordered': total_products_ordered,
        'status_filter': status_filter,
        'search_query': search_query,
    }
    return render(request, 'admin_dashboard/hospitals.html', context)


@admin_required
def export_hospitals_csv(request):
    """Export hospitals list to CSV respecting status filter"""
    import csv
    from django.db.models import Sum, Count

    status_filter = request.GET.get('status', 'all')
    qs = User.objects.filter(role=User.HOSPITAL).annotate(
        total_orders=Count('orders'),
        total_spent=Sum('orders__total_amount')
    ).order_by('-date_joined')
    if status_filter == 'active':
        qs = qs.filter(is_active=True)
    elif status_filter == 'inactive':
        qs = qs.filter(is_active=False)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="hospitals.csv"'
    writer = csv.writer(response)
    writer.writerow(['ID', 'First Name', 'Last Name', 'Email', 'Phone', 'Role', 'Active', 'Joined', 'Total Orders', 'Total Spent', 'Unique Code', 'Referral Code', 'Reward Points'])
    for u in qs:
        writer.writerow([
            str(u.id), u.first_name, u.last_name, u.email, u.phone or '', 'hospital',
            'yes' if u.is_active else 'no', u.date_joined.strftime('%Y-%m-%d %H:%M'),
            int(u.total_orders or 0), float(u.total_spent or 0),
            u.unique_code or '', u.referral_code or '', u.reward_points,
        ])
    return response


@admin_required
def pharmacy_page(request):
    """Pharmacies management page"""
    from ecom.models import Order
    from django.db.models import Sum, Count, Q
    
    # Get filter and search parameters
    status_filter = request.GET.get('status', 'all')
    search_query = request.GET.get('q', '').strip()
    
    # Get all pharmacies
    pharmacies = User.objects.filter(role=User.PHARMACY).annotate(
        total_orders=Count('orders'),
        total_spent=Sum('orders__total_amount')
    ).order_by('-date_joined')
    
    # Apply status filter
    if status_filter == 'active':
        pharmacies = pharmacies.filter(is_active=True)
    elif status_filter == 'inactive':
        pharmacies = pharmacies.filter(is_active=False)
    
    # Apply search filter
    if search_query:
        pharmacies = pharmacies.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(phone_number__icontains=search_query) |
            Q(company_name__icontains=search_query)
        )
    
    # Calculate statistics
    total_pharmacies = User.objects.filter(role=User.PHARMACY).count()
    inactive_pharmacies = User.objects.filter(role=User.PHARMACY, is_active=False).count()
    active_pharmacies = User.objects.filter(role=User.PHARMACY, is_active=True).count()
    
    # Get total products ordered (sum of all order items quantities for pharmacies)
    from ecom.models import OrderItem
    total_products_ordered = OrderItem.objects.filter(
        order__user__role=User.PHARMACY
    ).aggregate(total=Sum('quantity'))['total'] or 0
    
    context = {
        'page_title': 'Pharmacies',
        'pharmacies': pharmacies,
        'total_pharmacies': total_pharmacies,
        'inactive_pharmacies': inactive_pharmacies,
        'active_pharmacies': active_pharmacies,
        'total_products_ordered': total_products_ordered,
        'status_filter': status_filter,
        'search_query': search_query,
    }
    return render(request, 'admin_dashboard/pharmacies.html', context)


@admin_required
def export_pharmacies_csv(request):
    """Export pharmacies list to CSV respecting status filter"""
    import csv
    from django.db.models import Sum, Count

    status_filter = request.GET.get('status', 'all')
    qs = User.objects.filter(role=User.PHARMACY).annotate(
        total_orders=Count('orders'),
        total_spent=Sum('orders__total_amount')
    ).order_by('-date_joined')
    if status_filter == 'active':
        qs = qs.filter(is_active=True)
    elif status_filter == 'inactive':
        qs = qs.filter(is_active=False)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="pharmacies.csv"'
    writer = csv.writer(response)
    writer.writerow(['ID', 'First Name', 'Last Name', 'Email', 'Phone', 'Role', 'Active', 'Joined', 'Total Orders', 'Total Spent', 'Unique Code', 'Referral Code', 'Reward Points'])
    for u in qs:
        writer.writerow([
            str(u.id), u.first_name, u.last_name, u.email, u.phone or '', 'pharmacy',
            'yes' if u.is_active else 'no', u.date_joined.strftime('%Y-%m-%d %H:%M'),
            int(u.total_orders or 0), float(u.total_spent or 0),
            u.unique_code or '', u.referral_code or '', u.reward_points,
        ])
    return response





# ...existing code...

@admin_required
def products_page(request):
    from django.db.models import DecimalField, F, IntegerField, Sum, Value, Q
    from django.db.models.functions import Coalesce
    from django.utils import timezone
    from ecom.models import OrderItem

    # Get search query
    search_query = request.GET.get('q', '').strip()

    products = (
        Product.objects
        .annotate(
            units_sold=Coalesce(
                Sum('orderitem__quantity', output_field=IntegerField()),
                Value(0, output_field=IntegerField()),
            ),
            revenue=Coalesce(
                Sum(
                    F('orderitem__quantity') * F('orderitem__price'),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
                Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)),
            ),
        )
        .order_by('-created_at')
    )
    
    # Apply search filter
    if search_query:
        products = products.filter(
            Q(name__icontains=search_query) |
            Q(sku__icontains=search_query) |
            Q(category__name__icontains=search_query)
        )

    total_products = products.count()
    in_stock = products.filter(stock__gt=0).count()
    low_stock = products.filter(stock__gt=0, stock__lte=10).count()
    out_of_stock = products.filter(stock=0).count()

    total_revenue = OrderItem.objects.aggregate(
        total=Sum(
            F('quantity') * F('price'),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
    )['total'] or 0

    total_units_sold = OrderItem.objects.aggregate(
        total=Sum('quantity')
    )['total'] or 0

    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_revenue = OrderItem.objects.filter(order__created_at__gte=month_start).aggregate(
        total=Sum(
            F('quantity') * F('price'),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
    )['total'] or 0

    monthly_units_sold = OrderItem.objects.filter(order__created_at__gte=month_start).aggregate(
        total=Sum('quantity')
    )['total'] or 0

    context = {
        'products': products,
        'total_products': total_products,
        'in_stock': in_stock,
        'low_stock': low_stock,
        'out_of_stock': out_of_stock,
        'total_revenue': total_revenue,
        'total_units_sold': total_units_sold,
        'monthly_revenue': monthly_revenue,
        'monthly_units_sold': monthly_units_sold,
        'search_query': search_query,
    }
    return render(request, 'admin_dashboard/products.html', context)


@admin_required
def export_products_csv(request):
    """Export products to CSV"""
    import csv
    from django.db.models import DecimalField, F, IntegerField, Sum, Value
    from django.db.models.functions import Coalesce
    from ecom.models import OrderItem

    products = (
        Product.objects
        .annotate(
            units_sold=Coalesce(
                Sum('orderitem__quantity', output_field=IntegerField()),
                Value(0, output_field=IntegerField()),
            ),
            revenue=Coalesce(
                Sum(
                    F('orderitem__quantity') * F('orderitem__price'),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
                Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)),
            ),
        )
        .order_by('name')
    )

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="products.csv"'
    writer = csv.writer(response)
    writer.writerow(['SKU', 'Name', 'Category', 'Stock', 'Customer Price', 'Wholesaler Price', 'Retailer Price', 'Hospital Price', 'Pharmacy Price', 'Units Sold', 'Revenue'])
    for p in products:
        writer.writerow([
            p.sku or '', p.name, getattr(p.category, 'name', ''), p.stock,
            float(p.customer_price or 0), float(p.wholesaler_price or 0), float(p.retailer_price or 0),
            float(p.hospital_price or 0), float(p.pharmacy_price or 0), int(p.units_sold or 0), float(p.revenue or 0),
        ])
    return response

@admin_required
def add_product(request):
    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES)
        
        if form.is_valid():
            product = form.save()
            
            # Handle multiple image uploads (optional)
            uploaded_images = _dedupe_uploaded_files(request.FILES.getlist("images"))
            
            image_objects = []
            for img in uploaded_images:
                image_obj = ProductImage.objects.create(product=product, image=img)
                image_objects.append(image_obj)
            
            # Handle manually selected thumbnail
            thumb_index_str = request.POST.get("thumbnail_image", "")
            
            if thumb_index_str and thumb_index_str.isdigit() and image_objects:
                thumb_index = int(thumb_index_str)
                if 0 <= thumb_index < len(image_objects):
                    thumbnail_image_obj = image_objects[thumb_index]
                    thumbnail_image_obj.is_thumbnail = True
                    thumbnail_image_obj.save()
                    product.thumbnail = thumbnail_image_obj
                    product.save()
            elif image_objects:
                # Set first image as thumbnail if none selected
                first_image = image_objects[0]
                first_image.is_thumbnail = True
                first_image.save()
                product.thumbnail = first_image
                product.save()
            
            messages.success(request, 'Product added successfully!')
            return redirect("admin_products")
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ProductForm()
    
    return render(request, "admin_dashboard/add_product.html", {
        "form": form,
    })




# Replace the three image management functions in admin_dashboard/views.py with this:

# Replace the three image management functions in admin_dashboard/views.py with this:

@admin_required
def set_product_thumbnail(request, product_id, image_id):
    """Set product thumbnail"""
    if request.method == 'POST':
        try:
            product = get_object_or_404(Product, id=product_id)
            image = ProductImage.objects.get(id=image_id, product=product)
            
            # Update all images to not be thumbnail
            ProductImage.objects.filter(product=product).update(is_thumbnail=False)
            
            # Set this image as thumbnail
            image.is_thumbnail = True
            image.save()
            product.thumbnail = image
            product.save()
            
            messages.success(request, 'Thumbnail updated successfully!')
            return JsonResponse({
                'success': True,
                'message': 'Thumbnail updated',
                'thumbnail_id': str(image.id)
            })
        except ProductImage.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Image not found'
            }, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=400)
    return JsonResponse({'success': False, 'message': 'Invalid request'}, status=405)

@admin_required
def delete_product_image(request, product_id, image_id):
    """Delete product image"""
    if request.method == 'POST':
        try:
            product = get_object_or_404(Product, id=product_id)
            image = ProductImage.objects.get(id=image_id, product=product)
            
            # If this is the thumbnail, unset it
            if product.thumbnail == image:
                product.thumbnail = None
                product.save()
            
            image.delete()
            messages.success(request, 'Image deleted successfully!')
            return JsonResponse({
                'success': True,
                'message': 'Image deleted'
            })
        except ProductImage.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Image not found'
            }, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=400)
    return JsonResponse({'success': False, 'message': 'Invalid request'}, status=405)

@admin_required
def add_product_images(request, product_id):
    """Add new product images"""
    if request.method == 'POST':
        try:
            product = get_object_or_404(Product, id=product_id)
            new_images = _dedupe_uploaded_files(request.FILES.getlist('new_images'))
            
            if not new_images:
                return JsonResponse({
                    'success': False,
                    'message': 'No images selected'
                }, status=400)
            
            added_images = []
            for image_file in new_images:
                img = ProductImage.objects.create(
                    product=product,
                    image=image_file,
                    is_thumbnail=False
                )
                added_images.append({
                    'id': str(img.id),
                    'url': img.image.url
                })
            
            messages.success(request, f'{len(new_images)} image(s) added successfully!')
            return JsonResponse({
                'success': True,
                'message': f'{len(added_images)} image(s) added',
                'images': added_images
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=400)
    return JsonResponse({'success': False, 'message': 'Invalid request'}, status=405)


@admin_required
def cleanup_duplicate_product_images(request, product_id):
    """Remove duplicate images for a product based on image content hash."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid request'}, status=405)

    product = get_object_or_404(Product, id=product_id)
    images = list(product.images.all().order_by('created_at', 'id'))

    if len(images) < 2:
        return JsonResponse({'success': True, 'deleted': 0, 'message': 'No duplicate images found.'})

    grouped = {}
    for image in images:
        digest = _hash_product_image(image)
        if not digest:
            digest = f'unhashable:{image.id}'
        grouped.setdefault(digest, []).append(image)

    deleted_count = 0

    for _, group in grouped.items():
        if len(group) <= 1:
            continue

        keep = next((img for img in group if img.id == product.thumbnail_id), None)
        if keep is None:
            keep = next((img for img in group if img.is_thumbnail), group[0])

        for image in group:
            if image.id == keep.id:
                continue
            image.delete()
            deleted_count += 1

    remaining = ProductImage.objects.filter(product=product).order_by('created_at', 'id')
    thumbnail = remaining.filter(id=product.thumbnail_id).first() if product.thumbnail_id else None

    if not thumbnail:
        thumbnail = remaining.filter(is_thumbnail=True).first() or remaining.first()

    if thumbnail:
        ProductImage.objects.filter(product=product).exclude(id=thumbnail.id).update(is_thumbnail=False)
        ProductImage.objects.filter(id=thumbnail.id).update(is_thumbnail=True)
        if product.thumbnail_id != thumbnail.id:
            product.thumbnail = thumbnail
            product.save(update_fields=['thumbnail'])
    elif product.thumbnail_id:
        product.thumbnail = None
        product.save(update_fields=['thumbnail'])

    if deleted_count:
        messages.success(request, f'Removed {deleted_count} duplicate image(s).')
    else:
        messages.info(request, 'No duplicate images found.')

    return JsonResponse({
        'success': True,
        'deleted': deleted_count,
        'message': f'Removed {deleted_count} duplicate image(s).' if deleted_count else 'No duplicate images found.',
    })


@admin_required
def edit_product(request, product_id):
    """View and edit product details"""
    product = get_object_or_404(Product, id=product_id)
    categories = Category.objects.all()
    
    if request.method == 'POST':
        # Handle regular form submission (product details only)
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, 'Product updated successfully!')
            return redirect('edit_product', product_id=product.id)
    else:
        form = ProductForm(instance=product)
    
    context = {
        'product': product,
        'form': form,
        'categories': categories,
        'page_title': product.name,
    }
    return render(request, 'admin_dashboard/product_details.html', context)


def _dedupe_uploaded_files(files):
    """Remove duplicate files within a single request payload.

    This prevents accidental double-submits from creating repeated image rows.
    """
    unique_files = []
    seen_hashes = set()

    for file_obj in files or []:
        hasher = hashlib.sha256()
        for chunk in file_obj.chunks():
            hasher.update(chunk)
        digest = hasher.hexdigest()
        file_obj.seek(0)

        if digest in seen_hashes:
            continue

        seen_hashes.add(digest)
        unique_files.append(file_obj)

    return unique_files


def _hash_product_image(image_obj):
    """Compute a deterministic hash for a stored product image file."""
    image_field = getattr(image_obj, 'image', None)
    if not image_field:
        return None

    try:
        image_field.open('rb')
        hasher = hashlib.sha256()
        for chunk in image_field.chunks():
            hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return None
    finally:
        try:
            image_field.close()
        except Exception:
            pass



@admin_required
def delete_product(request, product_id):
    if request.method == 'DELETE':
        product = get_object_or_404(Product, id=product_id)
        product.delete()
        return JsonResponse({'success': True, 'message': 'Product deleted successfully'})
    return JsonResponse({'success': False, 'message': 'Invalid request'}, status=400)


# Category Views
@admin_required
def categories_page(request):
    # Get search query
    search_query = request.GET.get('q', '').strip()
    
    categories = Category.objects.all().order_by('-created_at')
    
    # Apply search filter
    if search_query:
        categories = categories.filter(
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    return render(request, 'admin_dashboard/categories.html', {
        'categories': categories,
        'search_query': search_query,
    })

@admin_required
def add_category(request):
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save()
            messages.success(request, f'Category {category.name} created successfully!')
            # HTMX-friendly redirect to reload the categories list
            resp = HttpResponse('')
            resp['HX-Redirect'] = reverse('admin_categories')
            return resp
        # Return the form partial with errors (HTTP 200 so HTMX can swap it)
        return render(request, 'partials/admin_dashboard/category_form.html', {'form': form})
    # GET: serve empty form partial
    form = CategoryForm()
    return render(request, 'partials/admin_dashboard/category_form.html', {'form': form})


@admin_required
def edit_category(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, 'Category updated successfully!')
            return redirect('admin_categories')
    else:
        form = CategoryForm(instance=category)
    return render(request, 'admin_dashboard/partials/category_form.html', {'form': form, 'category': category})

@admin_required
def delete_category(request, category_id):
    if request.method == 'DELETE':
        category = get_object_or_404(Category, id=category_id)
        category.delete()
        return JsonResponse({'success': True, 'message': 'Category deleted successfully'})
    return JsonResponse({'success': False, 'message': 'Invalid request'}, status=400)


@admin_required
def blog_categories_page(request):
    categories = BlogCategory.objects.all().order_by('name')
    return render(request, 'admin_dashboard/blog_categories.html', {'categories': categories})


@admin_required
def add_blog_category(request):
    if request.method == 'POST':
        form = BlogCategoryForm(request.POST)
        if form.is_valid():
            category = form.save()
            messages.success(request, f'Category {category.name} created successfully!')
            resp = HttpResponse('')
            resp['HX-Redirect'] = reverse('admin_blog_categories')
            return resp
        return render(request, 'partials/admin_dashboard/blog_category_form.html', {'form': form})
    form = BlogCategoryForm()
    return render(request, 'partials/admin_dashboard/blog_category_form.html', {'form': form})


@admin_required
def edit_blog_category(request, category_id):
    category = get_object_or_404(BlogCategory, id=category_id)
    if request.method == 'POST':
        form = BlogCategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, 'Category updated successfully!')
            # Return response with HX-Redirect for HTMX
            resp = HttpResponse('')
            resp['HX-Redirect'] = reverse('admin_blog_categories')
            return resp
        return render(request, 'partials/admin_dashboard/blog_category_form.html', {'form': form, 'category': category})
    else:
        form = BlogCategoryForm(instance=category)
    return render(request, 'partials/admin_dashboard/blog_category_form.html', {'form': form, 'category': category})


@admin_required
def delete_blog_category(request, category_id):
    if request.method == 'DELETE':
        category = get_object_or_404(BlogCategory, id=category_id)
        category.delete()
        return JsonResponse({'success': True, 'message': 'Category deleted successfully'})
    return JsonResponse({'success': False, 'message': 'Invalid request'}, status=400)


@admin_required
def orders_page(request):
    """Orders management page with pagination"""
    from ecom.models import Order
    from django.db.models import Count, Q
    from django.core.paginator import Paginator
    
    # Get filter parameters
    status_filter = request.GET.get('status', 'all')
    search_query = request.GET.get('q', '').strip()
    page = request.GET.get('page', 1)
    
    # Get all orders
    orders = Order.objects.select_related('user').prefetch_related('items__product').all()
    
    # Apply status filter
    if status_filter == 'processing':
        orders = orders.filter(status__in=[
            'ordered', 'inbound', 'packaged', 'outbound', 'picked',
            'departed', 'arrived', 'customs_declaration', 'flight_departed',
            'flight_landed', 'in_clearance', 'clearance_exception',
            'clearance_completed', 'in_delivery', 'returning',
        ])
    elif status_filter == 'completed':
        orders = orders.filter(status='delivered')
    elif status_filter == 'cancelled':
        orders = orders.filter(status='cancelled')
    
    # Apply search filter
    if search_query:
        orders = orders.filter(
            Q(id__icontains=search_query) |
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query) |
            Q(user__email__icontains=search_query)
        )
    
    # Sort by newest first
    orders = orders.order_by('-created_at')
    
    # Calculate statistics
    total_orders = Order.objects.count()
    cancelled_orders = Order.objects.filter(status='cancelled').count()
    active_orders = Order.objects.filter(status__in=[
        'pending', 'ordered', 'inbound', 'packaged', 'outbound', 'picked',
        'departed', 'arrived', 'customs_declaration', 'flight_departed',
        'flight_landed', 'in_clearance', 'clearance_exception',
        'clearance_completed', 'in_delivery', 'returning',
    ]).count()
    completed_orders = Order.objects.filter(status='delivered').count()
    processing_orders = Order.objects.filter(status__in=[
        'ordered', 'inbound', 'packaged', 'outbound', 'picked',
        'departed', 'arrived', 'customs_declaration', 'flight_departed',
        'flight_landed', 'in_clearance', 'clearance_exception',
        'clearance_completed', 'in_delivery', 'returning',
    ]).count()
    
    # Paginate results (12 per page)
    paginator = Paginator(orders, 12)
    page_obj = paginator.get_page(page)
    
    # Check if this is an HTMX request for more orders
    if request.headers.get('HX-Request') == 'true':
        # Return just the table rows partial
        return render(request, 'admin_dashboard/partials/orders_table_rows.html', {
            'orders': page_obj.object_list,
            'page_obj': page_obj,
            'status_filter': status_filter,
            'search_query': search_query,
        })
    
    context = {
        'page_title': 'Orders',
        'orders': page_obj.object_list,
        'page_obj': page_obj,
        'total_orders': total_orders,
        'cancelled_orders': cancelled_orders,
        'active_orders': active_orders,
        'completed_orders': completed_orders,
        'processing_orders': processing_orders,
        'status_filter': status_filter,
        'search_query': search_query,
    }
    return render(request, 'admin_dashboard/orders.html', context)


@admin_required
def export_orders_csv(request):
    """Export orders to CSV respecting status filter"""
    import csv
    from ecom.models import Order
    from django.db.models import Q, Count, Sum

    status_filter = request.GET.get('status', 'all')
    orders = Order.objects.select_related('user').annotate(
        items_count=Count('items'),
        items_qty=Sum('items__quantity')
    ).all()
    if status_filter == 'processing':
        orders = orders.filter(Q(status='processing') | Q(status='shipped'))
    elif status_filter == 'completed':
        orders = orders.filter(status='delivered')
    elif status_filter == 'cancelled':
        orders = orders.filter(status='cancelled')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="orders.csv"'
    writer = csv.writer(response)
    writer.writerow(['Order ID', 'User Email', 'User Role', 'Status', 'Total Amount', 'Items Count', 'Items Qty', 'Created At'])
    for o in orders.order_by('-created_at'):
        writer.writerow([
            str(o.id), getattr(o.user, 'email', ''), getattr(o.user, 'role', ''), o.status,
            float(o.total_amount or 0), int(o.items_count or 0), int(o.items_qty or 0), o.created_at.strftime('%Y-%m-%d %H:%M'),
        ])
    return response


@admin_required
def order_detail(request, order_id):
    """Detailed view for a single order with items and shipping info"""
    from ecom.models import Order

    if request.user.role != User.ADMINISTRATOR or not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('admin_login')

    order = get_object_or_404(
        Order.objects.select_related('user').prefetch_related('items__product__thumbnail', 'items__product__images'),
        id=order_id
    )

    items = list(order.items.all())
    items_total = sum((item.get_total_price() for item in items), Decimal('0'))
    delivery_fee = max(order.total_amount - items_total, Decimal('0'))
    tax_amount = Decimal('0')
    total_paid = order.total_amount

    context = {
        'order': order,
        'items': items,
        'items_total': items_total,
        'delivery_fee': delivery_fee,
        'tax_amount': tax_amount,
        'total_paid': total_paid,
    }
    return render(request, 'admin_dashboard/order_detail.html', context)


@admin_required
def orders_tracking(request, order_id=None):
    """Tracking screen with status filters; status is sourced from Speedaf."""
    from ecom.models import Order

    if request.user.role != User.ADMINISTRATOR or not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('admin_login')

    status_param = request.GET.get('status', 'all')
    if request.method == 'POST':
        messages.info(request, 'Manual status updates are disabled. Tracking status is synced from Speedaf.')
        return redirect(request.get_full_path())

    orders = Order.objects.select_related('user').prefetch_related('items__product__thumbnail').order_by('-created_at')

    if order_id:
        orders = orders.filter(id=order_id)
    else:
        if status_param == 'in_progress':
            orders = orders.filter(status__in=[
                'pending', 'ordered', 'inbound', 'packaged', 'outbound', 'picked',
                'departed', 'arrived', 'customs_declaration', 'flight_departed',
                'flight_landed', 'in_clearance', 'clearance_exception',
                'clearance_completed', 'in_delivery', 'returning',
            ])
        elif status_param == 'completed':
            orders = orders.filter(status='delivered')
        elif status_param == 'cancelled':
            orders = orders.filter(status='cancelled')

    total_orders = orders.count()
    in_progress_count = orders.filter(status__in=[
        'pending', 'ordered', 'inbound', 'packaged', 'outbound', 'picked',
        'departed', 'arrived', 'customs_declaration', 'flight_departed',
        'flight_landed', 'in_clearance', 'clearance_exception',
        'clearance_completed', 'in_delivery', 'returning',
    ]).count()
    completed_count = orders.filter(status='delivered').count()

    progress_map = {
        'pending':             1,
        'ordered':             2,
        'inbound':             3,
        'packaged':            3,
        'outbound':            3,
        'picked':              4,
        'departed':            4,
        'arrived':             5,
        'customs_declaration': 5,
        'flight_departed':     5,
        'flight_landed':       5,
        'in_clearance':        5,
        'clearance_exception': 5,
        'clearance_completed': 6,
        'in_delivery':         7,
        'delivered':           8,
        'returning':           2,
        'returned':            2,
        'cancelled':           0,
    }
    orders_data = [
        {
            'order': order,
            'progress': progress_map.get(order.status, 1),
        }
        for order in orders
    ]

    context = {
        'orders_data': orders_data,
        'status_param': status_param,
        'total_orders': total_orders,
        'in_progress_count': in_progress_count,
        'completed_count': completed_count,
    }
    return render(request, 'admin_dashboard/orders_tracking.html', context)


@admin_required
def delete_order(request, order_id):
    """Delete an order"""
    from ecom.models import Order
    
    if request.user.role != User.ADMINISTRATOR or not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied.'}, status=403)
    
    if request.method == 'DELETE':
        order = get_object_or_404(Order, id=order_id)
        order.delete()
        return JsonResponse({'success': True, 'message': 'Order deleted successfully'})
    
    return JsonResponse({'success': False, 'message': 'Invalid request'}, status=400)


@admin_required
def cancel_order(request, order_id):
    """Cancel an order"""
    from ecom.models import Order
    
    if request.user.role != User.ADMINISTRATOR or not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied.'}, status=403)
    
    if request.method == 'POST':
        order = get_object_or_404(Order, id=order_id)
        if order.status not in ['delivered', 'cancelled']:
            order.status = 'cancelled'
            order.save(update_fields=['status', 'updated_at'])
            return JsonResponse({'success': True, 'message': 'Order cancelled successfully'})
        else:
            return JsonResponse({'success': False, 'message': 'Cannot cancel a delivered or already cancelled order'})
    
    return JsonResponse({'success': False, 'message': 'Invalid request'}, status=400)


@admin_required
def analytics_page(request):
    """Analytics dashboard with real DB data"""
    from django.db.models.functions import TruncWeek
    from django.utils import timezone
    from datetime import timedelta

    now = timezone.now()
    current_year  = now.year
    prev_year     = current_year - 1
    this_month    = now.month
    prev_month    = this_month - 1 if this_month > 1 else 12
    prev_month_year = current_year if this_month > 1 else prev_year

    # ── Total Orders ────────────────────────────────────────────────────────
    total_orders = Order.objects.count()
    orders_this_month = Order.objects.filter(
        created_at__year=current_year, created_at__month=this_month
    ).count()
    orders_prev_month = Order.objects.filter(
        created_at__year=prev_month_year, created_at__month=prev_month
    ).count()
    orders_mom = round((orders_this_month - orders_prev_month) / orders_prev_month * 100, 1) if orders_prev_month else None

    # ── Total Sales (units sold) ─────────────────────────────────────────────
    from ecom.models import OrderItem
    total_sales = OrderItem.objects.aggregate(t=Sum('quantity'))['t'] or 0
    sales_this_month = OrderItem.objects.filter(
        order__created_at__year=current_year, order__created_at__month=this_month
    ).aggregate(t=Sum('quantity'))['t'] or 0
    sales_prev_month = OrderItem.objects.filter(
        order__created_at__year=prev_month_year, order__created_at__month=prev_month
    ).aggregate(t=Sum('quantity'))['t'] or 0
    sales_mom = round((sales_this_month - sales_prev_month) / sales_prev_month * 100, 1) if sales_prev_month else None

    # ── Annual Revenue ───────────────────────────────────────────────────────
    annual_revenue = Order.objects.filter(
        created_at__year=current_year, payment_status='completed'
    ).aggregate(t=Sum('total_amount'))['t'] or Decimal('0')
    prev_year_revenue = Order.objects.filter(
        created_at__year=prev_year, payment_status='completed'
    ).aggregate(t=Sum('total_amount'))['t'] or Decimal('0')
    revenue_yoy = round(float((annual_revenue - prev_year_revenue) / prev_year_revenue * 100), 1) if prev_year_revenue else None

    # ── Users ────────────────────────────────────────────────────────────────
    total_users = User.objects.count()
    users_this_year  = User.objects.filter(date_joined__year=current_year).count()
    users_prev_year  = User.objects.filter(date_joined__year=prev_year).count()
    users_yoy = round((users_this_year - users_prev_year) / users_prev_year * 100, 1) if users_prev_year else None

    # ── Monthly Sign-ups ─────────────────────────────────────────────────────
    monthly_signups = [0] * 12
    for d in User.objects.filter(date_joined__year=current_year).annotate(
        month=TruncMonth('date_joined')
    ).values('month').annotate(count=Count('id')).order_by('month'):
        monthly_signups[d['month'].month - 1] = d['count']

    # ── Monthly Revenue: current year vs prev year ───────────────────────────
    monthly_rev_current = [0.0] * 12
    for d in Order.objects.filter(
        created_at__year=current_year, payment_status='completed'
    ).annotate(month=TruncMonth('created_at')).values('month').annotate(
        t=Sum('total_amount')
    ).order_by('month'):
        monthly_rev_current[d['month'].month - 1] = float(d['t'])

    monthly_rev_prev = [0.0] * 12
    for d in Order.objects.filter(
        created_at__year=prev_year, payment_status='completed'
    ).annotate(month=TruncMonth('created_at')).values('month').annotate(
        t=Sum('total_amount')
    ).order_by('month'):
        monthly_rev_prev[d['month'].month - 1] = float(d['t'])

    # ── Last 7 Days ──────────────────────────────────────────────────────────
    seven_days_ago = now - timedelta(days=7)
    last7_revenue = Order.objects.filter(
        created_at__gte=seven_days_ago, payment_status='completed'
    ).aggregate(t=Sum('total_amount'))['t'] or Decimal('0')
    last7_items = OrderItem.objects.filter(
        order__created_at__gte=seven_days_ago, order__payment_status='completed'
    ).aggregate(t=Sum('quantity'))['t'] or 0

    # ── Today's new products ─────────────────────────────────────────────────
    from admin_dashboard.models import Product
    today = now.date()
    new_products_today = Product.objects.filter(created_at__date=today).count()

    # ── Average Order Value — last 7 weeks ───────────────────────────────────
    weekly_avg_labels = []
    weekly_avg_data   = []
    for i in range(6, -1, -1):
        week_start = (now - timedelta(weeks=i)).date()
        week_start = week_start - timedelta(days=week_start.weekday())  # Monday
        week_end   = week_start + timedelta(days=6)
        qs = Order.objects.filter(
            created_at__date__gte=week_start,
            created_at__date__lte=week_end,
            payment_status='completed'
        ).aggregate(t=Sum('total_amount'), c=Count('id'))
        rev   = float(qs['t'] or 0)
        cnt   = qs['c'] or 0
        avg   = round(rev / cnt, 2) if cnt else 0
        weekly_avg_labels.append(f"Wk {week_start.strftime('%d %b')}")
        weekly_avg_data.append(avg)

    completed_orders = Order.objects.filter(payment_status='completed').count()

    # ── Website visits (last 14 days) ───────────────────────────────────────
    today_local = timezone.localdate()
    visit_days = [today_local - timedelta(days=i) for i in range(13, -1, -1)]
    visit_stats = DailyWebsiteVisit.objects.filter(
        date__gte=visit_days[0],
        date__lte=visit_days[-1],
    )
    visit_map = {stat.date: stat for stat in visit_stats}
    daily_visits = [int(visit_map.get(day).total_visits if visit_map.get(day) else 0) for day in visit_days]
    daily_unique_visitors = [int(visit_map.get(day).unique_visitors if visit_map.get(day) else 0) for day in visit_days]
    visit_labels = [day.strftime('%b %d') for day in visit_days]

    today_stat = visit_map.get(today_local)
    visits_today = int(today_stat.total_visits) if today_stat else 0
    unique_visitors_today = int(today_stat.unique_visitors) if today_stat else 0
    avg_daily_visits = round(sum(daily_visits) / len(daily_visits), 1) if daily_visits else 0

    context = {
        'page_title': 'Analytics',
        # Cards
        'total_sales':    total_sales,
        'total_orders':   total_orders,
        'annual_revenue': annual_revenue,
        'total_users':    total_users,
        'sales_mom':      sales_mom,
        'orders_mom':     orders_mom,
        'revenue_yoy':    revenue_yoy,
        'users_yoy':      users_yoy,
        # Charts
        'monthly_signups':     json.dumps(monthly_signups),
        'monthly_rev_current': json.dumps(monthly_rev_current),
        'monthly_rev_prev':    json.dumps(monthly_rev_prev),
        'weekly_avg_labels':   json.dumps(weekly_avg_labels),
        'weekly_avg_data':     json.dumps(weekly_avg_data),
        # Bottom section
        'last7_revenue':       last7_revenue,
        'last7_items':         last7_items,
        'new_products_today':  new_products_today,
        'visits_today':        visits_today,
        'unique_visitors_today': unique_visitors_today,
        'avg_daily_visits':    avg_daily_visits,
        'daily_visits':        json.dumps(daily_visits),
        'daily_unique_visitors': json.dumps(daily_unique_visitors),
        'visit_labels':        json.dumps(visit_labels),
        'current_year':        current_year,
        'prev_year':           prev_year,
        'completed_orders':    completed_orders,
    }
    return render(request, 'admin_dashboard/analytics.html', context)


@admin_required
def website_visits_page(request):
    """Admin view for historical daily website visits with filtering."""
    from datetime import timedelta
    from django.core.paginator import Paginator

    start_date_str = (request.GET.get('start_date') or '').strip()
    end_date_str = (request.GET.get('end_date') or '').strip()

    qs = DailyWebsiteVisit.objects.all().order_by('-date')

    start_date = None
    end_date = None
    try:
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except ValueError:
        messages.error(request, 'Invalid date format. Use YYYY-MM-DD.')
        return redirect('admin_website_visits')

    if start_date:
        qs = qs.filter(date__gte=start_date)
    if end_date:
        qs = qs.filter(date__lte=end_date)

    if start_date and end_date and start_date > end_date:
        messages.error(request, 'Start date cannot be after end date.')
        return redirect('admin_website_visits')

    total_visits = qs.aggregate(total=Sum('total_visits'))['total'] or 0
    total_unique_visitors = qs.aggregate(total=Sum('unique_visitors'))['total'] or 0
    days_count = qs.count()
    avg_visits = round(total_visits / days_count, 1) if days_count else 0

    today = timezone.localdate()
    recent_7_start = today - timedelta(days=6)
    recent_7_visits = DailyWebsiteVisit.objects.filter(
        date__gte=recent_7_start,
        date__lte=today,
    ).aggregate(total=Sum('total_visits'))['total'] or 0

    page = request.GET.get('page', 1)
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(page)

    context = {
        'page_title': 'Website Visits',
        'page_obj': page_obj,
        'visits': page_obj,
        'start_date': start_date_str,
        'end_date': end_date_str,
        'total_visits': total_visits,
        'total_unique_visitors': total_unique_visitors,
        'days_count': days_count,
        'avg_visits': avg_visits,
        'recent_7_visits': recent_7_visits,
    }
    return render(request, 'admin_dashboard/website_visits.html', context)


@admin_required
def export_website_visits_csv(request):
    """Export website visits with optional date filters."""
    import csv

    start_date_str = (request.GET.get('start_date') or '').strip()
    end_date_str = (request.GET.get('end_date') or '').strip()

    qs = DailyWebsiteVisit.objects.all().order_by('-date')

    start_date = None
    end_date = None
    try:
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except ValueError:
        messages.error(request, 'Invalid date format. Use YYYY-MM-DD.')
        return redirect('admin_website_visits')

    if start_date:
        qs = qs.filter(date__gte=start_date)
    if end_date:
        qs = qs.filter(date__lte=end_date)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="website_visits.csv"'
    writer = csv.writer(response)
    writer.writerow(['Date', 'Total Visits', 'Unique Visitors'])

    for row in qs:
        writer.writerow([
            row.date.isoformat(),
            int(row.total_visits or 0),
            int(row.unique_visitors or 0),
        ])

    return response


@admin_required
def reward_withdrawals_page(request):
    """Admin view for wallet withdrawal monitoring and operations."""
    from django.core.paginator import Paginator

    status_filter = (request.GET.get('status') or 'all').strip().lower()
    search_query = (request.GET.get('q') or '').strip()
    start_date_str = (request.GET.get('start_date') or '').strip()
    end_date_str = (request.GET.get('end_date') or '').strip()

    qs = WalletWithdrawalRequest.objects.select_related('user', 'bank_account').order_by('-created_at')

    if status_filter in {
        WalletWithdrawalRequest.PENDING,
        WalletWithdrawalRequest.PROCESSING,
        WalletWithdrawalRequest.SUCCESS,
        WalletWithdrawalRequest.FAILED,
    }:
        qs = qs.filter(status=status_filter)
    else:
        status_filter = 'all'

    if search_query:
        qs = qs.filter(
            Q(reference__icontains=search_query)
            | Q(monnify_reference__icontains=search_query)
            | Q(user__email__icontains=search_query)
            | Q(bank_account__account_number__icontains=search_query)
            | Q(bank_account__account_name__icontains=search_query)
        )

    start_date = None
    end_date = None
    try:
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except ValueError:
        messages.error(request, 'Invalid date format. Use YYYY-MM-DD.')
        return redirect('admin_reward_withdrawals')

    if start_date and end_date and start_date > end_date:
        messages.error(request, 'Start date cannot be after end date.')
        return redirect('admin_reward_withdrawals')

    if start_date:
        qs = qs.filter(created_at__date__gte=start_date)
    if end_date:
        qs = qs.filter(created_at__date__lte=end_date)

    total_count = qs.count()
    total_amount = qs.aggregate(total=Sum('amount'))['total'] or Decimal('0')
    pending_count = qs.filter(status=WalletWithdrawalRequest.PENDING).count()
    processing_count = qs.filter(status=WalletWithdrawalRequest.PROCESSING).count()
    success_count = qs.filter(status=WalletWithdrawalRequest.SUCCESS).count()
    failed_count = qs.filter(status=WalletWithdrawalRequest.FAILED).count()

    page = request.GET.get('page', 1)
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(page)

    context = {
        'page_title': 'Reward Withdrawals',
        'withdrawals': page_obj,
        'page_obj': page_obj,
        'status_filter': status_filter,
        'search_query': search_query,
        'start_date': start_date_str,
        'end_date': end_date_str,
        'total_count': total_count,
        'total_amount': total_amount,
        'pending_count': pending_count,
        'processing_count': processing_count,
        'success_count': success_count,
        'failed_count': failed_count,
    }
    return render(request, 'admin_dashboard/reward_withdrawals.html', context)


@admin_required
def export_reward_withdrawals_csv(request):
    """Export wallet withdrawal rows with current filters."""
    import csv

    status_filter = (request.GET.get('status') or 'all').strip().lower()
    search_query = (request.GET.get('q') or '').strip()
    start_date_str = (request.GET.get('start_date') or '').strip()
    end_date_str = (request.GET.get('end_date') or '').strip()

    qs = WalletWithdrawalRequest.objects.select_related('user', 'bank_account').order_by('-created_at')

    if status_filter in {
        WalletWithdrawalRequest.PENDING,
        WalletWithdrawalRequest.PROCESSING,
        WalletWithdrawalRequest.SUCCESS,
        WalletWithdrawalRequest.FAILED,
    }:
        qs = qs.filter(status=status_filter)

    if search_query:
        qs = qs.filter(
            Q(reference__icontains=search_query)
            | Q(monnify_reference__icontains=search_query)
            | Q(user__email__icontains=search_query)
            | Q(bank_account__account_number__icontains=search_query)
            | Q(bank_account__account_name__icontains=search_query)
        )

    try:
        if start_date_str:
            qs = qs.filter(created_at__date__gte=datetime.strptime(start_date_str, '%Y-%m-%d').date())
        if end_date_str:
            qs = qs.filter(created_at__date__lte=datetime.strptime(end_date_str, '%Y-%m-%d').date())
    except ValueError:
        messages.error(request, 'Invalid date format. Use YYYY-MM-DD.')
        return redirect('admin_reward_withdrawals')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="reward_withdrawals.csv"'
    writer = csv.writer(response)
    writer.writerow([
        'Created At',
        'User Email',
        'Amount',
        'Status',
        'Reference',
        'Provider Reference',
        'Account Name',
        'Account Number',
        'Bank Name',
        'Failure Reason',
    ])

    for row in qs:
        writer.writerow([
            timezone.localtime(row.created_at).strftime('%Y-%m-%d %H:%M:%S'),
            row.user.email,
            f"{row.amount:.2f}",
            row.status,
            row.reference,
            row.monnify_reference or '',
            row.bank_account.account_name,
            row.bank_account.account_number,
            row.bank_account.bank_name or row.bank_account.bank_code,
            row.failure_reason or '',
        ])

    return response


@admin_required
def retry_reward_withdrawal(request, withdrawal_id):
    """Retry failed wallet withdrawal payout."""
    if request.method != 'POST':
        messages.error(request, 'Invalid request method for retry.')
        return redirect('admin_reward_withdrawals')

    withdrawal = get_object_or_404(WalletWithdrawalRequest, id=withdrawal_id)

    if withdrawal.status != WalletWithdrawalRequest.FAILED:
        messages.warning(request, 'Only failed withdrawals can be retried.')
        return redirect('admin_reward_withdrawals')

    try:
        process_withdrawal_request_task.delay(str(withdrawal.pk))
        messages.success(request, f'Withdrawal {withdrawal.reference} retry queued.')
    except WalletOperationError as exc:
        messages.error(request, f'Retry failed: {exc}')

    return redirect('admin_reward_withdrawals')

@admin_required
@admin_required
def customers_page(request):
    """Users management page - shows all users with their roles"""
    from django.db.models import Count
    
    # Get filter and search parameters
    role_filter = request.GET.get('role', 'all')
    search_query = request.GET.get('q', '').strip()
    
    # Get all users
    users = User.objects.all().annotate(
        total_orders=Count('orders'),
        completed_referral_orders=Count('referred_orders', filter=Q(referred_orders__payment_status='completed')),
    ).order_by('-date_joined')
    
    # Apply role filter
    if role_filter == 'administrator':
        users = users.filter(role=User.ADMINISTRATOR)
    elif role_filter == 'wholesaler':
        users = users.filter(role=User.WHOLESALER)
    elif role_filter == 'retailer':
        users = users.filter(role=User.RETAILER)
    elif role_filter == 'end_user':
        users = users.filter(role=User.END_USER)
    
    # Apply search filter
    if search_query:
        users = users.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(phone_number__icontains=search_query)
        )
    
    # Calculate stats
    total_users = User.objects.count()
    total_administrators = User.objects.filter(role=User.ADMINISTRATOR).count()
    total_wholesalers = User.objects.filter(role=User.WHOLESALER).count()
    total_retailers = User.objects.filter(role=User.RETAILER).count()
    total_customers = User.objects.filter(role=User.END_USER).count()
    
    context = {
        'page_title': 'Users',
        'users': users,
        'total_users': total_users,
        'total_administrators': total_administrators,
        'total_wholesalers': total_wholesalers,
        'total_retailers': total_retailers,
        'total_customers': total_customers,
        'role_filter': role_filter,
        'search_query': search_query,
    }
    return render(request, 'admin_dashboard/customers.html', context)


@admin_required
def end_users_page(request):
    """End Users management page - lists regular customers (END_USER) only"""
    from django.db.models import Count, Sum
    from ecom.models import Order

    # Get status and search filters
    status_filter = request.GET.get('status', 'all')
    search_query = request.GET.get('q', '').strip()

    # Get all end users
    all_end_users = User.objects.filter(role=User.END_USER).annotate(
        total_orders=Count('orders')
    ).order_by('-date_joined')

    # Apply status filter
    users = all_end_users
    if status_filter == 'active':
        users = users.filter(is_active=True)
    elif status_filter == 'inactive':
        users = users.filter(is_active=False)
    
    # Apply search filter
    if search_query:
        users = users.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(phone_number__icontains=search_query)
        )

    # Calculate stats
    total_end_users = all_end_users.count()
    active_end_users = all_end_users.filter(is_active=True).count()
    inactive_end_users = all_end_users.filter(is_active=False).count()
    total_orders = Order.objects.filter(user__role=User.END_USER).count()
    total_spent = (
        Order.objects.filter(user__role=User.END_USER).aggregate(total=Sum('total_amount'))['total']
        or 0
    )

    context = {
        'page_title': 'End Users',
        'users': users,
        'total_end_users': total_end_users,
        'active_end_users': active_end_users,
        'inactive_end_users': inactive_end_users,
        'total_orders': total_orders,
        'total_spent': total_spent,
        'status_filter': status_filter,
        'search_query': search_query,
    }
    return render(request, 'admin_dashboard/end_users.html', context)


@admin_required
def export_end_users_csv(request):
    """Export end users list to CSV respecting status filter"""
    import csv
    from django.db.models import Count

    status_filter = request.GET.get('status', 'all')
    qs = User.objects.filter(role=User.END_USER).annotate(
        total_orders=Count('orders')
    ).order_by('-date_joined')
    if status_filter == 'active':
        qs = qs.filter(is_active=True)
    elif status_filter == 'inactive':
        qs = qs.filter(is_active=False)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="end_users.csv"'
    writer = csv.writer(response)
    writer.writerow(['ID', 'First Name', 'Last Name', 'Email', 'Phone', 'Role', 'Active', 'Joined', 'Total Orders', 'Unique Code', 'Referral Code', 'Reward Points'])
    for u in qs:
        writer.writerow([
            str(u.id), u.first_name, u.last_name, u.email, u.phone or '', 'end_user',
            'yes' if u.is_active else 'no', u.date_joined.strftime('%Y-%m-%d %H:%M'), int(u.total_orders or 0),
            u.unique_code or '', u.referral_code or '', u.reward_points,
        ])
    return response


@admin_required
def delete_user_admin(request, user_id):
    """Delete a user via AJAX/API endpoint"""
    if request.method == 'POST':
        try:
            user = get_object_or_404(User, id=user_id)
            # Prevent deleting the current admin
            if user.id == request.user.id:
                return JsonResponse({
                    'success': False,
                    'message': 'You cannot delete yourself!'
                }, status=400)
            
            user.delete()
            return JsonResponse({
                'success': True,
                'message': 'User deleted successfully'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=400)
    
    return JsonResponse({'success': False, 'message': 'Invalid request'}, status=405)


@admin_required
def user_detail(request, user_id):
    """User detail page"""
    if request.user.role != User.ADMINISTRATOR or not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('admin_login')
    
    # Handle deletion
    if request.method == 'POST' and request.POST.get('action') == 'delete':
        user = get_object_or_404(User, id=user_id)
        user.delete()
        messages.success(request, 'User deleted successfully!')
        return redirect('admin_customers')
    
    user = get_object_or_404(User, id=user_id)
    
    # Get orders for this user
    from ecom.models import Order, OrderItem, RewardPointLedger
    from django.db.models import Sum
    
    orders = Order.objects.filter(user=user).prefetch_related('items__product').order_by('-created_at')
    point_ledger = RewardPointLedger.objects.filter(user=user).select_related('order')[:20]
    
    # Calculate stats
    total_orders = orders.count()
    total_spent = orders.aggregate(total=Sum('total_amount'))['total'] or 0
    total_items_purchased = OrderItem.objects.filter(order__user=user).aggregate(total=Sum('quantity'))['total'] or 0
    referral_orders_count = Order.objects.filter(referrer=user, payment_status='completed').count()
    unique_referred_buyers = Order.objects.filter(referrer=user, payment_status='completed').values('user').distinct().count()
    
    # Get role display name
    role_display = dict(User.ROLE_CHOICES).get(user.role, 'Unknown')
    
    context = {
        'user': user,
        'orders': orders[:10],  # Recent 10 orders
        'total_orders': total_orders,
        'total_spent': total_spent,
        'total_items_purchased': total_items_purchased,
        'referral_orders_count': referral_orders_count,
        'unique_referred_buyers': unique_referred_buyers,
        'role_display': role_display,
        'point_ledger': point_ledger,
        'page_title': f"{user.first_name} {user.last_name}",
    }
    return render(request, 'admin_dashboard/user_detail.html', context)


# Blog Views
@admin_required
def blog_list(request):
    if request.user.role != User.ADMINISTRATOR or not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('admin_login')
    
    # Get search query
    search_query = request.GET.get('q', '').strip()
    
    base_posts = BlogPost.objects.select_related('category').order_by('-created_at')
    total = base_posts.count()
    published = base_posts.filter(is_published=True).count()
    drafts = base_posts.filter(is_published=False).count()
    status = request.GET.get('status', 'all')

    posts = base_posts
    if status == 'published':
        posts = base_posts.filter(is_published=True)
    elif status == 'drafts':
        posts = base_posts.filter(is_published=False)
    
    # Apply search filter
    if search_query:
        posts = posts.filter(
            Q(title__icontains=search_query) |
            Q(slug__icontains=search_query) |
            Q(content__icontains=search_query) |
            Q(category__name__icontains=search_query)
        )

    categories = BlogCategory.objects.all().order_by('name')
    return render(request, 'admin_dashboard/blog_list.html', {
        'posts': posts,
        'total': total,
        'published': published,
        'drafts': drafts,
        'categories': categories,
        'active_status': status,
        'search_query': search_query,
    })


@admin_required
def blog_add(request):
    if request.user.role != User.ADMINISTRATOR or not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('admin_login')
    if request.method == 'POST':
        form = BlogPostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            # Handle publish action
            if request.POST.get('action') == 'publish':
                post.is_published = True
            post.save()
            messages.success(request, 'Article created successfully!')
            return redirect('admin_blog_edit', post_id=post.id)
        else:
            # Log form errors for debugging
            print("Form errors:", form.errors)
    else:
        form = BlogPostForm()
    return render(request, 'admin_dashboard/blog_edit.html', {
        'form': form,
        'post': None,
        'page_title': 'Add New Article',
    })


@admin_required
def blog_edit(request, post_id):
    if request.user.role != User.ADMINISTRATOR or not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('admin_login')
    post = get_object_or_404(BlogPost, id=post_id)
    if request.method == 'POST':
        form = BlogPostForm(request.POST, request.FILES, instance=post)
        if form.is_valid():
            post = form.save(commit=False)
            # Handle publish action
            if request.POST.get('action') == 'publish':
                post.is_published = True
            post.save()
            messages.success(request, 'Article updated successfully!')
            return redirect('admin_blog_edit', post_id=post.id)
        else:
            # Log form errors for debugging
            print("Form errors:", form.errors)
    else:
        form = BlogPostForm(instance=post)
    return render(request, 'admin_dashboard/blog_edit.html', {
        'form': form,
        'post': post,
        'page_title': post.title,
    })


@admin_required
def blog_delete(request, post_id):
    if request.method == 'POST':
        post = get_object_or_404(BlogPost, id=post_id)
        post.delete()
        messages.success(request, 'Article deleted successfully!')
        return redirect('admin_blog_list')
    return JsonResponse({'success': False, 'message': 'Invalid request'}, status=400)


@admin_required
def blog_toggle_publish(request, post_id):
    post = get_object_or_404(BlogPost, id=post_id)
    post.is_published = not post.is_published
    post.save()
    messages.success(request, 'Publish state updated.')
    return redirect('admin_blog_list')


# Wholesaler Detail View
@admin_required
def wholesaler_detail(request, wholesaler_id):
    if request.user.role != User.ADMINISTRATOR or not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('admin_login')
    
    # Handle deletion
    if request.method == 'POST' and request.POST.get('action') == 'delete':
        wholesaler = get_object_or_404(User, id=wholesaler_id, role=User.WHOLESALER)
        wholesaler.delete()
        messages.success(request, 'Wholesaler deleted successfully!')
        return redirect('admin_wholesalers')
    
    wholesaler = get_object_or_404(User, id=wholesaler_id, role=User.WHOLESALER)
    
    # Get orders for this wholesaler
    from ecom.models import Order, OrderItem
    from django.db.models import Sum, Count
    
    orders = Order.objects.filter(user=wholesaler).prefetch_related('items__product').order_by('-created_at')
    
    # Calculate stats
    total_orders = orders.count()
    total_revenue = orders.aggregate(total=Sum('total_amount'))['total'] or 0
    total_items_sold = OrderItem.objects.filter(order__user=wholesaler).aggregate(total=Sum('quantity'))['total'] or 0
    
    context = {
        'wholesaler': wholesaler,
        'orders': orders[:10],  # Recent 10 orders
        'total_orders': total_orders,
        'total_revenue': total_revenue,
        'total_items_sold': total_items_sold,
        'page_title': f"{wholesaler.first_name} {wholesaler.last_name}",
    }
    return render(request, 'admin_dashboard/wholesaler_detail.html', context)


# Distributor/Retailer Detail View
@admin_required
def retailer_detail(request, retailer_id):
    if request.user.role != User.ADMINISTRATOR or not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('admin_login')
    
    # Handle deletion
    if request.method == 'POST' and request.POST.get('action') == 'delete':
        retailer = get_object_or_404(User, id=retailer_id, role=User.RETAILER)
        retailer.delete()
        messages.success(request, 'Retailer deleted successfully!')
        return redirect('admin_retailers')
    
    retailer = get_object_or_404(User, id=retailer_id, role=User.RETAILER)
    
    # Get orders for this retailer
    from ecom.models import Order, OrderItem
    from django.db.models import Sum, Count
    
    orders = Order.objects.filter(user=retailer).prefetch_related('items__product').order_by('-created_at')
    
    # Calculate stats
    total_orders = orders.count()
    total_revenue = orders.aggregate(total=Sum('total_amount'))['total'] or 0
    total_items_sold = OrderItem.objects.filter(order__user=retailer).aggregate(total=Sum('quantity'))['total'] or 0
    
    context = {
        'retailer': retailer,
        'orders': orders[:10],  # Recent 10 orders
        'total_orders': total_orders,
        'total_revenue': total_revenue,
        'total_items_sold': total_items_sold,
        'page_title': f"{retailer.first_name} {retailer.last_name}",
    }
    return render(request, 'admin_dashboard/retailer_detail.html', context)


# Hospital Detail View
@admin_required
def hospital_detail(request, hospital_id):
    if request.user.role != User.ADMINISTRATOR or not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('admin_login')
    
    # Handle deletion
    if request.method == 'POST' and request.POST.get('action') == 'delete':
        hospital = get_object_or_404(User, id=hospital_id, role=User.HOSPITAL)
        hospital.delete()
        messages.success(request, 'Hospital deleted successfully!')
        return redirect('admin_hospitals')
    
    hospital = get_object_or_404(User, id=hospital_id, role=User.HOSPITAL)
    
    # Get orders for this hospital
    from ecom.models import Order, OrderItem
    from django.db.models import Sum, Count
    
    orders = Order.objects.filter(user=hospital).prefetch_related('items__product').order_by('-created_at')
    
    # Calculate stats
    total_orders = orders.count()
    total_revenue = orders.aggregate(total=Sum('total_amount'))['total'] or 0
    total_items_ordered = OrderItem.objects.filter(order__user=hospital).aggregate(total=Sum('quantity'))['total'] or 0
    
    context = {
        'hospital': hospital,
        'orders': orders[:10],  # Recent 10 orders
        'total_orders': total_orders,
        'total_revenue': total_revenue,
        'total_items_ordered': total_items_ordered,
        'page_title': f"{hospital.first_name} {hospital.last_name}",
    }
    return render(request, 'admin_dashboard/hospital_detail.html', context)


# Pharmacy Detail View
@admin_required
def pharmacy_detail(request, pharmacy_id):
    if request.user.role != User.ADMINISTRATOR or not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('admin_login')
    
    # Handle deletion
    if request.method == 'POST' and request.POST.get('action') == 'delete':
        pharmacy = get_object_or_404(User, id=pharmacy_id, role=User.PHARMACY)
        pharmacy.delete()
        messages.success(request, 'Pharmacy deleted successfully!')
        return redirect('admin_pharmacies')
    
    pharmacy = get_object_or_404(User, id=pharmacy_id, role=User.PHARMACY)
    
    # Get orders for this pharmacy
    from ecom.models import Order, OrderItem
    from django.db.models import Sum, Count
    
    orders = Order.objects.filter(user=pharmacy).prefetch_related('items__product').order_by('-created_at')
    
    # Calculate stats
    total_orders = orders.count()
    total_revenue = orders.aggregate(total=Sum('total_amount'))['total'] or 0
    total_items_ordered = OrderItem.objects.filter(order__user=pharmacy).aggregate(total=Sum('quantity'))['total'] or 0
    
    context = {
        'pharmacy': pharmacy,
        'orders': orders[:10],  # Recent 10 orders
        'total_orders': total_orders,
        'total_revenue': total_revenue,
        'total_items_ordered': total_items_ordered,
        'page_title': f"{pharmacy.first_name} {pharmacy.last_name}",
    }
    return render(request, 'admin_dashboard/pharmacy_detail.html', context)


@admin_required
def tickets_page(request):
    """Tickets management page similar to orders"""
    from users.models import Ticket
    from django.db.models import Count, Q
    
    if request.user.role != User.ADMINISTRATOR or not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('admin_login')
    
    # Get filter parameters
    status_filter = request.GET.get('status', 'all')
    priority_filter = request.GET.get('priority', 'all')
    
    # Get all tickets
    tickets = Ticket.objects.select_related('user', 'assigned_to').order_by('-created_at')
    
    # Apply status filter
    if status_filter == 'open':
        tickets = tickets.filter(status='open')
    elif status_filter == 'in_progress':
        tickets = tickets.filter(status='in_progress')
    elif status_filter == 'resolved':
        tickets = tickets.filter(status='resolved')
    elif status_filter == 'closed':
        tickets = tickets.filter(status='closed')
    
    # Apply priority filter
    if priority_filter in ['low', 'medium', 'high', 'urgent']:
        tickets = tickets.filter(priority=priority_filter)
    
    # Calculate statistics
    total_tickets = Ticket.objects.count()
    open_tickets = Ticket.objects.filter(status='open').count()
    in_progress_tickets = Ticket.objects.filter(status='in_progress').count()
    resolved_tickets = Ticket.objects.filter(status='resolved').count()
    closed_tickets = Ticket.objects.filter(status='closed').count()
    urgent_tickets = Ticket.objects.filter(priority='urgent', status__in=['open', 'in_progress']).count()
    
    context = {
        'page_title': 'Support Tickets',
        'tickets': tickets,
        'total_tickets': total_tickets,
        'open_tickets': open_tickets,
        'in_progress_tickets': in_progress_tickets,
        'resolved_tickets': resolved_tickets,
        'closed_tickets': closed_tickets,
        'urgent_tickets': urgent_tickets,
        'status_filter': status_filter,
        'priority_filter': priority_filter,
    }
    return render(request, 'admin_dashboard/tickets.html', context)


@admin_required
def ticket_detail(request, ticket_id):
    """Detailed view for a single ticket with admin response"""
    from users.models import Ticket
    from django.utils import timezone
    
    if request.user.role != User.ADMINISTRATOR or not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('admin_login')
    
    ticket = get_object_or_404(Ticket.objects.select_related('user', 'assigned_to'), id=ticket_id)
    
    # Handle status and response updates
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'update_status':
            new_status = request.POST.get('status')
            if new_status in [choice[0] for choice in Ticket.STATUS_CHOICES]:
                ticket.status = new_status
                if new_status in ['resolved', 'closed'] and not ticket.resolved_at:
                    ticket.resolved_at = timezone.now()
                ticket.save(update_fields=['status', 'resolved_at', 'updated_at'])
                messages.success(request, f'Ticket status updated to {new_status.replace("_", " ").title()}')
            else:
                messages.error(request, 'Invalid status.')
        
        elif action == 'add_response':
            admin_response = request.POST.get('admin_response', '').strip()
            if admin_response:
                ticket.admin_response = admin_response
                ticket.assigned_to = request.user
                if ticket.status == 'open':
                    ticket.status = 'in_progress'
                ticket.save(update_fields=['admin_response', 'assigned_to', 'status', 'updated_at'])
                messages.success(request, 'Response added successfully')
                
                # Send email notification to user
                from django.core.mail import send_mail
                from django.template.loader import render_to_string
                from django.conf import settings
                try:
                    subject = f"Update on Your Support Ticket #{str(ticket.id)[:8]}"
                    html_message = render_to_string('emails/ticket_response.html', {
                        'ticket': ticket,
                        'user': ticket.user,
                    })
                    send_mail(
                        subject,
                        f'Your ticket has been updated. Please check your dashboard for details.',
                        settings.DEFAULT_FROM_EMAIL,
                        [ticket.contact_email or ticket.user.email],
                        html_message=html_message,
                        fail_silently=True,
                    )
                except Exception as e:
                    print(f"Failed to send ticket response email: {e}")
            else:
                messages.error(request, 'Response cannot be empty.')
        
        elif action == 'assign':
            admin_id = request.POST.get('admin_id')
            if admin_id:
                try:
                    admin_user = User.objects.get(id=admin_id, role=User.ADMINISTRATOR)
                    ticket.assigned_to = admin_user
                    ticket.save(update_fields=['assigned_to', 'updated_at'])
                    messages.success(request, f'Ticket assigned to {admin_user.get_full_name() or admin_user.email}')
                except User.DoesNotExist:
                    messages.error(request, 'Invalid administrator.')
        
        return redirect('admin_ticket_detail', ticket_id=ticket.id)
    
    # Get all administrators for assignment dropdown
    administrators = User.objects.filter(role=User.ADMINISTRATOR, is_staff=True).exclude(id=ticket.assigned_to.id if ticket.assigned_to else None)
    
    context = {
        'ticket': ticket,
        'administrators': administrators,
        'page_title': f'Ticket #{str(ticket.id)[:8]}',
    }
    return render(request, 'admin_dashboard/ticket_detail.html', context)


@admin_required
def delete_notification(request, notification_type, notification_id):
    """Delete a notification (order or ticket)"""
    if request.method == 'DELETE':
        try:
            # Store dismissed notifications in session
            if 'dismissed_notifications' not in request.session:
                request.session['dismissed_notifications'] = []
            
            notification_key = f"{notification_type}-{str(notification_id)}"
            if notification_key not in request.session['dismissed_notifications']:
                request.session['dismissed_notifications'].append(notification_key)
                request.session.modified = True
            
            return JsonResponse({'success': True, 'message': 'Notification dismissed'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=500)
    return JsonResponse({'success': False, 'message': 'Invalid request'}, status=400)


@admin_required
def kyc_submissions(request):
    """List all KYC submissions for admin review"""
    status_filter = request.GET.get('status', '')
    search_query = request.GET.get('search', '')
    
    kyc_qs = KYCSubmission.objects.select_related('user', 'verified_by').order_by('-created_at').distinct()
    
    # Filter by status
    if status_filter:
        kyc_qs = kyc_qs.filter(status=status_filter)
    
    # Search by user email or business name
    if search_query:
        kyc_qs = kyc_qs.filter(
            Q(user__email__icontains=search_query) |
            Q(business_name__icontains=search_query)
        )
    
    # Pagination
    page = request.GET.get('page', 1)
    per_page = 12
    start = (int(page) - 1) * per_page
    end = start + per_page
    
    kyc_list = kyc_qs[start:end]
    total = kyc_qs.count()
    has_next = end < total
    
    context = {
        'kyc_list': kyc_list,
        'total': total,
        'page': page,
        'has_next': has_next,
        'status_filter': status_filter,
        'search_query': search_query,
        'page_title': 'KYC Submissions',
        'status_choices': KYCSubmission.STATUS_CHOICES,
    }
    return render(request, 'admin_dashboard/kyc_submissions.html', context)


@admin_required
def kyc_detail(request, submission_id):
    """View and verify KYC submission detail"""
    kyc_submission = get_object_or_404(KYCSubmission, id=submission_id)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'approve':
            kyc_submission.approve(request.user)
            try:
                async_result = send_kyc_status_update_email_task.delay(str(kyc_submission.id))
                kyc_submission.log_event(
                    event_type=KYCSubmissionAuditLog.EVENT_EMAIL,
                    actor=request.user,
                    email_status=KYCSubmissionAuditLog.EMAIL_QUEUED,
                    message='KYC status email queued.',
                    metadata={'task_id': async_result.id},
                )
            except Exception:
                # Fallback to synchronous send if broker is unavailable.
                sent = send_kyc_approved_email(kyc_submission.user)
                kyc_submission.log_event(
                    event_type=KYCSubmissionAuditLog.EVENT_EMAIL,
                    actor=request.user,
                    email_status=KYCSubmissionAuditLog.EMAIL_SENT if sent else KYCSubmissionAuditLog.EMAIL_FAILED,
                    message='KYC status email sent synchronously due to queue unavailability.' if sent else 'KYC status email failed during synchronous fallback.',
                )
            messages.success(request, f'KYC approved for {kyc_submission.user.email}')
            return redirect('kyc-submissions')
        
        elif action == 'reject':
            rejection_reason = request.POST.get('rejection_reason', '').strip()
            if not rejection_reason:
                messages.error(request, 'Rejection reason is required.')
            else:
                kyc_submission.reject(request.user, rejection_reason)
                try:
                    async_result = send_kyc_status_update_email_task.delay(str(kyc_submission.id))
                    kyc_submission.log_event(
                        event_type=KYCSubmissionAuditLog.EVENT_EMAIL,
                        actor=request.user,
                        email_status=KYCSubmissionAuditLog.EMAIL_QUEUED,
                        message='KYC status email queued.',
                        metadata={'task_id': async_result.id},
                    )
                except Exception:
                    # Fallback to synchronous send if broker is unavailable.
                    sent = send_kyc_rejected_email(kyc_submission.user, rejection_reason)
                    kyc_submission.log_event(
                        event_type=KYCSubmissionAuditLog.EVENT_EMAIL,
                        actor=request.user,
                        email_status=KYCSubmissionAuditLog.EMAIL_SENT if sent else KYCSubmissionAuditLog.EMAIL_FAILED,
                        message='KYC status email sent synchronously due to queue unavailability.' if sent else 'KYC status email failed during synchronous fallback.',
                    )
                messages.success(request, f'KYC rejected for {kyc_submission.user.email}')
                return redirect('kyc-submissions')
    
    audit_logs = kyc_submission.audit_logs.select_related('actor')[:30]

    context = {
        'kyc_submission': kyc_submission,
        'user': kyc_submission.user,
        'audit_logs': audit_logs,
        'page_title': f'KYC - {kyc_submission.user.email}',
    }
    return render(request, 'admin_dashboard/kyc_detail.html', context)
