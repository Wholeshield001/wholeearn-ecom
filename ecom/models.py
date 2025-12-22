from django.db import models
from django.contrib.auth import get_user_model
from admin_dashboard.models import Product
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
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    
    # Order details
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    
    # Payment info
    payment_reference = models.CharField(max_length=255, unique=True, null=True, blank=True)
    paystack_reference = models.CharField(max_length=255, null=True, blank=True)
    
    # Shipping info
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


class OrderItem(models.Model):
    """Items in an order"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    product_name = models.CharField(max_length=255)  # Snapshot
    product_sku = models.CharField(max_length=100, null=True, blank=True)  # Snapshot
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)  # Snapshot at order time
    
    def __str__(self):
        return f"{self.product_name} x{self.quantity}"
    
    def get_total_price(self):
        return self.price * self.quantity
