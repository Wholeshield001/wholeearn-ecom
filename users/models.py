from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils import timezone
import uuid
import random
import string
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
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("role", "administrator")
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    ADMINISTRATOR = 'administrator'
    WHOLESALER = 'wholesaler'
    RETAILER = 'retailer'
    HOSPITAL = 'hospital'
    PHARMACY = 'pharmacy'
    END_USER = 'end_user'
    ONLINE_VENDOR = 'online_vendor'

    ROLE_CHOICES = [
        (ADMINISTRATOR, 'Administrator'),
        (WHOLESALER, 'Wholesaler'),
        (RETAILER, 'Retailer'),
        (HOSPITAL, 'Hospital'),
        (PHARMACY, 'Pharmacy'),
        (END_USER, 'End User'),
        (ONLINE_VENDOR, 'Online Vendor'),
    ]
    
    # KYC Status choices
    KYC_PENDING = 'pending'
    KYC_APPROVED = 'approved'
    KYC_REJECTED = 'rejected'
    
    KYC_STATUS_CHOICES = [
        (KYC_PENDING, 'Pending'),
        (KYC_APPROVED, 'Approved'),
        (KYC_REJECTED, 'Rejected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    unique_code = models.CharField(max_length=12, unique=True, blank=True, null=True)
    referral_code = models.CharField(max_length=12, unique=True, blank=True, null=True)
    referred_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='referred_users'
    )
    reward_points = models.PositiveIntegerField(default=0)
    first_name = models.CharField(max_length=150, blank=True, null=True)
    last_name = models.CharField(max_length=150, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, blank=True, null=True)
    is_verified_kyc = models.BooleanField(default=False, blank=True, null=True)
    is_active = models.BooleanField(default=False)  # Changed to False by default
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    
    # KYC fields
    kyc_status = models.CharField(max_length=20, choices=KYC_STATUS_CHOICES, default=KYC_PENDING)
    kyc_submitted_at = models.DateTimeField(null=True, blank=True)
    kyc_verified_at = models.DateTimeField(null=True, blank=True)
    kyc_verified_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='kyc_verified_users')
    kyc_rejection_reason = models.TextField(null=True, blank=True)
    
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

    @classmethod
    def _generate_unique_code(cls, prefix):
        """Generate a collision-safe code with a predictable prefix."""
        alphabet = string.ascii_uppercase + string.digits
        while True:
            candidate = f"{prefix}{''.join(secrets.choice(alphabet) for _ in range(8))}"
            if not cls.objects.filter(unique_code=candidate).exists() and not cls.objects.filter(referral_code=candidate).exists():
                return candidate

    def save(self, *args, **kwargs):
        if not self.unique_code:
            self.unique_code = self._generate_unique_code('USR')
        if not self.referral_code:
            self.referral_code = self._generate_unique_code('REF')
        super().save(*args, **kwargs)
    
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


class KYCSubmission(models.Model):
    """KYC (Know Your Customer) submission for partner verification"""

    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    
    USER_TYPE_CHOICES = [
        ('wholesaler', 'Wholesaler'),
        ('retailer', 'Retailer'),
        ('pharmacy', 'Pharmacy'),
        ('hospital', 'Hospital'),
        ('online_vendor', 'Online Vendor'),
    ]
    
    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (APPROVED, 'Approved'),
        (REJECTED, 'Rejected'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='kyc_submission')
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES)
    
    # Common fields
    business_name = models.CharField(max_length=255)
    contact_number = models.CharField(max_length=20)
    business_address = models.TextField()
    
    # Document field (can be CAC, business registration, etc.)
    cac_document = models.FileField(upload_to='kyc_documents/%Y/%m/%d/', null=True, blank=True)
    
    # Status tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='kyc_verified_submissions')
    rejection_reason = models.TextField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'KYC Submission'
        verbose_name_plural = 'KYC Submissions'
        indexes = [
            models.Index(fields=['status', 'user']),
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return f"KYC {self.user.email} - {self.status}"

    def log_event(
        self,
        *,
        event_type,
        actor=None,
        from_status=None,
        to_status=None,
        email_status='',
        message='',
        metadata=None,
    ):
        return KYCSubmissionAuditLog.objects.create(
            submission=self,
            actor=actor,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            email_status=email_status or '',
            message=message or '',
            metadata=metadata or None,
        )
    
    def approve(self, admin_user):
        """Approve the KYC submission"""
        previous_status = self.status
        self.status = self.APPROVED
        self.verified_at = timezone.now()
        self.verified_by = admin_user
        self.save()
        
        # Update user KYC status
        self.user.kyc_status = User.KYC_APPROVED
        self.user.kyc_verified_at = timezone.now()
        self.user.kyc_verified_by = admin_user
        self.user.save()

        self.log_event(
            event_type=KYCSubmissionAuditLog.EVENT_STATUS_CHANGED,
            actor=admin_user,
            from_status=previous_status,
            to_status=self.APPROVED,
            message='KYC status updated to approved.',
        )
    
    def reject(self, admin_user, reason):
        """Reject the KYC submission"""
        previous_status = self.status
        self.status = self.REJECTED
        self.verified_at = timezone.now()
        self.verified_by = admin_user
        self.rejection_reason = reason
        self.save()
        
        # Update user KYC status
        self.user.kyc_status = User.KYC_REJECTED
        self.user.kyc_verified_at = timezone.now()
        self.user.kyc_verified_by = admin_user
        self.user.kyc_rejection_reason = reason
        self.user.save()

        self.log_event(
            event_type=KYCSubmissionAuditLog.EVENT_STATUS_CHANGED,
            actor=admin_user,
            from_status=previous_status,
            to_status=self.REJECTED,
            message='KYC status updated to rejected.',
            metadata={'rejection_reason': reason},
        )


class KYCSubmissionAuditLog(models.Model):
    """Tracks status and email delivery events for KYC submissions."""

    EVENT_STATUS_CHANGED = 'status_changed'
    EVENT_EMAIL = 'email'
    EVENT_CHOICES = [
        (EVENT_STATUS_CHANGED, 'Status Changed'),
        (EVENT_EMAIL, 'Email Event'),
    ]

    EMAIL_QUEUED = 'queued'
    EMAIL_SENT = 'sent'
    EMAIL_FAILED = 'failed'
    EMAIL_STATUS_CHOICES = [
        ('', 'N/A'),
        (EMAIL_QUEUED, 'Queued'),
        (EMAIL_SENT, 'Sent'),
        (EMAIL_FAILED, 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submission = models.ForeignKey(KYCSubmission, on_delete=models.CASCADE, related_name='audit_logs')
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='kyc_audit_events')
    event_type = models.CharField(max_length=20, choices=EVENT_CHOICES)
    from_status = models.CharField(max_length=20, blank=True, null=True)
    to_status = models.CharField(max_length=20, blank=True, null=True)
    email_status = models.CharField(max_length=20, choices=EMAIL_STATUS_CHOICES, blank=True, default='')
    message = models.TextField(blank=True, default='')
    metadata = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['submission', '-created_at']),
            models.Index(fields=['event_type', 'created_at']),
        ]

    def __str__(self):
        return f"{self.submission.user.email} | {self.event_type} | {self.created_at}"
