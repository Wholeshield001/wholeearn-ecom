from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages, auth
from django.contrib.auth import authenticate, update_session_auth_hash
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db import IntegrityError
from django.db.models import Sum
from django.db.models import Exists, OuterRef
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
import secrets
from ecom.models import (
    Cart,
    CartItem,
    Order,
    RewardPointConfig,
    RewardPointLedger,
    RewardConversion,
    UserWallet,
    WalletBankAccount,
    WalletWithdrawalRequest,
)
from ecom.views import reconcile_recent_monnify_orders_for_user
from ecom.services.wallets import (
    WalletOperationError,
    add_or_update_bank_account,
    convert_points_to_wallet,
    create_withdrawal_request,
)
from ecom.services.payments import PaymentGatewayError, get_payment_provider
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
    PartnerRegistrationForm,
    KYCSubmissionForm,
    RewardConversionForm,
    WalletBankAccountForm,
    WalletWithdrawalForm,
)
from .models import Ticket, KYCSubmission, KYCSubmissionAuditLog
from .emails import send_verification_otp_email, send_welcome_email, send_password_reset_email, send_kyc_submitted_email, send_kyc_submitted_admin_email
from .tasks import send_kyc_submission_email_task
from ecom.tasks import process_withdrawal_request_task

User = get_user_model()

REFERRAL_SESSION_KEY = 'signup_referral_code'


def _normalize_referral_code(value):
    return (value or '').strip().upper()


def _get_signup_referral_code(request):
    referral_code = _normalize_referral_code(
        request.GET.get('ref')
        or request.GET.get('referral')
        or request.GET.get('code')
    )
    if referral_code:
        if User.objects.filter(referral_code=referral_code).exists():
            request.session[REFERRAL_SESSION_KEY] = referral_code
        else:
            request.session.pop(REFERRAL_SESSION_KEY, None)
            messages.warning(request, 'That referral link is invalid or has expired.')
            return ''
    return request.session.get(REFERRAL_SESSION_KEY, '')


@require_http_methods(["GET", "POST"])
def signup(request):
    """Handle user registration"""
    referral_code = _get_signup_referral_code(request)

    if request.method == 'POST':
        post_data = request.POST.copy()
        if not post_data.get('referral_code_input') and referral_code:
            post_data['referral_code_input'] = referral_code
        form = SignUpForm(post_data)
        if form.is_valid():
            try:
                user = form.save(commit=False)
                user.save()
                request.session.pop(REFERRAL_SESSION_KEY, None)
                
                # Send verification OTP email
                email_sent = send_verification_otp_email(user)
                
                # Store user email in session for OTP verification
                request.session['pending_verification_email'] = user.email
                request.session['verification_attempts'] = 0

                if email_sent:
                    messages.success(
                        request,
                        'Account created! Check your email for the verification code.'
                    )
                else:
                    messages.warning(
                        request,
                        'Account created, but we could not send the verification email right now. Please use "Resend code" in the next step.'
                    )
                return redirect('verify-otp')
            except IntegrityError:
                messages.error(request, 'An error occurred. Please try again.')
                form = SignUpForm()
    else:
        form = SignUpForm(initial={'referral_code_input': referral_code} if referral_code else None)
    
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
        email_sent = send_verification_otp_email(user)
        if email_sent:
            request.session['verification_attempts'] = 0
            messages.success(request, 'Verification code sent! Check your email.')
        else:
            messages.error(request, 'Could not send verification code right now. Please try again in a moment.')
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
    from django.db.models import Sum, Q, Exists, OuterRef

    reconcile_recent_monnify_orders_for_user(request, request.user)
    
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

    referred_users = request.user.referred_users.annotate(
        has_purchased=Exists(
            Order.objects.filter(user=OuterRef('pk'), payment_status='completed')
        )
    ).order_by('-date_joined')
    context['referred_users'] = referred_users
    context['referral_code'] = request.user.referral_code
    context['referral_link'] = request.build_absolute_uri(
        f"{reverse('signup')}?ref={request.user.referral_code}"
    )

    return render(request, 'users/dashboard.html', context)


