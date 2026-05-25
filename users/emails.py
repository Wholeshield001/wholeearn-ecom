from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import logging


logger = logging.getLogger(__name__)


def _safe_send_mail(*, subject, message, from_email, recipient_list, html_message):
    """Send email without raising exceptions to request handlers."""
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=recipient_list,
            html_message=html_message,
            fail_silently=False,
        )
        return True
    except Exception:
        logger.exception("Failed to send email '%s' to %s", subject, recipient_list)
        return False


def send_verification_otp_email(user):
    """Send OTP to user's email for verification"""
    otp = user.generate_verification_otp()
    
    context = {
        'user': user,
        'otp': otp,
        'site_name': 'WholeShield',
    }
    
    # Render HTML email
    html_message = render_to_string('emails/verification_otp_email.html', context)
    plain_message = strip_tags(html_message)
    
    return _safe_send_mail(
        subject='Your WholeShield Verification Code',
        message=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=html_message,
    )


def send_welcome_email(user):
    """Send welcome email after successful verification"""
    context = {
        'user': user,
        'site_name': 'WholeShield',
    }
    
    html_message = render_to_string('emails/welcome_email.html', context)
    plain_message = strip_tags(html_message)
    
    return _safe_send_mail(
        subject='Welcome to WholeShield!',
        message=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=html_message,
    )


def send_password_reset_email(user):
    """Send password reset OTP and token"""
    otp = user.generate_reset_otp()
    context = {
        'user': user,
        'otp': otp,
        'site_name': 'WholeShield',
    }

    html_message = render_to_string('emails/password_reset_email.html', context)
    plain_message = strip_tags(html_message)

    return _safe_send_mail(
        subject='Reset your WholeShield password',
        message=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=html_message,
    )


def send_kyc_submitted_email(user, kyc_submission):
    """Send confirmation email after KYC submission"""
    context = {
        'user': user,
        'kyc_submission': kyc_submission,
        'site_name': 'WholeShield',
        'site_url': settings.SITE_URL,
    }
    
    html_message = render_to_string('emails/kyc_submitted.html', context)
    plain_message = strip_tags(html_message)
    
    return _safe_send_mail(
        subject='KYC Documents Received - WholeShield',
        message=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=html_message,
    )


def send_kyc_submitted_admin_email(user, kyc_submission):
    """Send admin notification when KYC is submitted"""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    # Get all admin users
    admins = User.objects.filter(role=User.ADMINISTRATOR)
    admin_emails = list(admins.values_list('email', flat=True))
    
    if not admin_emails:
        return False
    
    context = {
        'user': user,
        'kyc_submission': kyc_submission,
        'site_name': 'WholeShield',
        'site_url': settings.SITE_URL,
    }
    
    html_message = render_to_string('emails/kyc_submitted_admin.html', context)
    plain_message = strip_tags(html_message)
    
    return _safe_send_mail(
        subject=f'New KYC Submission: {user.email}',
        message=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=admin_emails,
        html_message=html_message,
    )


def send_kyc_approved_email(user):
    """Send email when KYC is approved"""
    context = {
        'user': user,
        'site_name': 'WholeShield',
        'site_url': settings.SITE_URL,
    }
    
    html_message = render_to_string('emails/kyc_approved.html', context)
    plain_message = strip_tags(html_message)
    
    return _safe_send_mail(
        subject='Your KYC has been Approved - WholeShield',
        message=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=html_message,
    )


def send_kyc_rejected_email(user, rejection_reason):
    """Send email when KYC is rejected"""
    context = {
        'user': user,
        'rejection_reason': rejection_reason,
        'site_name': 'WholeShield',
        'site_url': settings.SITE_URL,
    }
    
    html_message = render_to_string('emails/kyc_rejected.html', context)
    plain_message = strip_tags(html_message)
    
    return _safe_send_mail(
        subject='KYC Verification Update - WholeShield',
        message=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=html_message,
    )