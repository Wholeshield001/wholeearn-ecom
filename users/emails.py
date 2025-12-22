from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags


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
    
    send_mail(
        subject='Your WholeShield Verification Code',
        message=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=html_message,
        fail_silently=False,
    )


def send_welcome_email(user):
    """Send welcome email after successful verification"""
    context = {
        'user': user,
        'site_name': 'WholeShield',
    }
    
    html_message = render_to_string('emails/welcome_email.html', context)
    plain_message = strip_tags(html_message)
    
    send_mail(
        subject='Welcome to WholeShield!',
        message=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=html_message,
        fail_silently=False,
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

    send_mail(
        subject='Reset your WholeShield password',
        message=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=html_message,
        fail_silently=False,
    )