@login_required(login_url='login')
@require_http_methods(["GET"])
def reward_dashboard(request):
    """Dedicated rewards dashboard with referral and points activity."""
    withdrawal_notice = request.session.pop('withdrawal_notice', None)
    withdrawal_idempotency_key = secrets.token_urlsafe(24)
    request.session['withdrawal_idempotency_key'] = withdrawal_idempotency_key
    referral_link = request.build_absolute_uri(
        f"{reverse('signup')}?ref={request.user.referral_code}"
    )
    referred_users = request.user.referred_users.annotate(
        has_purchased=Exists(
            Order.objects.filter(user=OuterRef('pk'), payment_status='completed')
        )
    ).order_by('-date_joined')

    completed_referrals = referred_users.filter(has_purchased=True).count()

    page_size = 8
    ledger_qs = RewardPointLedger.objects.filter(user=request.user).select_related('order').order_by('-created_at')
    point_ledger = ledger_qs[:page_size]
    has_more = ledger_qs.count() > page_size

    config = RewardPointConfig.get_solo()
    wallet = UserWallet.get_for_user(request.user)
    bank_accounts = WalletBankAccount.objects.filter(user=request.user, is_active=True).order_by('-is_default', '-updated_at')
    recent_conversions = RewardConversion.objects.filter(user=request.user).order_by('-created_at')[:5]
    recent_withdrawals = WalletWithdrawalRequest.objects.filter(user=request.user).select_related('bank_account').order_by('-created_at')[:5]

    context = {
        'referral_code': request.user.referral_code,
        'referral_link': referral_link,
        'referred_users': referred_users,
        'total_referrals': referred_users.count(),
        'completed_referrals': completed_referrals,
        'point_ledger': point_ledger,
        'has_more': has_more,
        'next_offset': page_size,
        'wallet': wallet,
        'reward_config': config,
        'bank_accounts': bank_accounts,
        'recent_conversions': recent_conversions,
        'recent_withdrawals': recent_withdrawals,
        'withdrawal_notice': withdrawal_notice,
        'withdrawal_idempotency_key': withdrawal_idempotency_key,
        'conversion_form': RewardConversionForm(request.user),
        'bank_account_form': WalletBankAccountForm(),
        'withdrawal_form': WalletWithdrawalForm(request.user),
    }
    return render(request, 'users/reward.html', context)


@login_required(login_url='login')
@require_http_methods(["POST"])
def convert_rewards_to_wallet(request):
    """Convert reward points to wallet balance."""
    form = RewardConversionForm(request.user, request.POST)
    if not form.is_valid():
        messages.error(request, '; '.join(form.errors.get('points', ['Invalid conversion request.'])))
        return redirect('reward-dashboard')

    try:
        conversion = convert_points_to_wallet(user=request.user, points=form.cleaned_data['points'])
        messages.success(
            request,
            f"Conversion successful: {conversion.points} points converted to N{conversion.naira_amount}."
        )
    except WalletOperationError as exc:
        messages.error(request, str(exc))
    return redirect('reward-dashboard')


@login_required(login_url='login')
@require_http_methods(["POST"])
def add_wallet_bank_account(request):
    """Add and verify payout bank account through Monnify."""
    form = WalletBankAccountForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Please provide valid bank account details.')
        return redirect('reward-dashboard')

    try:
        account = add_or_update_bank_account(
            user=request.user,
            account_number=form.cleaned_data['account_number'],
            bank_code=form.cleaned_data['bank_code'],
            bank_name=form.cleaned_data.get('bank_name'),
            set_default=bool(form.cleaned_data.get('set_default')),
        )
        messages.success(request, f"Bank account verified for {account.account_name}.")
    except WalletOperationError as exc:
        messages.error(request, str(exc))
    return redirect('reward-dashboard')


