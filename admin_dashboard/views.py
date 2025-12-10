from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
import sys
from django.http import HttpResponse
from .forms import (AdminLoginForm,
                    ForgotPasswordForm, 
                    VerifyOTPForm, 
                    ResetPasswordForm, 
                    ProductForm, 
                    ProductImageForm, 
                    CategoryForm)
from users.models import User
from django.http import JsonResponse
from .models import Product, Category, ProductImage
from django.db.models import Count
from django.db.models.functions import TruncMonth
from datetime import datetime
import json





def admin_login(request):
    # Redirect if already logged in as admin
    if request.user.is_authenticated and request.user.role == User.ADMINISTRATOR:
        return redirect('admin_dashboard')
    
    if request.method == 'POST':
        form = AdminLoginForm(request=request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            
            # Handle remember me
            if not form.cleaned_data.get('remember_me'):
                request.session.set_expiry(0)
            
            messages.success(request, f'Welcome back, {user.first_name or user.email}!')
            
            # Redirect to next or dashboard
            next_url = request.GET.get('next', 'admin_dashboard')
            return redirect(next_url)
    else:
        form = AdminLoginForm()
    
    return render(request, 'admin_dashboard/admin_login.html', {'form': form})


def admin_logout(request):
    logout(request)
    messages.info(request, 'You have been logged out successfully.')
    return redirect('admin_login')


@login_required(login_url='admin_login')
def admin_dashboard(request):
    # Verify user is admin
    if request.user.role != User.ADMINISTRATOR or not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('admin_login')
    
    context = {
        'user': request.user,
    }
    return render(request, 'admin_dashboard/dashboard.html', context)


def forgot_password(request):
    if request.method == 'POST':
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            user = User.objects.get(email=email, role=User.ADMINISTRATOR, is_staff=True)
            
            # Generate OTP
            otp = user.generate_reset_otp()
            
            # Log OTP to terminal
            print("\n" + "="*50, flush=True)
            print(f"PASSWORD RESET OTP FOR {email}", flush=True)
            print(f"OTP: {otp}", flush=True)
            print(f"This code will expire in 10 minutes.", flush=True)
            print("="*50 + "\n", flush=True)
            sys.stdout.flush()
            
            messages.success(request, f'OTP has been generated. Check your terminal.')
            # Store email in session for next step
            request.session['reset_email'] = email
            return redirect('verify_otp')
    else:
        form = ForgotPasswordForm()
    
    return render(request, 'admin_dashboard/forgot_password.html', {'form': form})


def verify_otp(request):
    email = request.session.get('reset_email')
    if not email:
        messages.error(request, 'Please start the password reset process again.')
        return redirect('forgot_password')
    
    if request.method == 'POST':
        form = VerifyOTPForm(request.POST)
        if form.is_valid():
            otp = form.get_otp()
            print(f"\n[DEBUG] Attempting to verify OTP: {otp} for {email}", flush=True)
            try:
                user = User.objects.get(email=email)
                if user.verify_reset_otp(otp):
                    # Store token in session
                    request.session['reset_token'] = user.reset_token
                    print(f"[DEBUG] OTP verified successfully for {email}", flush=True)
                    messages.success(request, 'OTP verified successfully!')
                    return redirect('reset_password')
                else:
                    print(f"[DEBUG] OTP verification failed for {email}", flush=True)
                    messages.error(request, 'Invalid or expired OTP. Please try again.')
            except User.DoesNotExist:
                print(f"[DEBUG] User not found: {email}", flush=True)
                messages.error(request, 'User not found.')
                return redirect('forgot_password')
    else:
        form = VerifyOTPForm()
    
    context = {
        'form': form,
        'email': email
    }
    return render(request, 'admin_dashboard/verify_otp.html', context)


def resend_otp(request):
    email = request.session.get('reset_email')
    if not email:
        messages.error(request, 'Please start the password reset process again.')
        return redirect('forgot_password')
    
    try:
        user = User.objects.get(email=email, role=User.ADMINISTRATOR, is_staff=True)
        otp = user.generate_reset_otp()
        
        # Log OTP to terminal
        print("\n" + "="*50, flush=True)
        print(f"RESENT PASSWORD RESET OTP FOR {email}", flush=True)
        print(f"OTP: {otp}", flush=True)
        print(f"This code will expire in 10 minutes.", flush=True)
        print("="*50 + "\n", flush=True)
        sys.stdout.flush()
        
        messages.success(request, 'OTP has been resent. Check your terminal.')
    except Exception as e:
        print(f"[ERROR] Failed to resend OTP: {str(e)}", flush=True)
        messages.error(request, 'Failed to resend OTP.')
    
    return redirect('verify_otp')


def reset_password(request):
    reset_token = request.session.get('reset_token')
    email = request.session.get('reset_email')
    
    if not reset_token or not email:
        messages.error(request, 'Invalid password reset session.')
        return redirect('forgot_password')
    
    try:
        user = User.objects.get(email=email, reset_token=reset_token)
    except User.DoesNotExist:
        messages.error(request, 'Invalid password reset session.')
        return redirect('forgot_password')
    
    if request.method == 'POST':
        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            new_password = form.cleaned_data['new_password']
            user.set_password(new_password)
            user.clear_reset_data()
            
            # Clear session data
            del request.session['reset_token']
            del request.session['reset_email']
            
            print(f"[SUCCESS] Password successfully reset for {email}", flush=True)
            
            # Redirect to success page instead of login
            return redirect('password_reset_success')
    else:
        form = ResetPasswordForm()
    
    return render(request, 'admin_dashboard/reset_password.html', {'form': form})


def password_reset_success(request):
    return render(request, 'admin_dashboard/password_reset_success.html')


def products_page(request):
    return render(request, 'admin_dashboard/products.html')

def notifications_page(request):
    return render(request, 'admin_dashboard/notifications.html')

def wholesalers_page(request):
    return render(request, 'admin_dashboard/wholesalers.html')


def retailers_page(request):
    return render(request, 'admin_dashboard/retailer.html')





# ...existing code...

@login_required(login_url='admin_login')
def products_page(request):
    products = Product.objects.all().order_by('-created_at')
    return render(request, 'admin_dashboard/products.html', {'products': products})

@login_required(login_url='admin_login')
def add_product(request):
    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES)
        
        if form.is_valid():
            product = form.save()
            
            # Handle multiple image uploads (optional)
            uploaded_images = request.FILES.getlist("images")
            
            image_objects = []
            for img in uploaded_images:
                image_obj = ProductImage.objects.create(product=product, image=img)
                image_objects.append(image_obj)
            
            # Handle manually selected thumbnail
            thumb_index_str = request.POST.get("thumbnail_image", "")
            
            if thumb_index_str and thumb_index_str.isdigit() and image_objects:
                thumb_index = int(thumb_index_str)
                if 0 <= thumb_index < len(image_objects):
                    thumbnail_image_obj = image_objects[thumb_index]
                    thumbnail_image_obj.is_thumbnail = True
                    thumbnail_image_obj.save()
                    product.thumbnail = thumbnail_image_obj
                    product.save()
            elif image_objects:
                # Set first image as thumbnail if none selected
                first_image = image_objects[0]
                first_image.is_thumbnail = True
                first_image.save()
                product.thumbnail = first_image
                product.save()
            
            messages.success(request, 'Product added successfully!')
            return redirect("admin_products")
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ProductForm()
    
    return render(request, "admin_dashboard/add_product.html", {
        "form": form,
    })


