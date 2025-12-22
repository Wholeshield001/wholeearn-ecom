from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages, auth
from django.contrib.auth import authenticate, update_session_auth_hash
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.db.models import Sum
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from ecom.models import Cart, CartItem
from .forms import (
    SignUpForm,
    VerifyOTPForm,
    LoginForm,
    ProfileForm,
    PasswordChangeForm,
    PasswordResetRequestForm,
    PasswordResetVerifyForm,
    PasswordResetSetForm,
    TicketForm,
)
from .emails import send_verification_otp_email, send_welcome_email, send_password_reset_email

User = get_user_model()


@require_http_methods(["GET", "POST"])
def signup(request):
    """Handle user registration"""
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            try:
                user = form.save(commit=False)
                user.save()
                
                # Send verification OTP email
                send_verification_otp_email(user)
                
                # Store user email in session for OTP verification
                request.session['pending_verification_email'] = user.email
                request.session['verification_attempts'] = 0
                
                messages.success(
                    request,
                    'Account created! Check your email for the verification code.'
                )
                return redirect('verify-otp')
            except IntegrityError:
                messages.error(request, 'An error occurred. Please try again.')
                form = SignUpForm()
    else:
        form = SignUpForm()
    
    return render(request, 'users/signup.html', {'form': form})


@require_http_methods(["GET", "POST"])
def verify_otp(request):
    """Handle OTP verification"""
    email = request.session.get('pending_verification_email')
    
    # Redirect if no pending verification
    if not email:
        messages.warning(request, 'No pending verification. Please sign up first.')
        return redirect('signup')
    
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        messages.error(request, 'User not found. Please sign up again.')
        del request.session['pending_verification_email']
        return redirect('signup')
    
    # Check if already verified
    if user.email_verified:
        messages.info(request, 'Your email is already verified. Please log in.')
        del request.session['pending_verification_email']
        return redirect('login')
    
    if request.method == 'POST':
        form = VerifyOTPForm(request.POST)
        if form.is_valid():
            otp = form.cleaned_data['otp']
            
            if user.verify_email_otp(otp):
                # Send welcome email
                send_welcome_email(user)
                
                # Clean up session
                del request.session['pending_verification_email']
                if 'verification_attempts' in request.session:
                    del request.session['verification_attempts']
                
                messages.success(
                    request,
                    'Email verified successfully! You can now log in.'
                )
                return redirect('login')
            else:
                # Increment failed attempts
                attempts = request.session.get('verification_attempts', 0) + 1
                request.session['verification_attempts'] = attempts
                
                # Check if OTP is expired
                from django.utils import timezone
                time_diff = timezone.now() - user.verification_otp_created_at
                if time_diff.total_seconds() > 900:
                    user.clear_verification_otp()
                    messages.error(
                        request,
                        'OTP has expired. Please sign up again.'
                    )
                    del request.session['pending_verification_email']
                    return redirect('signup')
                
                # Limit attempts
                if attempts >= 3:
                    user.clear_verification_otp()
                    messages.error(
                        request,
                        'Too many failed attempts. Please sign up again.'
                    )
                    del request.session['pending_verification_email']
                    return redirect('signup')
                
                messages.error(
                    request,
                    f'Invalid OTP. {3 - attempts} attempts remaining.'
                )
    else:
        form = VerifyOTPForm()
    
    context = {
        'form': form,
        'email': email,
    }
    return render(request, 'users/verify_otp.html', context)


@require_http_methods(["POST"])
def resend_otp(request):
    """Resend OTP to email"""
    email = request.session.get('pending_verification_email')
    
    if not email:
        messages.warning(request, 'No pending verification.')
        return redirect('signup')
    
    try:
        user = User.objects.get(email=email)
        send_verification_otp_email(user)
        request.session['verification_attempts'] = 0
        messages.success(request, 'Verification code sent! Check your email.')
    except User.DoesNotExist:
        messages.error(request, 'User not found.')
        del request.session['pending_verification_email']
    
    return redirect('verify-otp')


@require_http_methods(["GET", "POST"])
def login(request):
    """Handle user login"""
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            remember_me = form.cleaned_data['remember_me']
            
            try:
                user = User.objects.get(email=email)
                user = authenticate(request, username=email, password=password)
                
                if user is not None:
                    auth.login(request, user)
                    
                    if not remember_me:
                        request.session.set_expiry(0)  # Session expires when browser closes
                    else:
                        request.session.set_expiry(1209600)  # 2 weeks
                    
                    messages.success(request, f'Welcome back, {user.first_name}!')
                    
                    # Redirect to dashboard or home based on user role
                    if user.role == 'administrator':
                        return redirect('admin-dashboard')
                    else:
                        return redirect('home')
            except User.DoesNotExist:
                messages.error(request, 'Invalid email or password.')
    else:
        form = LoginForm()
    
    return render(request, 'users/login.html', {'form': form})


