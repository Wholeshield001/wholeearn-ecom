from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
import sys
from .forms import AdminLoginForm, ForgotPasswordForm, VerifyOTPForm, ResetPasswordForm
from users.models import User


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


@login_required(login_url='admin_login')
def admin_dashboard(request):
    # Verify user is admin
    if request.user.role != User.ADMINISTRATOR or not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('admin_login')
    
    context = {
        'user': request.user,
    }
    return render(request, 'admin_dashboard/dashboard.html', context)


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


def products_page(request):
    return render(request, 'admin_dashboard/products.html')

def notifications_page(request):
    return render(request, 'admin_dashboard/notifications.html')

def wholesalers_page(request):
    return render(request, 'admin_dashboard/wholesalers.html')


def retailers_page(request):
    return render(request, 'admin_dashboard/retailer.html')