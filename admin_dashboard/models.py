from django.db import models
from django.conf import settings
from django.utils.text import slugify
import uuid
from django_ckeditor_5.fields import CKEditor5Field

class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['-created_at']

    def __str__(self):
        return self.name

class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, blank=True, null=True)
    description = CKEditor5Field('Description', config_name='default', blank=True, null=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    
    # Pricing for different roles
    customer_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    wholesaler_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True, null=True)
    retailer_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True, null=True)
    hospital_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True, null=True)
    pharmacy_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True, null=True)
    online_vendor_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True, null=True)
    
    # Legacy field kept for backward compatibility
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Legacy price field - use role-specific prices instead")
    
    discount = models.IntegerField(default=0, help_text="Discount percentage")
    stock = models.IntegerField(default=0, blank=True, null=True)
    weight_kg = models.DecimalField(max_digits=8, decimal_places=2, default=1.00, help_text="Product unit weight in kg")
    sku = models.CharField(max_length=100, unique=True, blank=True, null=True)
    is_best_seller = models.BooleanField(default=False, blank=True, null=True)
    is_male = models.BooleanField(default=False, help_text="Product for male")
    is_female = models.BooleanField(default=False, help_text="Product for female")
    is_general = models.BooleanField(default=True, help_text="Product for everyone")
    additional_info = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # IMPORTANT: store thumbnail relationship
    thumbnail = models.ForeignKey(
        "ProductImage", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return str(self.name)
    
    def get_price_for_role(self, role):
        """Get price based on user role"""
        from users.models import User
        
        price_map = {
            User.END_USER: self.customer_price,
            User.WHOLESALER: self.wholesaler_price or self.customer_price,
            User.RETAILER: self.retailer_price or self.customer_price,
            User.HOSPITAL: self.hospital_price or self.customer_price,
            User.PHARMACY: self.pharmacy_price or self.customer_price,
            User.ONLINE_VENDOR: self.online_vendor_price or self.customer_price,
        }
        return price_map.get(role, self.customer_price)
    
    def get_min_quantity_for_role(self, role):
        """Get minimum quantity that can be added to cart based on user role"""
        from users.models import User
        
        min_quantity_map = {
            User.END_USER: 1,
            User.WHOLESALER: 10,
            User.RETAILER: 5,
            User.HOSPITAL: 5,
            User.PHARMACY: 5,
            User.ONLINE_VENDOR: 10,
        }
        return min_quantity_map.get(role, 1)


class ProductImage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/", blank=True, null=True)
    is_thumbnail = models.BooleanField(default=False, blank=True, null=True)

    def __str__(self):
        return f"Image for {self.product.name}"


class BlogCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120, blank=True, null=True)
    slug = models.SlugField(max_length=160, unique=True)
    # parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Blog Category'
        verbose_name_plural = 'Blog Categories'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)
            unique = base
            idx = 1
            while BlogCategory.objects.filter(slug=unique).exclude(pk=self.pk).exists():
                unique = f"{base}-{idx}"
                idx += 1
            self.slug = unique
        super().save(*args, **kwargs)


class BlogPost(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    content = CKEditor5Field('Content', config_name='default', blank=True, null=True)
    cover_image = models.ImageField(upload_to='blog/', blank=True, null=True)
    is_published = models.BooleanField(default=False)
    category = models.ForeignKey(BlogCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='posts')
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='blog_posts')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)
            unique = base
            idx = 1
            while BlogPost.objects.filter(slug=unique).exclude(pk=self.pk).exists():
                unique = f"{base}-{idx}"
                idx += 1
            self.slug = unique
        super().save(*args, **kwargs)


class DailyWebsiteVisit(models.Model):
    date = models.DateField(unique=True)
    total_visits = models.PositiveIntegerField(default=0)
    unique_visitors = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.date}: {self.total_visits} visits"