@require_http_methods(["GET"])
def logout(request):
    """Handle user logout"""
    auth.logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('home')


@login_required(login_url='login')
@require_http_methods(["GET"])
def dashboard(request):
    """User dashboard with order metrics and recent orders."""
    from ecom.models import Order
    from django.db.models import Sum, Q
    
    total_users = User.objects.count()
    
    # Get user's orders
    user_orders = Order.objects.filter(user=request.user)
    total_orders = user_orders.count()
    pending_orders = user_orders.filter(status='pending').count()
    total_revenue = user_orders.filter(payment_status='completed').aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    
    # Get recent order items (max 10)
    recent_orders = user_orders.prefetch_related('items').order_by('-created_at')[:5]
    items = []
    for order in recent_orders:
        for item in order.items.all():
            items.append({
                'product_name': item.product_name,
                'product_sku': item.product_sku,
                'quantity': item.quantity,
                'price': item.price,
                'date': order.created_at,
            })
            if len(items) >= 10:
                break
        if len(items) >= 10:
            break

    context = {
        'total_users': total_users,
        'total_orders': total_orders,
        'pending_orders': pending_orders,
        'total_revenue': total_revenue,
        'items': items,
    }
    return render(request, 'users/dashboard.html', context)


@login_required(login_url='login')
@require_http_methods(["GET", "POST"])
def profile(request):
    """Allow user to view and update profile details or change password."""
    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        
        if form_type == 'profile':
            # Handle profile update
            form = ProfileForm(request.POST, instance=request.user)
            if form.is_valid():
                form.save()
                messages.success(request, 'Profile updated successfully!')
                return redirect('profile')
            else:
                messages.error(request, 'Please correct the errors in the contact information form.')
        
        elif form_type == 'password':
            # Handle password change
            current_password = request.POST.get('current_password')
            new_password = request.POST.get('new_password')
            new_password_confirm = request.POST.get('new_password_confirm')
            
            if not request.user.check_password(current_password):
                messages.error(request, 'Current password is incorrect.')
            elif new_password != new_password_confirm:
                messages.error(request, 'New passwords do not match.')
            elif len(new_password) < 8:
                messages.error(request, 'New password must be at least 8 characters long.')
            else:
                try:
                    validate_password(new_password, request.user)
                    request.user.set_password(new_password)
                    request.user.save()
                    update_session_auth_hash(request, request.user)
                    messages.success(request, 'Password changed successfully!')
                    return redirect('profile')
                except ValidationError as e:
                    messages.error(request, ' '.join(e.messages))

    return render(request, 'users/profile.html')


@login_required(login_url='login')
@require_http_methods(["GET", "POST"])
def change_password(request):
    """Allow user to change password after providing current password."""
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            new_pwd = form.cleaned_data['new_password']
            request.user.set_password(new_pwd)
            request.user.save()
            update_session_auth_hash(request, request.user)
            messages.success(request, 'Password changed successfully.')
            return redirect('profile')
    else:
        form = PasswordChangeForm(request.user)

    return render(request, 'users/change_password.html', {'form': form})


@require_http_methods(["GET", "POST"])
def password_reset_request(request):
    """Start password reset by sending OTP to email."""
    if request.method == 'POST':
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            try:
                user = User.objects.get(email=email)
                send_password_reset_email(user)
                request.session['reset_email'] = email
                messages.success(request, 'We sent a verification code to your email.')
                return redirect('password-reset-verify')
            except User.DoesNotExist:
                messages.error(request, 'If that email exists, we have sent a reset code.')
                return redirect('password-reset-request')
    else:
        form = PasswordResetRequestForm()

    return render(request, 'users/password_reset_request.html', {'form': form})


@require_http_methods(["GET", "POST"])
def password_reset_verify(request):
    """Verify the OTP sent for password reset."""
    email = request.session.get('reset_email')
    if not email:
        messages.warning(request, 'Start password reset first.')
        return redirect('password-reset-request')

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        messages.error(request, 'User not found.')
        return redirect('password-reset-request')

    if request.method == 'POST':
        form = PasswordResetVerifyForm(request.POST)
        if form.is_valid():
            otp = form.cleaned_data['otp']
            if user.verify_reset_otp(otp):
                request.session['reset_token'] = user.reset_token
                messages.success(request, 'Code verified. Set a new password.')
                return redirect('password-reset-new')
            else:
                messages.error(request, 'Invalid or expired code. Please request again.')
                return redirect('password-reset-request')
    else:
        form = PasswordResetVerifyForm()

    return render(request, 'users/password_reset_verify.html', {'form': form, 'email': email})