@login_required(login_url='login')
@require_http_methods(["POST"])
def request_wallet_withdrawal(request):
    """Create and process wallet withdrawal using Monnify transfer."""
    form = WalletWithdrawalForm(request.user, request.POST)
    if not form.is_valid():
        messages.error(request, 'Please provide a valid withdrawal amount and account.')
        return redirect('reward-dashboard')

    withdrawal_idempotency_key = (request.POST.get('withdrawal_idempotency_key') or '').strip()
    session_withdrawal_key = request.session.get('withdrawal_idempotency_key', '')
    if not withdrawal_idempotency_key or withdrawal_idempotency_key != session_withdrawal_key:
        messages.error(request, 'Your withdrawal form expired. Please reopen the withdrawal form and try again.')
        return redirect('reward-dashboard')

    bank_account = get_object_or_404(
        WalletBankAccount,
        id=form.cleaned_data['bank_account_id'],
        user=request.user,
        is_verified=True,
        is_active=True,
    )

    try:
        withdrawal = create_withdrawal_request(
            user=request.user,
            amount=form.cleaned_data['amount'],
            bank_account=bank_account,
            idempotency_key=withdrawal_idempotency_key,
        )
        if withdrawal.status in {WalletWithdrawalRequest.PENDING, WalletWithdrawalRequest.FAILED}:
            process_withdrawal_request_task.delay(str(withdrawal.pk))
            request.session['withdrawal_notice'] = {
                'kind': 'queued',
                'title': 'Withdrawal queued',
                'message': 'Your withdrawal request has been received and is waiting in the processing queue.',
                'reference': withdrawal.reference,
                'amount': f"N{withdrawal.amount:.2f}",
            }
            messages.success(request, f"Withdrawal request received and queued for processing. Reference: {withdrawal.reference}")
        elif withdrawal.status == WalletWithdrawalRequest.PROCESSING:
            request.session['withdrawal_notice'] = {
                'kind': 'processing',
                'title': 'Withdrawal already processing',
                'message': 'This withdrawal is already being processed. You do not need to submit it again.',
                'reference': withdrawal.reference,
                'amount': f"N{withdrawal.amount:.2f}",
            }
            messages.info(request, f"Withdrawal is already being processed. Reference: {withdrawal.reference}")
        elif withdrawal.status == WalletWithdrawalRequest.SUCCESS:
            request.session['withdrawal_notice'] = {
                'kind': 'success',
                'title': 'Withdrawal completed',
                'message': f'Withdrawal successful: N{withdrawal.amount:.2f} sent to your bank account.',
                'reference': withdrawal.reference,
                'amount': f"N{withdrawal.amount:.2f}",
            }
            messages.success(request, f"Withdrawal successful: N{withdrawal.amount} sent to your bank account.")
        else:
            messages.warning(request, 'Withdrawal request submitted and is being processed.')
    except WalletOperationError as exc:
        messages.error(request, str(exc))

    return redirect('reward-dashboard')


@login_required(login_url='login')
@require_http_methods(["GET"])
def wallet_bank_list(request):
    """Return Monnify-supported bank list for bank-account dropdowns."""
    try:
        provider = get_payment_provider('monnify')
        if not hasattr(provider, 'list_banks'):
            return JsonResponse({'ok': False, 'error': 'Bank list unavailable.'}, status=400)

        banks = provider.list_banks()
        banks = sorted(banks, key=lambda row: row.get('name', '').lower())
        return JsonResponse({'ok': True, 'banks': banks})
    except PaymentGatewayError as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=502)
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Unable to load bank list right now.'}, status=500)


