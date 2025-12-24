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
                    AdminPasswordChangeForm)
from users.models import User
from django.core.mail import send_mail
from django.conf import settings
from django.http import JsonResponse
from .models import Product, Category, ProductImage, BlogPost, BlogCategory
from django.db.models import Count
from django.db.models.functions import TruncMonth
from datetime import datetime
from decimal import Decimal
import json
import secrets


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
    
    context = {
        'user': request.user,
        'total_orders': total_orders,
        'pending_orders': pending_orders,
        'total_users': total_users,
        'total_revenue': total_revenue,
        'top_products': top_products_data,
        'monthly_sales_2025': json.dumps(monthly_sales_2025),
        'monthly_sales_2024': json.dumps(monthly_sales_2024),
        'daily_revenue': json.dumps(daily_revenue),
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
    
    # Get filter parameter
    status_filter = request.GET.get('status', 'all')
    
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
    writer.writerow(['ID', 'First Name', 'Last Name', 'Email', 'Phone', 'Role', 'Active', 'Joined', 'Total Orders', 'Total Spent'])
    for u in qs:
        writer.writerow([
            str(u.id), u.first_name, u.last_name, u.email, u.phone or '', 'wholesaler',
            'yes' if u.is_active else 'no', u.date_joined.strftime('%Y-%m-%d %H:%M'),
            int(u.total_orders or 0), float(u.total_spent or 0),
        ])
    return response


@admin_required
def retailers_page(request):
    """Retailers management page"""
    from ecom.models import Order
    from django.db.models import Sum, Count, Q
    
    # Get filter parameter
    status_filter = request.GET.get('status', 'all')
    
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
    writer.writerow(['ID', 'First Name', 'Last Name', 'Email', 'Phone', 'Role', 'Active', 'Joined', 'Total Orders', 'Total Spent'])
    for u in qs:
        writer.writerow([
            str(u.id), u.first_name, u.last_name, u.email, u.phone or '', 'retailer',
            'yes' if u.is_active else 'no', u.date_joined.strftime('%Y-%m-%d %H:%M'),
            int(u.total_orders or 0), float(u.total_spent or 0),
        ])
    return response


@admin_required
def hospitals_page(request):
    """Hospitals management page"""
    from ecom.models import Order
    from django.db.models import Sum, Count, Q
    
    # Get filter parameter
    status_filter = request.GET.get('status', 'all')
    
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
    writer.writerow(['ID', 'First Name', 'Last Name', 'Email', 'Phone', 'Role', 'Active', 'Joined', 'Total Orders', 'Total Spent'])
    for u in qs:
        writer.writerow([
            str(u.id), u.first_name, u.last_name, u.email, u.phone or '', 'hospital',
            'yes' if u.is_active else 'no', u.date_joined.strftime('%Y-%m-%d %H:%M'),
            int(u.total_orders or 0), float(u.total_spent or 0),
        ])
    return response


@admin_required
def pharmacy_page(request):
    """Pharmacies management page"""
    from ecom.models import Order
    from django.db.models import Sum, Count, Q
    
    # Get filter parameter
    status_filter = request.GET.get('status', 'all')
    
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
    writer.writerow(['ID', 'First Name', 'Last Name', 'Email', 'Phone', 'Role', 'Active', 'Joined', 'Total Orders', 'Total Spent'])
    for u in qs:
        writer.writerow([
            str(u.id), u.first_name, u.last_name, u.email, u.phone or '', 'pharmacy',
            'yes' if u.is_active else 'no', u.date_joined.strftime('%Y-%m-%d %H:%M'),
            int(u.total_orders or 0), float(u.total_spent or 0),
        ])
    return response





# ...existing code...

@admin_required
def products_page(request):
    from django.db.models import DecimalField, F, IntegerField, Sum, Value
    from django.db.models.functions import Coalesce
    from django.utils import timezone
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
        .order_by('-created_at')
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
            uploaded_images = request.FILES.getlist("images")
            
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
            new_images = request.FILES.getlist('new_images')
            
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
                'message': f'{len(new_images)} image(s) added',
                'images': added_images
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=400)
    return JsonResponse({'success': False, 'message': 'Invalid request'}, status=405)


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
    categories = Category.objects.all().order_by('-created_at')
    return render(request, 'admin_dashboard/categories.html', {'categories': categories})

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
    """Orders management page"""
    from ecom.models import Order
    from django.db.models import Count, Q
    
    # Get filter parameter
    status_filter = request.GET.get('status', 'all')
    
    # Get all orders
    orders = Order.objects.select_related('user').prefetch_related('items__product').all()
    
    # Apply status filter
    if status_filter == 'processing':
        orders = orders.filter(Q(status='processing') | Q(status='shipped'))
    elif status_filter == 'completed':
        orders = orders.filter(status='delivered')
    elif status_filter == 'cancelled':
        orders = orders.filter(status='cancelled')
    
    # Calculate statistics
    total_orders = Order.objects.count()
    cancelled_orders = Order.objects.filter(status='cancelled').count()
    active_orders = Order.objects.filter(Q(status='pending') | Q(status='processing') | Q(status='shipped')).count()
    completed_orders = Order.objects.filter(status='delivered').count()
    processing_orders = Order.objects.filter(Q(status='processing') | Q(status='shipped')).count()
    
    context = {
        'page_title': 'Orders',
        'orders': orders,
        'total_orders': total_orders,
        'cancelled_orders': cancelled_orders,
        'active_orders': active_orders,
        'completed_orders': completed_orders,
        'processing_orders': processing_orders,
        'status_filter': status_filter,
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
    """Tracking screen with status filters and inline status updates"""
    from ecom.models import Order

    if request.user.role != User.ADMINISTRATOR or not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('admin_login')

    status_param = request.GET.get('status', 'all')
    status_choices = [choice[0] for choice in Order.STATUS_CHOICES]

    if request.method == 'POST':
        posted_order_id = request.POST.get('order_id')
        new_status = request.POST.get('status')
        if not posted_order_id or new_status not in status_choices:
            messages.error(request, 'Invalid status update request.')
            return redirect(request.path)
        order = get_object_or_404(Order, id=posted_order_id)
        order.status = new_status
        order.save(update_fields=['status', 'updated_at'])
        messages.success(request, f'Order status updated to {new_status.title()}')

        redirect_url = reverse(
            'admin_order_tracking',
            kwargs={'order_id': order_id},
        ) if order_id else reverse('admin_orders_tracking')
        if status_param:
            redirect_url += f'?status={status_param}'
        return redirect(redirect_url)

    orders = Order.objects.select_related('user').prefetch_related('items__product__thumbnail').order_by('-created_at')

    if order_id:
        orders = orders.filter(id=order_id)
    else:
        if status_param == 'in_progress':
            orders = orders.filter(status__in=['pending', 'processing', 'shipped'])
        elif status_param == 'completed':
            orders = orders.filter(status='delivered')
        elif status_param == 'cancelled':
            orders = orders.filter(status='cancelled')

    total_orders = orders.count()
    in_progress_count = orders.filter(status__in=['pending', 'processing', 'shipped']).count()
    completed_count = orders.filter(status='delivered').count()

    progress_map = {
        'pending': 1,
        'processing': 2,
        'shipped': 3,
        'delivered': 4,
        'cancelled': 0,
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
        'status_choices': status_choices,
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
    """Analytics dashboard page"""
    
    # Get current year
    current_year = datetime.now().year
    
    # Calculate monthly user sign-ups for current year
    monthly_data = User.objects.filter(
        date_joined__year=current_year
    ).annotate(
        month=TruncMonth('date_joined')
    ).values('month').annotate(
        count=Count('id')
    ).order_by('month')
    
    # Create array with 12 months (Jan-Dec), default 0
    monthly_signups = [0] * 12
    for data in monthly_data:
        month_index = data['month'].month - 1  # 0-indexed
        monthly_signups[month_index] = data['count']
    
    # Total users count
    total_users = User.objects.count()
    
    context = {
        'page_title': 'Analytics',
        'monthly_signups': json.dumps(monthly_signups),
        'current_year': current_year,
        'total_users': total_users,
    }
    return render(request, 'admin_dashboard/analytics.html', context)

@admin_required
@admin_required
def customers_page(request):
    """Users management page - shows all users with their roles"""
    from django.db.models import Count
    
    # Get filter parameter
    role_filter = request.GET.get('role', 'all')
    
    # Get all users
    users = User.objects.all().annotate(
        total_orders=Count('orders')
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
    }
    return render(request, 'admin_dashboard/customers.html', context)


@admin_required
def end_users_page(request):
    """End Users management page - lists regular customers (END_USER) only"""
    from django.db.models import Count, Sum
    from ecom.models import Order

    # Get status filter
    status_filter = request.GET.get('status', 'all')

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
    writer.writerow(['ID', 'First Name', 'Last Name', 'Email', 'Phone', 'Role', 'Active', 'Joined', 'Total Orders'])
    for u in qs:
        writer.writerow([
            str(u.id), u.first_name, u.last_name, u.email, u.phone or '', 'end_user',
            'yes' if u.is_active else 'no', u.date_joined.strftime('%Y-%m-%d %H:%M'), int(u.total_orders or 0)
        ])
    return response


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
    from ecom.models import Order, OrderItem
    from django.db.models import Sum
    
    orders = Order.objects.filter(user=user).prefetch_related('items__product').order_by('-created_at')
    
    # Calculate stats
    total_orders = orders.count()
    total_spent = orders.aggregate(total=Sum('total_amount'))['total'] or 0
    total_items_purchased = OrderItem.objects.filter(order__user=user).aggregate(total=Sum('quantity'))['total'] or 0
    
    # Get role display name
    role_display = dict(User.ROLE_CHOICES).get(user.role, 'Unknown')
    
    context = {
        'user': user,
        'orders': orders[:10],  # Recent 10 orders
        'total_orders': total_orders,
        'total_spent': total_spent,
        'total_items_purchased': total_items_purchased,
        'role_display': role_display,
        'page_title': f"{user.first_name} {user.last_name}",
    }
    return render(request, 'admin_dashboard/user_detail.html', context)


# Blog Views
@admin_required
def blog_list(request):
    if request.user.role != User.ADMINISTRATOR or not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('admin_login')
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

    categories = BlogCategory.objects.all().order_by('name')
    return render(request, 'admin_dashboard/blog_list.html', {
        'posts': posts,
        'total': total,
        'published': published,
        'drafts': drafts,
        'categories': categories,
        'active_status': status,
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