@require_http_methods(["GET", "POST"])
def password_reset_new(request):
    """Set a new password after OTP verification."""
    email = request.session.get('reset_email')
    token = request.session.get('reset_token')
    if not email or not token:
        messages.warning(request, 'Start password reset first.')
        return redirect('password-reset-request')

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        messages.error(request, 'User not found.')
        return redirect('password-reset-request')

    if user.reset_token != token:
        messages.error(request, 'Invalid reset session. Please request again.')
        return redirect('password-reset-request')

    if request.method == 'POST':
        form = PasswordResetSetForm(user, request.POST)
        if form.is_valid():
            new_pwd = form.cleaned_data['new_password']
            user.set_password(new_pwd)
            user.clear_reset_data()
            user.save()
            request.session.pop('reset_email', None)
            request.session.pop('reset_token', None)
            messages.success(request, 'Password reset successful. You can now log in.')
            return redirect('login')
    else:
        form = PasswordResetSetForm(user)

    return render(request, 'users/password_reset_new.html', {'form': form, 'email': email})

@login_required(login_url='login')
@require_http_methods(["GET", "POST"])
def create_ticket(request):
    """Create a support ticket/complaint"""
    if request.method == 'POST':
        form = TicketForm(request.POST)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.user = request.user
            # Auto-populate contact info from user
            ticket.contact_name = request.user.get_full_name() or request.user.email
            ticket.contact_email = request.user.email
            ticket.save()
            
            # Send confirmation email
            from django.core.mail import send_mail
            from django.template.loader import render_to_string
            from django.conf import settings
            try:
                subject = f"Support Ticket Received - #{str(ticket.id)[:8]}"
                html_message = render_to_string('emails/ticket_confirmation.html', {
                    'ticket': ticket,
                    'name': ticket.contact_name,
                })
                send_mail(
                    subject,
                    f'Thank you for contacting us. Your ticket #{str(ticket.id)[:8]} has been received and will be attended to shortly.',
                    settings.DEFAULT_FROM_EMAIL,
                    [request.user.email],
                    html_message=html_message,
                    fail_silently=True,
                )
            except Exception as e:
                print(f"Failed to send ticket confirmation email: {e}")
            
            messages.success(request, f'Ticket #{str(ticket.id)[:8]} created successfully! We will respond soon.')
            return redirect('user-dashboard')
    else:
        form = TicketForm()
    
    return render(request, 'users/create_ticket.html', {'form': form})


@login_required(login_url='login')
@require_http_methods(["GET"])
def order_history(request):
    """Show user's order history with summary metrics"""
    from ecom.models import Order

    orders = Order.objects.filter(user=request.user).prefetch_related('items').order_by('-created_at')
    total_orders = orders.count()
    pending_orders = orders.filter(status='pending').count()
    total_revenue = orders.filter(payment_status='completed').aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    total_users = User.objects.count()

    context = {
        'orders': orders,
        'total_orders': total_orders,
        'pending_orders': pending_orders,
        'total_revenue': total_revenue,
        'total_users': total_users,
    }
    return render(request, 'users/order_history.html', context)


@login_required(login_url='login')
@require_http_methods(["GET"])
def view_tickets(request):
    """View user's support tickets"""
    from .models import Ticket
    
    # Get filter parameter
    status_filter = request.GET.get('status', 'all')
    
    # Get user's tickets
    tickets_qs = Ticket.objects.filter(user=request.user).order_by('-created_at')
    
    # Filter by status
    if status_filter != 'all':
        tickets_qs = tickets_qs.filter(status=status_filter)
    
    # Get stats
    total_tickets = Ticket.objects.filter(user=request.user).count()
    open_tickets = Ticket.objects.filter(user=request.user, status__in=['open', 'in_progress']).count()
    resolved_tickets = Ticket.objects.filter(user=request.user, status='resolved').count()
    
    context = {
        'tickets': tickets_qs,
        'total_tickets': total_tickets,
        'open_tickets': open_tickets,
        'resolved_tickets': resolved_tickets,
        'status_filter': status_filter,
    }
    return render(request, 'users/view_tickets.html', context)


@login_required(login_url='login')
@require_http_methods(["GET"])
def ticket_detail(request, ticket_id):
    """View ticket detail with admin responses"""
    from .models import Ticket
    
    # Get ticket and ensure user owns it
    ticket = get_object_or_404(Ticket, id=ticket_id, user=request.user)
    
    context = {
        'ticket': ticket,
    }
    return render(request, 'users/ticket_detail.html', context)