@login_required(login_url='login')
@require_http_methods(["GET"])
def wallet_account_lookup(request):
    """Resolve account name from bank code and account number using Monnify."""
    account_number = (request.GET.get('account_number') or '').strip()
    bank_code = (request.GET.get('bank_code') or '').strip()

    if not account_number or not bank_code:
        return JsonResponse({'ok': False, 'error': 'Account number and bank code are required.'}, status=400)

    if not account_number.isdigit() or len(account_number) != 10:
        return JsonResponse({'ok': False, 'error': 'Enter a valid 10-digit account number.'}, status=400)

    import re
    if not re.fullmatch(r'[\w\-]{1,20}', bank_code):
        return JsonResponse({'ok': False, 'error': 'Invalid bank code.'}, status=400)

    try:
        provider = get_payment_provider('monnify')
        if not hasattr(provider, 'verify_bank_account'):
            return JsonResponse({'ok': False, 'error': 'Account lookup unavailable.'}, status=400)

        result = provider.verify_bank_account(account_number=account_number, bank_code=bank_code)
        account_name = (result.get('account_name') or '').strip()
        if not account_name:
            return JsonResponse({'ok': False, 'error': 'Unable to resolve account name.'}, status=502)

        return JsonResponse({
            'ok': True,
            'account_name': account_name,
            'bank_name': (result.get('bank_name') or '').strip(),
        })
    except PaymentGatewayError as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=502)
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Unable to verify account right now.'}, status=500)


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

    PAGE_SIZE = 5
    qs = RewardPointLedger.objects.filter(user=request.user).select_related('order').order_by('-created_at')
    point_ledger = qs[:PAGE_SIZE]
    has_more = qs.count() > PAGE_SIZE
    return render(request, 'users/profile.html', {
        'point_ledger': point_ledger,
        'has_more': has_more,
        'next_offset': PAGE_SIZE,
    })


@login_required(login_url='login')
@require_http_methods(["GET"])
def rewards_load_more(request):
    PAGE_SIZE = 5
    try:
        offset = int(request.GET.get('offset', 0))
    except (ValueError, TypeError):
        offset = 0
    qs = RewardPointLedger.objects.filter(user=request.user).select_related('order').order_by('-created_at')
    total = qs.count()
    point_ledger = qs[offset:offset + PAGE_SIZE]
    next_offset = offset + PAGE_SIZE
    has_more = next_offset < total
    return render(request, 'users/partials/reward_rows.html', {
        'point_ledger': point_ledger,
        'has_more': has_more,
        'next_offset': next_offset,
    })


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
                email_sent = send_password_reset_email(user)
                if email_sent:
                    request.session['reset_email'] = email
                    messages.success(request, 'We sent a verification code to your email.')
                    return redirect('password-reset-verify')
                messages.error(request, 'We could not send a reset code right now. Please try again shortly.')
                return redirect('password-reset-request')
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

    PAGE_SIZE = 10
    qs = Order.objects.filter(user=request.user).prefetch_related('items').order_by('-created_at')
    total_orders = qs.count()
    pending_orders = qs.filter(status='pending').count()
    total_revenue = qs.filter(payment_status='completed').aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    total_users = User.objects.count()

    orders = qs[:PAGE_SIZE]
    has_more = total_orders > PAGE_SIZE

    context = {
        'orders': orders,
        'total_orders': total_orders,
        'pending_orders': pending_orders,
        'total_revenue': total_revenue,
        'total_users': total_users,
        'has_more': has_more,
        'next_offset': PAGE_SIZE,
    }
    return render(request, 'users/order_history.html', context)


@login_required(login_url='login')
@require_http_methods(["GET"])
def order_history_more(request):
    """HTMX endpoint: load next page of orders"""
    from ecom.models import Order

    PAGE_SIZE = 10
    try:
        offset = int(request.GET.get('offset', 0))
    except (ValueError, TypeError):
        offset = 0

    qs = Order.objects.filter(user=request.user).prefetch_related('items').order_by('-created_at')
    total = qs.count()
    orders = qs[offset:offset + PAGE_SIZE]
    next_offset = offset + PAGE_SIZE
    has_more = next_offset < total

    return render(request, 'users/partials/order_rows.html', {
        'orders': orders,
        'has_more': has_more,
        'next_offset': next_offset,
    })


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


