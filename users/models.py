from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils import timezone
import uuid
import random
import pyotp
import secrets

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    ADMINISTRATOR = 'administrator'
    WHOLESALER = 'wholesaler'
    RETAILER = 'retailer'
    HOSPITAL = 'hospital'
    PHARMACY = 'pharmacy'
    END_USER = 'end_user'

    ROLE_CHOICES = [
        (ADMINISTRATOR, 'Administrator'),
        (WHOLESALER, 'Wholesaler'),
        (RETAILER, 'Retailer'),
        (HOSPITAL, 'Hospital'),
        (PHARMACY, 'Pharmacy'),
        (END_USER, 'End User'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=150, blank=True, null=True)
    last_name = models.CharField(max_length=150, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, blank=True, null=True)
    is_verified_kyc = models.BooleanField(default=False, blank=True, null=True)
    is_active = models.BooleanField(default=False)  # Changed to False by default
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    
    # Email verification OTP fields
    email_verified = models.BooleanField(default=False)
    verification_otp = models.CharField(max_length=6, blank=True, null=True)
    verification_otp_created_at = models.DateTimeField(blank=True, null=True)
    
    # Password reset fields
    reset_otp = models.CharField(max_length=6, blank=True, null=True)
    reset_otp_created_at = models.DateTimeField(blank=True, null=True)
    reset_token = models.CharField(max_length=100, blank=True, null=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return f"{self.email} ({self.role})"
    
    def generate_verification_otp(self):
        """Generate a 6-digit OTP for email verification"""
        self.verification_otp = str(random.randint(100000, 999999))
        self.verification_otp_created_at = timezone.now()
        self.save()
        return self.verification_otp
    
    def verify_email_otp(self, otp):
        """Verify the OTP is correct and not expired (valid for 15 minutes)"""
        if not self.verification_otp or not self.verification_otp_created_at:
            return False
        
        # Check if OTP matches
        if self.verification_otp != otp:
            return False
        
        # Check if OTP is expired (15 minutes)
        time_diff = timezone.now() - self.verification_otp_created_at
        if time_diff.total_seconds() > 900:  # 15 minutes
            return False
        
        self.email_verified = True
        self.is_active = True
        self.verification_otp = None
        self.verification_otp_created_at = None
        self.save()
        return True
    
    def clear_verification_otp(self):
        """Clear verification OTP after failed attempts or expiration"""
        self.verification_otp = None
        self.verification_otp_created_at = None
        self.save()
    
    def generate_reset_otp(self):
        """Generate a 6-digit OTP for password reset"""
        self.reset_otp = str(random.randint(100000, 999999))
        self.reset_otp_created_at = timezone.now()
        self.reset_token = secrets.token_urlsafe(32)
        self.save()
        return self.reset_otp
    
    def verify_reset_otp(self, otp):
        """Verify the OTP is correct and not expired (valid for 10 minutes)"""
        if not self.reset_otp or not self.reset_otp_created_at:
            return False
        
        # Check if OTP matches
        if self.reset_otp != otp:
            return False
        
        # Check if OTP is expired (10 minutes)
        time_diff = timezone.now() - self.reset_otp_created_at
        if time_diff.total_seconds() > 600:  # 10 minutes
            return False
        
        return True
    
    def clear_reset_data(self):
        """Clear password reset data after successful reset"""
        self.reset_otp = None
        self.reset_otp_created_at = None
        self.reset_token = None
        self.save()
    
    def get_full_name(self):
        """Return the user's full name or email if name not set"""
        full_name = ""
        if self.first_name:
            full_name = self.first_name
        if self.last_name:
            full_name = f"{full_name} {self.last_name}".strip()
        return full_name if full_name else self.email


class Ticket(models.Model):
    """Support tickets/complaints from users"""
    STATUS_CHOICES = [
        ("open", "Open"),
        ("in_progress", "In Progress"),
        ("resolved", "Resolved"),
        ("closed", "Closed"),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="support_tickets")
    title = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open")
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    
    # Admin response and assignment
    admin_response = models.TextField(null=True, blank=True)
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_support_tickets', limit_choices_to={'role': 'administrator'})
    
    # Contact info
    contact_email = models.EmailField(blank=True, null=True)
    contact_name = models.CharField(max_length=255, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Ticket #{str(self.id)[:8]} - {self.title}"

