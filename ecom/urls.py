from django.urls import path
from .views import (
    home, products, product_detail, add_to_cart, view_cart,
    update_cart_item, remove_from_cart, checkout, get_cart_drawer,
    process_checkout, verify_payment, retry_payment, order_confirmation, user_orders, order_detail,
    blog_list, blog_detail, terms_of_service, privacy_policy, return_policy, delivery_policy,
    monnify_transfer_webhook,
    get_shipping_quote, htmx_speedaf_cities
)

urlpatterns = [
    path('', home, name='home'),
    path('products/', products, name='products'),
    path('products/<uuid:product_id>/', product_detail, name='product-detail'),
    path('cart/add/<uuid:product_id>/', add_to_cart, name='add-to-cart'),
    path('cart/', view_cart, name='view-cart'),
    path('cart/drawer/', get_cart_drawer, name='get-cart-drawer'),
    path('cart/update/<uuid:item_id>/', update_cart_item, name='update-cart-item'),
    path('cart/remove/<uuid:item_id>/', remove_from_cart, name='remove-from-cart'),
    path('checkout/', checkout, name='checkout'),
    path('checkout/shipping-quote/', get_shipping_quote, name='get-shipping-quote'),
    path('checkout/speedaf-cities/', htmx_speedaf_cities, name='htmx-speedaf-cities'),
    path('checkout/process/', process_checkout, name='process-checkout'),
    path('checkout/verify/', verify_payment, name='verify-payment'),
    path('webhooks/monnify/transfer/', monnify_transfer_webhook, name='monnify-transfer-webhook'),
    path('checkout/retry/<uuid:order_id>/', retry_payment, name='retry-payment'),
    path('order/confirmation/<uuid:order_id>/', order_confirmation, name='order-confirmation'),
    path('orders/', user_orders, name='user-orders'),
    path('orders/<uuid:order_id>/', order_detail, name='order-detail'),
    path('blog/', blog_list, name='blog'),
    path('blog/<slug:slug>/', blog_detail, name='blog-detail'),
    path('terms-of-service/', terms_of_service, name='terms-of-service'),
    path('privacy-policy/', privacy_policy, name='privacy-policy'),
    path('return-policy/', return_policy, name='return-policy'),
    path('delivery-policy/', delivery_policy, name='delivery-policy'),
]