@require_http_methods(["GET", "POST"])
def partner_signup(request):
    """Handle business partner registration"""
    referral_code = _get_signup_referral_code(request)

    if request.method == 'POST':
        post_data = request.POST.copy()
        if not post_data.get('referral_code_input') and referral_code:
            post_data['referral_code_input'] = referral_code
        form = PartnerRegistrationForm(post_data)
        if form.is_valid():
            try:
                user = form.save(commit=False)
                user.save()
                request.session.pop(REFERRAL_SESSION_KEY, None)
                
                # Send verification OTP email
                email_sent = send_verification_otp_email(user)
                
                # Store user email in session for OTP verification
                request.session['pending_verification_email'] = user.email
                request.session['verification_attempts'] = 0
                request.session['partner_type'] = form.cleaned_data.get('partner_type')

                if email_sent:
                    messages.success(
                        request,
                        'Account created! Check your email for the verification code.'
                    )
                else:
                    messages.warning(
                        request,
                        'Account created, but we could not send the verification email. Please use "Resend code" in the next step.'
                    )
                return redirect('verify-otp')
            except IntegrityError:
                messages.error(request, 'An account with this email already exists.')
                form = PartnerRegistrationForm()
    else:
        form = PartnerRegistrationForm(initial={'referral_code_input': referral_code} if referral_code else None)
    
    return render(request, 'users/partner_signup.html', {'form': form})


@login_required(login_url='login')
@require_http_methods(["GET", "POST"])
def submit_kyc(request):
    """Allow users to submit KYC documents"""
    # Only partner roles (non END_USER) need KYC
    if request.user.role == User.END_USER:
        messages.info(request, 'KYC is not required for end-users.')
        return redirect('dashboard')
    
    # Check if user already has KYC submission
    existing_kyc = KYCSubmission.objects.filter(user=request.user).first()
    
    if request.method == 'POST':
        form = KYCSubmissionForm(request.POST, request.FILES, instance=existing_kyc)
        if form.is_valid():
            kyc = form.save(commit=False)
            kyc.user = request.user
            kyc.user_type = request.user.role
            kyc.save()
            
            # Update user KYC submitted timestamp
            request.user.kyc_submitted_at = timezone.now()
            request.user.kyc_status = User.KYC_PENDING
            request.user.save()
            
            # Queue notification emails (user + admins) through Celery.
            try:
                async_result = send_kyc_submission_email_task.delay(str(kyc.id))
                kyc.log_event(
                    event_type=KYCSubmissionAuditLog.EVENT_EMAIL,
                    actor=request.user,
                    email_status=KYCSubmissionAuditLog.EMAIL_QUEUED,
                    message='KYC submission emails queued.',
                    metadata={'task_id': async_result.id},
                )
            except Exception:
                # Fallback to synchronous send if queue is unavailable.
                user_sent = send_kyc_submitted_email(request.user, kyc)
                admin_sent = send_kyc_submitted_admin_email(request.user, kyc)
                all_sent = user_sent and admin_sent
                kyc.log_event(
                    event_type=KYCSubmissionAuditLog.EVENT_EMAIL,
                    actor=request.user,
                    email_status=KYCSubmissionAuditLog.EMAIL_SENT if all_sent else KYCSubmissionAuditLog.EMAIL_FAILED,
                    message='KYC submission emails sent synchronously due to queue unavailability.' if all_sent else 'KYC submission email failed during synchronous fallback.',
                    metadata={'user_email_sent': bool(user_sent), 'admin_email_sent': bool(admin_sent)},
                )
            
            messages.success(
                request,
                'KYC documents submitted successfully! Our team will review and get back to you shortly.'
            )
            return redirect('kyc-status')
    else:
        initial_data = {
            'user_type': request.user.role,
        } if not existing_kyc else None
        form = KYCSubmissionForm(instance=existing_kyc, initial=initial_data)
    
    context = {
        'form': form,
        'existing_kyc': existing_kyc,
    }
    return render(request, 'users/submit_kyc.html', context)


@login_required(login_url='login')
@require_http_methods(["GET", "POST"])
def kyc_status(request):
    """Display user's KYC verification status"""
    kyc_submission = KYCSubmission.objects.filter(user=request.user).first()

    # Handle skip logic
    can_skip = request.session.pop('kyc_skip_allowed', False)
    if request.method == 'POST' and can_skip:
        # User chose to skip KYC for now
        messages.info(request, 'You skipped KYC. You must complete it before you can buy products.')
        return redirect('dashboard')

    context = {
        'kyc_submission': kyc_submission,
        'kyc_status': request.user.kyc_status,
        'kyc_rejection_reason': request.user.kyc_rejection_reason,
        'can_skip': can_skip,
    }
    return render(request, 'users/kyc_status.html', context)

