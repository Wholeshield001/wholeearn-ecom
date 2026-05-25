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
    path('admins/', views.admin_admins, name='admin_admins'),
    path('profile/', views.admin_profile, name='admin_profile'),
    path('reward-settings/', views.reward_settings, name='admin_reward_settings'),
    path('reward-withdrawals/', views.reward_withdrawals_page, name='admin_reward_withdrawals'),
    path('reward-withdrawals/export/', views.export_reward_withdrawals_csv, name='admin_export_reward_withdrawals'),
    path('reward-withdrawals/<uuid:withdrawal_id>/retry/', views.retry_reward_withdrawal, name='admin_retry_reward_withdrawal'),
    path('payment-settings/', views.payment_settings, name='admin_payment_settings'),
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
    path('products/export/', views.export_products_csv, name='admin_export_products'),


    # Add to admin_dashboard/urls.py

    # Product Image Management# Update admin_dashboard/urls.py - replace the image management paths with:
    path('products/<uuid:product_id>/images/set-thumbnail/<uuid:image_id>/', views.set_product_thumbnail, name='set_product_thumbnail'),
    path('products/<uuid:product_id>/images/delete/<uuid:image_id>/', views.delete_product_image, name='delete_product_image'),
    path('products/<uuid:product_id>/images/add/', views.add_product_images, name='add_product_images'),


    # Notifications
    path('notifications/', views.notifications_page, name='admin_notifications'),
    path('notifications/<str:notification_type>/<uuid:notification_id>/delete/', views.delete_notification, name='delete_notification'),


    path('wholesalers/', views.wholesalers_page, name='admin_wholesalers'),
    path('wholesalers/<uuid:wholesaler_id>/detail/', views.wholesaler_detail, name='wholesaler_detail'),
    path('wholesalers/export/', views.export_wholesalers_csv, name='admin_export_wholesalers'),
    path('retailers/', views.retailers_page, name='admin_retailers'),
    path('retailers/<uuid:retailer_id>/detail/', views.retailer_detail, name='retailer_detail'),
    path('retailers/export/', views.export_retailers_csv, name='admin_export_retailers'),
    path('hospitals/', views.hospitals_page, name='admin_hospitals'),
    path('hospitals/<uuid:hospital_id>/detail/', views.hospital_detail, name='hospital_detail'),
    path('hospitals/export/', views.export_hospitals_csv, name='admin_export_hospitals'),
    path('pharmacies/', views.pharmacy_page, name='admin_pharmacies'),
    path('pharmacies/<uuid:pharmacy_id>/detail/', views.pharmacy_detail, name='pharmacy_detail'),
    path('pharmacies/export/', views.export_pharmacies_csv, name='admin_export_pharmacies'),
    # path('products/add/', views.add_product, name='add_product'),

    # Analytics
    path('analytics/', views.analytics_page, name='admin_analytics'),
    path('analytics/website-visits/', views.website_visits_page, name='admin_website_visits'),
    path('analytics/website-visits/export/', views.export_website_visits_csv, name='admin_export_website_visits'),


    # Orders
    path('orders/', views.orders_page, name='admin_orders'),
    path('orders/export/', views.export_orders_csv, name='admin_export_orders'),
    path('orders/<uuid:order_id>/detail/', views.order_detail, name='admin_order_detail'),
    path('orders/<uuid:order_id>/tracking/', views.orders_tracking, name='admin_order_tracking'),
    path('orders/tracking/', views.orders_tracking, name='admin_orders_tracking'),
    path('orders/<uuid:order_id>/delete/', views.delete_order, name='admin_delete_order'),
    path('orders/<uuid:order_id>/cancel/', views.cancel_order, name='admin_cancel_order'),

    # Tickets
    path('tickets/', views.tickets_page, name='admin_tickets'),
    path('tickets/<uuid:ticket_id>/', views.ticket_detail, name='admin_ticket_detail'),

    # Customers
    path('customers/', views.customers_page, name='admin_customers'),
    path('customers/<uuid:user_id>/detail/', views.user_detail, name='user_detail'),
    path('users/<uuid:user_id>/delete/', views.delete_user_admin, name='admin_delete_user'),

    # End Users (regular customers)
    path('end-users/', views.end_users_page, name='admin_end_users'),
    path('end-users/export/', views.export_end_users_csv, name='admin_export_end_users'),

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

    # KYC Submissions
    path('kyc-submissions/', views.kyc_submissions, name='kyc-submissions'),
    path('kyc-submissions/<uuid:submission_id>/', views.kyc_detail, name='kyc-detail'),
]