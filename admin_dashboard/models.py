from django.db import models
import uuid

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
    description = models.TextField(blank=True, null=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount = models.IntegerField(default=0, help_text="Discount percentage")  # matches form
    stock = models.IntegerField(default=0, blank=True, null=True)
    sku = models.CharField(max_length=100, unique=True, blank=True, null=True)
    # thumbnail = models.ImageField(upload_to='products/thumbnails/', blank=True, null=True)
    # image_1 = models.ImageField(upload_to='products/', blank=True, null=True)
    # image_2 = models.ImageField(upload_to='products/', blank=True, null=True)
    # image_3 = models.ImageField(upload_to='products/', blank=True, null=True)
    additional_info = models.TextField(blank=True, null=True)  # matches form
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


class ProductImage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/", blank=True, null=True)
    is_thumbnail = models.BooleanField(default=False, blank=True, null=True)

    def __str__(self):
        return f"Image for {self.product.name}"