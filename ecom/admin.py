from django.contrib import admin
from .models import (
    Cart,
    CartItem,
    Order,
    OrderItem,
    RewardPointConfig,
    RewardPointLedger,
    PaymentProviderConfig,
    UserWallet,
    RewardConversion,
    WalletBankAccount,
    WalletWithdrawalRequest,
)
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
    readonly_fields = ('id', 'payment_reference', 'paystack_reference', 'created_at', 'updated_at', 'speedaf_label_link')
    fieldsets = (
        ('Order Information', {
            'fields': ('id', 'user', 'total_amount', 'status', 'payment_status')
        }),
        ('Payment Details', {
            'fields': ('payment_reference', 'paystack_reference')
        }),
        ('Shipping Information', {
            'fields': ('shipping_fee', 'shipping_address', 'shipping_city', 'shipping_state', 'shipping_phone')
        }),
        ('Tracking', {
            'fields': ('speedaf_order_id', 'tracking_number', 'tracking_notes', 'speedaf_label_link')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    ordering = ('-created_at',)
    actions = ['create_speedaf_shipment']

    def speedaf_label_link(self, obj):
        if obj.tracking_number:
            from .services.speedaf import SpeedAFClient
            client = SpeedAFClient()
            url = client.get_waybill_label(obj.tracking_number)
            if url:
                from django.utils.html import format_html
                return format_html('<a href="{}" target="_blank">Download Label</a>', url)
        return "-"
    speedaf_label_link.short_description = "SpeedAF Label"

    def create_speedaf_shipment(self, request, queryset):
        from .services.speedaf import SpeedAFClient
        client = SpeedAFClient()
        success_count = 0
        for order in queryset:
            if not order.speedaf_order_id:
                speedaf_id, waybill = client.create_shipping_order(order)
                if speedaf_id:
                    order.speedaf_order_id = speedaf_id
                    if waybill:
                        order.tracking_number = waybill
                    order.save()
                    success_count += 1
        self.message_user(request, f"Successfully created {success_count} SpeedAF shipments.")
    create_speedaf_shipment.short_description = "Create SpeedAF Shipment"


@admin.register(OrderItem)
class OrderItemAdmin(ModelAdmin):
    list_display = ('id', 'order', 'product_name', 'quantity', 'price', 'get_total_price')
    list_filter = ('order__status', 'order__created_at')
    search_fields = ('product_name', 'product_sku', 'order__user__email')
    readonly_fields = ('id',)
    
    def get_total_price(self, obj):
        return f"₦{obj.get_total_price()}"
    get_total_price.short_description = "Total Price"


@admin.register(RewardPointConfig)
class RewardPointConfigAdmin(ModelAdmin):
    list_display = (
        'points_per_purchase',
        'referral_bonus_points',
        'points_to_naira_rate',
        'minimum_withdrawal_amount',
        'updated_by',
        'updated_at',
    )
    readonly_fields = ('updated_at',)


@admin.register(RewardPointLedger)
class RewardPointLedgerAdmin(ModelAdmin):
    list_display = ('user', 'points', 'reason', 'order', 'created_at')
    list_filter = ('reason', 'created_at')
    search_fields = ('user__email',)
    readonly_fields = ('created_at',)


@admin.register(PaymentProviderConfig)
class PaymentProviderConfigAdmin(ModelAdmin):
    list_display = ('active_provider', 'updated_by', 'updated_at')
    readonly_fields = ('updated_at',)


@admin.register(UserWallet)
class UserWalletAdmin(ModelAdmin):
    list_display = ('user', 'available_balance', 'pending_balance', 'total_converted', 'total_withdrawn', 'updated_at')
    search_fields = ('user__email',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(RewardConversion)
class RewardConversionAdmin(ModelAdmin):
    list_display = ('reference', 'user', 'points', 'naira_amount', 'rate_snapshot', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('reference', 'user__email')
    readonly_fields = ('created_at',)


@admin.register(WalletBankAccount)
class WalletBankAccountAdmin(ModelAdmin):
    list_display = ('user', 'account_name', 'account_number', 'bank_code', 'is_verified', 'is_default', 'is_active', 'updated_at')
    list_filter = ('is_verified', 'is_default', 'is_active', 'updated_at')
    search_fields = ('user__email', 'account_number', 'account_name', 'bank_code')
    readonly_fields = ('created_at', 'updated_at', 'verified_at')


@admin.register(WalletWithdrawalRequest)
class WalletWithdrawalRequestAdmin(ModelAdmin):
    list_display = ('reference', 'user', 'amount', 'status', 'monnify_reference', 'created_at', 'processed_at')
    list_filter = ('status', 'created_at', 'processed_at')
    search_fields = ('reference', 'user__email', 'monnify_reference')
    readonly_fields = ('created_at', 'updated_at', 'processed_at')

