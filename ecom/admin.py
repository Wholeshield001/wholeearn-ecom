from django.contrib import admin
from .models import Cart, CartItem, Order, OrderItem
from unfold.admin import ModelAdmin


@admin.register(Cart)
class CartAdmin(ModelAdmin):
    list_display = ('id', 'user', 'session_id', 'created_at', 'get_item_count')
    list_filter = ('created_at',)
    search_fields = ('user__email', 'session_id')
    readonly_fields = ('id', 'created_at', 'updated_at')

    def get_item_count(self, obj):
        return obj.get_item_count()
    get_item_count.short_description = "Item Count"


@admin.register(CartItem)
class CartItemAdmin(ModelAdmin):
    list_display = ('id', 'cart', 'product', 'quantity', 'price', 'get_total_price')
    list_filter = ('created_at', 'product')
    search_fields = ('product__name', 'cart__user__email')
    readonly_fields = ('id', 'created_at', 'updated_at')

    def get_total_price(self, obj):
        return f"${obj.get_total_price()}"
    get_total_price.short_description = "Total Price"


@admin.register(Order)
class OrderAdmin(ModelAdmin):
    list_display = ('id', 'user', 'total_amount', 'status', 'payment_status', 'created_at')
    list_filter = ('status', 'payment_status', 'created_at')
    search_fields = ('user__email', 'payment_reference', 'paystack_reference', 'shipping_phone')
    readonly_fields = ('id', 'payment_reference', 'paystack_reference', 'created_at', 'updated_at')
    fieldsets = (
        ('Order Information', {
            'fields': ('id', 'user', 'total_amount', 'status', 'payment_status')
        }),
        ('Payment Details', {
            'fields': ('payment_reference', 'paystack_reference')
        }),
        ('Shipping Information', {
            'fields': ('shipping_address', 'shipping_city', 'shipping_state', 'shipping_phone')
        }),
        ('Tracking', {
            'fields': ('tracking_number', 'tracking_notes')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    ordering = ('-created_at',)


@admin.register(OrderItem)
class OrderItemAdmin(ModelAdmin):
    list_display = ('id', 'order', 'product_name', 'quantity', 'price', 'get_total_price')
    list_filter = ('order__status', 'order__created_at')
    search_fields = ('product_name', 'product_sku', 'order__user__email')
    readonly_fields = ('id',)
    
    def get_total_price(self, obj):
        return f"₦{obj.get_total_price()}"
    get_total_price.short_description = "Total Price"

