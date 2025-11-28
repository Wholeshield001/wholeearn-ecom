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
    CUSTOMER = 'customer'

    ROLE_CHOICES = [
        (ADMINISTRATOR, 'Administrator'),
        (WHOLESALER, 'Wholesaler'),
        (RETAILER, 'Retailer'),
        (CUSTOMER, 'Customer'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=150, blank=True, null=True)
    last_name = models.CharField(max_length=150, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, blank=True, null=True)
    is_verified_kyc = models.BooleanField(default=False, blank=True, null=True)
    is_verifier = models.BooleanField(default=False, blank=True, null=True)
    is_active = models.BooleanField(default=True, blank=True, null=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    
    # Password reset fields
    reset_otp = models.CharField(max_length=6, blank=True, null=True)
    reset_otp_created_at = models.DateTimeField(blank=True, null=True)
    reset_token = models.CharField(max_length=100, blank=True, null=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return f"{self.email} ({self.role})"
    
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