@login_required(login_url='admin_login')
def edit_product(request, product_id):
    """View and edit product details"""
    product = get_object_or_404(Product, id=product_id)
    categories = Category.objects.all()
    
    if request.method == 'POST':
        # Handle set thumbnail via AJAX
        if 'set_thumbnail_id' in request.POST:
            thumbnail_id = request.POST.get('set_thumbnail_id')
            try:
                image = ProductImage.objects.get(id=thumbnail_id, product=product)
                product.thumbnail = image
                product.save()
                return JsonResponse({'success': True, 'message': 'Thumbnail updated'})
            except ProductImage.DoesNotExist:
                return JsonResponse({'success': False, 'message': 'Image not found'}, status=400)
        
        # Handle delete image via AJAX
        if 'delete_image_id' in request.POST:
            image_id = request.POST.get('delete_image_id')
            try:
                image = ProductImage.objects.get(id=image_id, product=product)
                # If this is the thumbnail, unset it
                if product.thumbnail == image:
                    product.thumbnail = None
                    product.save()
                image.delete()
                return JsonResponse({'success': True, 'message': 'Image deleted'})
            except ProductImage.DoesNotExist:
                return JsonResponse({'success': False, 'message': 'Image not found'}, status=400)
        
        # Handle regular form submission (product details + new images)
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            
            # Handle new images upload
            new_images = request.FILES.getlist('new_images')
            if new_images:
                for image_file in new_images:
                    ProductImage.objects.create(
                        product=product,
                        image=image_file,
                        is_thumbnail=False
                    )
            
            messages.success(request, 'Product updated successfully!')
            return redirect('admin_products')
    else:
        form = ProductForm(instance=product)
    
    context = {
        'product': product,
        'form': form,
        'categories': categories,
        'page_title': product.name,
    }
    return render(request, 'admin_dashboard/product_details.html', context)



