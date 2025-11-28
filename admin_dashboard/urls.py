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

    path('products/', views.products_page, name='admin_products'),
    path('notifications/', views.notifications_page, name='admin_notifications'),
    path('wholesalers/', views.wholesalers_page, name='admin_wholesalers'),
    path('retailers/', views.retailers_page, name='admin_retailers'),
]