from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.admin_login, name='admin_login'),
    path('logout/', views.admin_logout, name='admin_logout'),
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('verify-otp/', views.verify_otp, name='verify_otp'),
    path('resend-otp/', views.resend_otp, name='resend_otp'),
    path('reset-password/', views.reset_password, name='reset_password'),
    path('password-reset-success/', views.password_reset_success, name='password_reset_success'),
    path('', views.admin_dashboard, name='admin_dashboard'),

    # Categories
    path('categories/', views.categories_page, name='admin_categories'),
    path('categories/add/', views.add_category, name='add_category'),
    path('categories/<uuid:category_id>/edit/', views.edit_category, name='edit_category'),
    path('categories/<uuid:category_id>/delete/', views.delete_category, name='delete_category'),
    
    # Products
    path('products/', views.products_page, name='admin_products'),
    path('products/add/', views.add_product, name='add_product'),
    path('products/<uuid:product_id>/delete/', views.delete_product, name='delete_product'),
    path('products/<uuid:product_id>/edit/', views.edit_product, name='edit_product'),


    # Add to admin_dashboard/urls.py

    # Product Image Management# Update admin_dashboard/urls.py - replace the image management paths with:
    path('products/<uuid:product_id>/images/set-thumbnail/<uuid:image_id>/', views.set_product_thumbnail, name='set_product_thumbnail'),
    path('products/<uuid:product_id>/images/delete/<uuid:image_id>/', views.delete_product_image, name='delete_product_image'),
    path('products/<uuid:product_id>/images/add/', views.add_product_images, name='add_product_images'),


    # Notifications
    path('notifications/', views.notifications_page, name='admin_notifications'),


    path('wholesalers/', views.wholesalers_page, name='admin_wholesalers'),
    path('wholesalers/<uuid:wholesaler_id>/detail/', views.wholesaler_detail, name='wholesaler_detail'),
    path('retailers/', views.retailers_page, name='admin_retailers'),
    path('retailers/<uuid:distributor_id>/detail/', views.distributor_detail, name='distributor_detail'),
    # path('products/add/', views.add_product, name='add_product'),

    # Analytics
    path('analytics/', views.analytics_page, name='admin_analytics'),


    # Orders
    path('orders/', views.orders_page, name='admin_orders'),
    path('orders/<uuid:order_id>/detail/', views.order_detail, name='admin_order_detail'),
    path('orders/tracking/', views.orders_tracking, name='admin_orders_tracking'),
    path('orders/<uuid:order_id>/delete/', views.delete_order, name='admin_delete_order'),
    path('orders/<uuid:order_id>/cancel/', views.cancel_order, name='admin_cancel_order'),

    # Tickets
    path('tickets/', views.tickets_page, name='admin_tickets'),
    path('tickets/<uuid:ticket_id>/', views.ticket_detail, name='admin_ticket_detail'),

    # Customers
    path('customers/', views.customers_page, name='admin_customers'),
    path('customers/<uuid:user_id>/detail/', views.user_detail, name='user_detail'),

    # Blog
    path('blog/', views.blog_list, name='admin_blog_list'),
    path('blog/add/', views.blog_add, name='admin_blog_add'),
    path('blog/<uuid:post_id>/edit/', views.blog_edit, name='admin_blog_edit'),
    path('blog/<uuid:post_id>/delete/', views.blog_delete, name='admin_blog_delete'),
    path('blog/<uuid:post_id>/toggle-publish/', views.blog_toggle_publish, name='admin_blog_toggle_publish'),

    # Blog Categories
    path('blog/categories/', views.blog_categories_page, name='admin_blog_categories'),
    path('blog/categories/add/', views.add_blog_category, name='add_blog_category'),
    path('blog/categories/<uuid:category_id>/edit/', views.edit_blog_category, name='edit_blog_category'),
    path('blog/categories/<uuid:category_id>/delete/', views.delete_blog_category, name='delete_blog_category'),
]