@login_required(login_url='admin_login')
def delete_product(request, product_id):
    if request.method == 'DELETE':
        product = get_object_or_404(Product, id=product_id)
        product.delete()
        return JsonResponse({'success': True, 'message': 'Product deleted successfully'})
    return JsonResponse({'success': False, 'message': 'Invalid request'}, status=400)


# Category Views
@login_required(login_url='admin_login')
def categories_page(request):
    categories = Category.objects.all().order_by('-created_at')
    return render(request, 'admin_dashboard/categories.html', {'categories': categories})

@login_required(login_url='admin_login')
def add_category(request):
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save()
            messages.success(request, f'Category {category.name} created successfully!')
            # HTMX-friendly redirect to reload the categories list
            resp = HttpResponse('')
            resp['HX-Redirect'] = reverse('admin_categories')
            return resp
        # Return the form partial with errors (HTTP 200 so HTMX can swap it)
        return render(request, 'partials/admin_dashboard/category_form.html', {'form': form})
    # GET: serve empty form partial
    form = CategoryForm()
    return render(request, 'partials/admin_dashboard/category_form.html', {'form': form})


@login_required(login_url='admin_login')
def edit_category(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, 'Category updated successfully!')
            return redirect('admin_categories')
    else:
        form = CategoryForm(instance=category)
    return render(request, 'admin_dashboard/partials/category_form.html', {'form': form, 'category': category})

@login_required(login_url='admin_login')
def delete_category(request, category_id):
    if request.method == 'DELETE':
        category = get_object_or_404(Category, id=category_id)
        category.delete()
        return JsonResponse({'success': True, 'message': 'Category deleted successfully'})
    return JsonResponse({'success': False, 'message': 'Invalid request'}, status=400)


@login_required(login_url='admin_login')
def orders_page(request):
    """Orders management page"""
    context = {
        'page_title': 'Orders',
    }
    return render(request, 'admin_dashboard/orders.html', context)


@login_required(login_url='admin_login')
def analytics_page(request):
    """Analytics dashboard page"""
    
    # Get current year
    current_year = datetime.now().year
    
    # Calculate monthly user sign-ups for current year
    monthly_data = User.objects.filter(
        date_joined__year=current_year
    ).annotate(
        month=TruncMonth('date_joined')
    ).values('month').annotate(
        count=Count('id')
    ).order_by('month')
    
    # Create array with 12 months (Jan-Dec), default 0
    monthly_signups = [0] * 12
    for data in monthly_data:
        month_index = data['month'].month - 1  # 0-indexed
        monthly_signups[month_index] = data['count']
    
    # Total users count
    total_users = User.objects.count()
    
    context = {
        'page_title': 'Analytics',
        'monthly_signups': json.dumps(monthly_signups),
        'current_year': current_year,
        'total_users': total_users,
    }
    return render(request, 'admin_dashboard/analytics.html', context)

@login_required(login_url='admin_login')
def customers_page(request):
    """Customers management page"""
    # Get all customers (users with CUSTOMER role)
    customers = User.objects.all().order_by('-date_joined')
    
    # Calculate stats (you can add real calculations later)
    total_customers = 164
    wholesalers = 64
    retailers = 100
    basic_customers = 12250
    
    context = {
        'page_title': 'Customers',
        'customers': customers,
        'total_customers': total_customers,
        'wholesalers': wholesalers,
        'retailers': retailers,
        'basic_customers': basic_customers,
        'total_customers': customers.count(),
    }
    return render(request, 'admin_dashboard/customers.html', context)