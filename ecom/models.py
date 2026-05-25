from django.db import models, transaction
from django.db.models import F
from django.db.models.functions import Greatest
from django.utils import timezone
from django.contrib.auth import get_user_model
from admin_dashboard.models import Product
from decimal import Decimal
import uuid

User = get_user_model()

class Cart(models.Model):
    """Shopping cart for authenticated and anonymous users."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="cart", null=True, blank=True)
    session_id = models.CharField(max_length=255, null=True, blank=True)  # For anonymous users
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Carts"

    def __str__(self):
        return f"Cart for {self.user.email if self.user else self.session_id}"

    def get_total_price(self):
        """Calculate total price of all items in cart."""
        return sum(item.get_total_price() for item in self.items.all())

    def get_item_count(self):
        """Get total number of items in cart."""
        return sum(item.quantity for item in self.items.all())


class CartItem(models.Model):
    """Individual items in a shopping cart."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="cart_items")
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)  # Snapshot of price at time of adding
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Cart Items"
        unique_together = ("cart", "product")  # Prevent duplicate items in same cart

    def __str__(self):
        return f"{self.product.name} (x{self.quantity})"

    def get_total_price(self):
        """Calculate total price for this cart item."""
        return self.price * self.quantity


class Order(models.Model):
    """Customer orders with payment and tracking"""
    PAYMENT_PROVIDER_CHOICES = [
        ('paystack', 'Paystack'),
        ('monnify', 'Monnify'),
    ]

    # Statuses mirror Speedaf's tracking action codes so the display always
    # reflects what the carrier reports.
    STATUS_CHOICES = [
        ('pending',              'Pending'),               # before payment
        ('ordered',              'Ordered'),               # Speedaf action 10
        ('inbound',              'Inbound'),               # action 150
        ('packaged',             'Packaged'),              # action 181
        ('outbound',             'Outbound'),              # action 190
        ('picked',               'Picked'),                # action 1
        ('departed',             'Departed'),              # action 2
        ('arrived',              'Arrived'),               # action 3
        ('customs_declaration',  'Customs Declaration'),   # action 402
        ('flight_departed',      'Flight Departed'),       # action 220
        ('flight_landed',        'Flight Landed'),         # action 230
        ('in_clearance',         'In Clearance'),          # action 360
        ('clearance_exception',  'Clearance Exception'),   # action 401
        ('clearance_completed',  'Clearance Completed'),   # action 370
        ('in_delivery',          'In Delivery'),           # action 4
        ('delivered',            'Delivered'),             # action 5 / 16 / 18
        ('returning',            'Returning'),             # action -710
        ('returned',             'Returned'),              # action 730
        ('cancelled',            'Cancelled'),             # action -10
    ]
    
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    checkout_idempotency_key = models.CharField(max_length=64, unique=True, null=True, blank=True)
    
    # Order details
    shipping_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    inventory_deducted = models.BooleanField(default=False)
    
    # Payment info
    payment_provider = models.CharField(max_length=20, choices=PAYMENT_PROVIDER_CHOICES, default='paystack')
    payment_reference = models.CharField(max_length=255, unique=True, null=True, blank=True)
    gateway_reference = models.CharField(max_length=255, null=True, blank=True)
    paystack_reference = models.CharField(max_length=255, null=True, blank=True)
    referral_code_used = models.CharField(max_length=12, null=True, blank=True)
    referrer = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='referred_orders'
    )
    checkout_code = models.CharField(max_length=12, null=True, blank=True)
    checkout_code_owner = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='checkout_code_orders',
    )
    checkout_discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    checkout_discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    purchase_points_awarded = models.BooleanField(default=False)
    referral_points_awarded = models.BooleanField(default=False)
    checkout_code_points_awarded = models.BooleanField(default=False)
    
    # Shipping info
    speedaf_order_id = models.CharField(max_length=100, null=True, blank=True)
    shipping_address = models.TextField()
    shipping_city = models.CharField(max_length=100)
    shipping_state = models.CharField(max_length=100)
    shipping_phone = models.CharField(max_length=20)
    
    # Tracking
    tracking_number = models.CharField(max_length=100, null=True, blank=True)
    tracking_notes = models.TextField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Order {self.id} - {self.user.email}"

    def _should_deduct_inventory(self, was_deducted: bool = False):
        return (not was_deducted) and (
            self.payment_status == 'completed' or self.status == 'delivered'
        )

    @property
    def status_badge_class(self):
        """Tailwind CSS classes for the status badge pill."""
        green  = 'bg-green-100 text-green-700'
        blue   = 'bg-blue-100 text-blue-700'
        indigo = 'bg-indigo-100 text-indigo-700'
        orange = 'bg-orange-100 text-orange-700'
        red    = 'bg-red-100 text-red-700'
        yellow = 'bg-yellow-100 text-yellow-700'
        gray   = 'bg-gray-100 text-gray-600'
        mapping = {
            'pending':             yellow,
            'ordered':             blue,
            'inbound':             blue,
            'packaged':            blue,
            'outbound':            blue,
            'picked':              indigo,
            'departed':            indigo,
            'arrived':             indigo,
            'customs_declaration': indigo,
            'flight_departed':     indigo,
            'flight_landed':       indigo,
            'in_clearance':        indigo,
            'clearance_completed': indigo,
            'clearance_exception': orange,
            'in_delivery':         orange,
            'returning':           orange,
            'returned':            gray,
            'delivered':           green,
            'cancelled':           red,
        }
        return mapping.get(self.status, gray)

    def adjust_inventory(self):
        if self.inventory_deducted:
            return
        items = self.items.select_related('product')
        with transaction.atomic():
            for item in items:
                if item.product_id:
                    Product.objects.filter(id=item.product_id).update(
                        stock=Greatest(F('stock') - item.quantity, 0)
                    )
            # avoid recursive save by using update()
            Order.objects.filter(pk=self.pk).update(
                inventory_deducted=True,
                updated_at=timezone.now(),
            )
            self.inventory_deducted = True

    def apply_reward_points(self):
        """Award purchase/referral points only on a user's first completed purchase."""
        if self.payment_status != 'completed':
            return

        config = RewardPointConfig.get_solo()
        with transaction.atomic():
            is_first_purchase = not Order.objects.filter(
                user_id=self.user_id,
                payment_status='completed',
            ).exclude(pk=self.pk).exists()

            if not self.purchase_points_awarded:
                if is_first_purchase:
                    User.objects.filter(pk=self.user_id).update(
                        reward_points=F('reward_points') + config.points_per_purchase
                    )
                    RewardPointLedger.objects.create(
                        user_id=self.user_id,
                        points=config.points_per_purchase,
                        reason=RewardPointLedger.PURCHASE,
                        order=self,
                    )
                self.purchase_points_awarded = True

            if self.referrer_id and not self.referral_points_awarded:
                # Award referral bonus only on the referred user's first completed purchase.
                if is_first_purchase:
                    User.objects.filter(pk=self.referrer_id).update(
                        reward_points=F('reward_points') + config.referral_bonus_points
                    )
                    RewardPointLedger.objects.create(
                        user_id=self.referrer_id,
                        points=config.referral_bonus_points,
                        reason=RewardPointLedger.REFERRAL,
                        order=self,
                    )
                self.referral_points_awarded = True

            if self.checkout_code_owner_id and not self.checkout_code_points_awarded:
                checkout_code_points = sum(
                    (item.checkout_code_points or 0) * item.quantity
                    for item in self.items.all()
                )
                if checkout_code_points > 0:
                    User.objects.filter(pk=self.checkout_code_owner_id).update(
                        reward_points=F('reward_points') + checkout_code_points
                    )
                    RewardPointLedger.objects.create(
                        user_id=self.checkout_code_owner_id,
                        points=checkout_code_points,
                        reason=RewardPointLedger.CHECKOUT_CODE,
                        order=self,
                    )
                self.checkout_code_points_awarded = True

            Order.objects.filter(pk=self.pk).update(
                purchase_points_awarded=self.purchase_points_awarded,
                referral_points_awarded=self.referral_points_awarded,
                checkout_code_points_awarded=self.checkout_code_points_awarded,
                updated_at=timezone.now(),
            )

    def save(self, *args, **kwargs):
        should_adjust = False
        should_award_points = False
        prev = None
        if self.pk:
            prev = Order.objects.filter(pk=self.pk).values(
                'inventory_deducted', 'status', 'payment_status', 'purchase_points_awarded', 'referral_points_awarded'
            ).first()

        if prev:
            should_adjust = self._should_deduct_inventory(prev['inventory_deducted'])
            should_award_points = (
                prev['payment_status'] != 'completed'
                and self.payment_status == 'completed'
            )
        else:
            should_adjust = self._should_deduct_inventory(False)
            should_award_points = self.payment_status == 'completed'

        super().save(*args, **kwargs)

        if should_adjust:
            self.adjust_inventory()

        if should_award_points:
            self.apply_reward_points()


