from django.contrib import admin
from .models import Category, Product, ProductImage, BlogCategory, BlogPost
from unfold.admin import ModelAdmin

# Register your models here.


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ('name', 'description', 'created_at', 'updated_at')
    search_fields = ('name',)
    ordering = ('name',)

@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ('name', 'category', 'price', 'stock', 'is_best_seller', 'created_at', 'updated_at')
    search_fields = ('name', 'category__name')
    list_filter = ('category', 'is_best_seller')
    ordering = ('name',)


@admin.register(ProductImage)
class ProductImageAdmin(ModelAdmin):
    list_display = ('product', 'is_thumbnail')
    list_filter = ('is_thumbnail',)
    search_fields = ('product__name',)


@admin.register(BlogCategory)
class BlogCategoryAdmin(ModelAdmin):
    list_display = ('name', 'slug', 'created_at')
    search_fields = ('name', 'slug')
    # list_filter = ()


@admin.register(BlogPost)
class BlogPostAdmin(ModelAdmin):
    list_display = ('title', 'category', 'is_published', 'author', 'created_at')
    list_filter = ('is_published', 'category')
    search_fields = ('title', 'slug')