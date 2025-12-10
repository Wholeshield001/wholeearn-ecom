from django.contrib import admin
from .models import Category, Product, ProductImage
from unfold.admin import ModelAdmin

# Register your models here.


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ('name', 'description', 'created_at', 'updated_at')
    search_fields = ('name',)
    ordering = ('name',)

@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ('name', 'category', 'price', 'stock', 'created_at', 'updated_at')
    search_fields = ('name', 'category__name')
    list_filter = ('category',)
    ordering = ('name',)


@admin.register(ProductImage)
class ProductImageAdmin(ModelAdmin):
    list_display = ('product', 'is_thumbnail')
    list_filter = ('is_thumbnail',)
    search_fields = ('product__name',)