class RewardPointConfig(models.Model):
    """Configurable points awarded on completed purchases and referrals."""
    points_per_purchase = models.PositiveIntegerField(default=1)
    referral_bonus_points = models.PositiveIntegerField(default=1)
    checkout_code_discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Percentage discount applied to the product subtotal when a valid checkout code is used.',
    )
    points_to_naira_rate = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=Decimal('1.0000'),
        help_text='How much 1 reward point is worth in naira.',
    )
    minimum_withdrawal_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('1000.00'),
        help_text='Minimum wallet withdrawal amount in naira.',
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reward_configs_updated'
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Reward Point Configuration'
        verbose_name_plural = 'Reward Point Configuration'

    def __str__(self):
        return (
            f"Purchase: {self.points_per_purchase} | Referral: {self.referral_bonus_points} "
            f"| Code discount: {self.checkout_code_discount_percent}% | Rate: {self.points_to_naira_rate}"
        )

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class PaymentProviderConfig(models.Model):
    """Admin-configurable active payment gateway."""
    active_provider = models.CharField(
        max_length=20,
        choices=Order.PAYMENT_PROVIDER_CHOICES,
        default='paystack',
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payment_provider_configs_updated',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Payment Provider Configuration'
        verbose_name_plural = 'Payment Provider Configuration'

    def __str__(self):
        return f"Active payment provider: {self.get_active_provider_display()}"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class RewardPointLedger(models.Model):
    """Records every point credit or debit for a user."""
    PURCHASE = 'purchase'
    REFERRAL = 'referral'
    CHECKOUT_CODE = 'checkout_code'
    CONVERSION_DEBIT = 'conversion_debit'
    REASON_CHOICES = [
        (PURCHASE, 'Purchase Reward'),
        (REFERRAL, 'Referral Bonus'),
        (CHECKOUT_CODE, 'Checkout Code Reward'),
        (CONVERSION_DEBIT, 'Converted to Wallet'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='point_ledger',
    )
    points = models.IntegerField()  # positive = credit
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    order = models.ForeignKey(
        'Order',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ledger_entries',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Reward Point Entry'
        verbose_name_plural = 'Reward Point Ledger'

    def __str__(self):
        return f"{self.user.email} | {self.get_reason_display()} | {self.points:+d} pts"


class UserWallet(models.Model):
    """In-app wallet balance used for withdrawals."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wallet')
    available_balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    pending_balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    total_converted = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    total_withdrawn = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"Wallet {self.user.email} | Available: {self.available_balance}"

    @property
    def total_balance(self):
        return (self.available_balance or Decimal('0.00')) + (self.pending_balance or Decimal('0.00'))

    @classmethod
    def get_for_user(cls, user):
        wallet, _ = cls.objects.get_or_create(user=user)
        return wallet


class RewardConversion(models.Model):
    """Tracks conversion of points to naira in user wallet."""
    SUCCESS = 'success'
    FAILED = 'failed'
    STATUS_CHOICES = [
        (SUCCESS, 'Success'),
        (FAILED, 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reward_conversions')
    wallet = models.ForeignKey(UserWallet, on_delete=models.CASCADE, related_name='conversions')
    points = models.PositiveIntegerField()
    naira_amount = models.DecimalField(max_digits=14, decimal_places=2)
    rate_snapshot = models.DecimalField(max_digits=12, decimal_places=4)
    reference = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=SUCCESS)
    note = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} | {self.points} pts -> {self.naira_amount}"


class WalletBankAccount(models.Model):
    """Bank account destination for wallet withdrawals."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wallet_bank_accounts')
    account_name = models.CharField(max_length=255)
    account_number = models.CharField(max_length=20)
    bank_code = models.CharField(max_length=20)
    bank_name = models.CharField(max_length=120, blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    monnify_account_reference = models.CharField(max_length=120, blank=True, null=True)
    verified_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_default', '-updated_at']
        unique_together = ('user', 'account_number', 'bank_code')

    def __str__(self):
        return f"{self.user.email} | {self.bank_name or self.bank_code} - {self.account_number}"


class WalletWithdrawalRequest(models.Model):
    """Withdrawal requests from user wallet to bank account."""
    PENDING = 'pending'
    PROCESSING = 'processing'
    SUCCESS = 'success'
    FAILED = 'failed'
    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (PROCESSING, 'Processing'),
        (SUCCESS, 'Success'),
        (FAILED, 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wallet_withdrawals')
    wallet = models.ForeignKey(UserWallet, on_delete=models.CASCADE, related_name='withdrawals')
    bank_account = models.ForeignKey(WalletBankAccount, on_delete=models.PROTECT, related_name='withdrawals')
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reference = models.CharField(max_length=120, unique=True)
    idempotency_key = models.CharField(max_length=64, unique=True, null=True, blank=True)
    monnify_reference = models.CharField(max_length=120, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    provider_response = models.JSONField(blank=True, null=True)
    failure_reason = models.TextField(blank=True, null=True)
    processed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['user', 'created_at']),
        ]

    def __str__(self):
        return f"{self.user.email} | {self.amount} | {self.status}"


class OrderItem(models.Model):
    """Items in an order"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    product_name = models.CharField(max_length=255)  # Snapshot
    product_sku = models.CharField(max_length=100, null=True, blank=True)  # Snapshot
    checkout_code_points = models.PositiveIntegerField(default=0)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)  # Snapshot at order time
    
    def __str__(self):
        return f"{self.product_name} x{self.quantity}"
    
    def get_total_price(self):
        return self.price * self.quantity
