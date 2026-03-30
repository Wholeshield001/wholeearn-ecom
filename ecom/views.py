from django.shortcuts import render, get_object_or_404, redirect
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from admin_dashboard.models import Product, Category, BlogPost, BlogCategory
from .models import Cart, CartItem


def home(request):
    # Show marked best sellers; fallback to latest
    bestsellers = Product.objects.filter(is_best_seller=True).order_by('-created_at')[:8]
    if not bestsellers:
        bestsellers = Product.objects.order_by('-created_at')[:8]
    return render(request, 'ecommerce/home.html', {'bestsellers': bestsellers})


@require_http_methods(["GET"])
def products(request):
    """Display all products with filtering and pagination"""
    products_list = Product.objects.all().order_by('-created_at')
    
    # Filter by category if provided and not empty
    category_id = request.GET.get('category', '').strip()
    if category_id:
        try:
            products_list = products_list.filter(category_id=category_id)
        except Exception as e:
            # If UUID is invalid, just show all products
            pass
    
    # Filter by gender
    gender_filter = request.GET.get('gender', '').strip().lower()
    if gender_filter == 'men':
        products_list = products_list.filter(is_male=True)
    elif gender_filter == 'women':
        products_list = products_list.filter(is_female=True)
    
    # Search functionality
    search_query = request.GET.get('q', '').strip()
    if search_query:
        products_list = products_list.filter(name__icontains=search_query)
    
    # Pagination: 12 products per page
    paginator = Paginator(products_list, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get all categories for filter
    categories = Category.objects.all().order_by('name')
    
    # Partial rendering modes
    is_htmx = request.headers.get('HX-Request') == 'true'
    is_partial_cards = request.GET.get('partial') == '1'
    
    if is_partial_cards:
        # Return only product cards for infinite scroll appends
        return render(
            request,
            'partials/ecommerce/product_cards.html',
            {
                'products': page_obj.object_list,
            }
        )
    
    if is_htmx:
        # HTMX filter/search updates: return full grid partial
        return render(
            request,
            'partials/ecommerce/products_grid.html',
            {
                'page_obj': page_obj,
                'products': page_obj.object_list,
                'search_query': search_query,
                'selected_category': category_id if category_id else None,
                'gender_filter': gender_filter if gender_filter else None,
            }
        )
    
    context = {
        'page_obj': page_obj,
        'products': page_obj.object_list,
        'categories': categories,
        'search_query': search_query,
        'selected_category': category_id if category_id else None,
        'gender_filter': gender_filter if gender_filter else None,
    }
    return render(request, 'ecommerce/products.html', context)


@require_http_methods(["GET"])
def product_detail(request, product_id):
    """Display product detail page"""
    product = get_object_or_404(Product, id=product_id)
    
    # Get related products from the same category
    related_products = Product.objects.filter(
        category=product.category
    ).exclude(id=product_id).order_by('-created_at')[:5]
    
    # Get minimum quantity based on user role
    min_quantity = 1
    if request.user.is_authenticated:
        min_quantity = product.get_min_quantity_for_role(request.user.role)
    
    context = {
        'product': product,
        'related_products': related_products,
        'min_quantity': min_quantity,
    }
    return render(request, 'ecommerce/product_detail.html', context)


def get_or_create_cart(request):
    """Get or create a cart for the user (authenticated or anonymous)."""
    if request.user.is_authenticated:
        cart, created = Cart.objects.get_or_create(user=request.user)
    else:
        # Use session ID for anonymous users
        session_id = request.session.session_key
        if not session_id:
            request.session.create()
            session_id = request.session.session_key
        cart, created = Cart.objects.get_or_create(session_id=session_id)
    return cart


@require_http_methods(["POST"])
def add_to_cart(request, product_id):
    """Add a product to the cart."""
    product = get_object_or_404(Product, id=product_id)
    
    # Get quantity from POST
    quantity = int(request.POST.get('quantity', 1))
    if quantity < 1:
        quantity = 1
    
    # Get user role for minimum quantity validation
    user_role = None
    role_display = "End User"
    min_quantity = 1
    if request.user.is_authenticated:
        user_role = request.user.role
        min_quantity = product.get_min_quantity_for_role(user_role)
        # Get role display name
        role_display = dict(request.user.ROLE_CHOICES).get(user_role, "End User")
    
    # Validate minimum quantity requirement
    if quantity < min_quantity:
        error_msg = f"As a {role_display}, the minimum quantity for {product.name} is {min_quantity} items."
        if request.headers.get('HX-Request') == 'true':
            return JsonResponse({'success': False, 'message': error_msg}, status=400)
        messages.error(request, error_msg, extra_tags='cart')
        return redirect('product-detail', product_id=product_id)
    
    # Validate stock
    if product.stock < quantity:
        error_msg = f"Only {product.stock} items available in stock. You need at least {min_quantity} items (as a {role_display})."
        if request.headers.get('HX-Request') == 'true':
            return JsonResponse({'success': False, 'message': error_msg}, status=400)
        messages.error(request, error_msg, extra_tags='cart')
        return redirect('product-detail', product_id=product_id)
    
    # Get or create cart
    cart = get_or_create_cart(request)
    
    # Add or update cart item
    cart_item, created = CartItem.objects.get_or_create(
        cart=cart,
        product=product,
        defaults={'price': product.price, 'quantity': quantity}
    )
    
    if not created:
        # Item already in cart, update quantity
        new_quantity = cart_item.quantity + quantity
        if new_quantity < min_quantity:
            error_msg = f"Total quantity must be at least {min_quantity} items (minimum for {role_display}). Currently you have {cart_item.quantity} in cart."
            if request.headers.get('HX-Request') == 'true':
                return JsonResponse({'success': False, 'message': error_msg}, status=400)
            messages.error(request, error_msg, extra_tags='cart')
            return redirect('product-detail', product_id=product_id)
        if new_quantity <= product.stock:
            cart_item.quantity = new_quantity
            cart_item.save()
        else:
            error_msg = f"Cannot add {quantity} more items. Only {product.stock - cart_item.quantity} available. Minimum required is {min_quantity} items (as a {role_display})."
            if request.headers.get('HX-Request') == 'true':
                return JsonResponse({'success': False, 'message': error_msg}, status=400)
            messages.error(request, error_msg, extra_tags='cart')
            return redirect('product-detail', product_id=product_id)
    
    # Check if HTMX request, return JSON
    if request.headers.get('HX-Request') == 'true':
        return JsonResponse({
            'success': True,
            'item_count': cart.get_item_count(),
            'message': f"{product.name} added to cart!"
        })
    
    messages.success(request, f"{product.name} added to cart!", extra_tags='cart')
    return redirect('product-detail', product_id=product_id)


@require_http_methods(["GET"])
def view_cart(request):
    """Redirect to home page - cart is now a drawer sidebar."""
    return redirect('home')


@require_http_methods(["POST"])
def update_cart_item(request, item_id):
    """Update quantity of a cart item."""
    cart_item = get_object_or_404(CartItem, id=item_id)
    
    # Check authorization
    cart = get_or_create_cart(request)
    if cart_item.cart != cart:
        if request.headers.get('HX-Request') == 'true':
            return JsonResponse({'success': False, 'message': 'Unauthorized action.'}, status=403)
        messages.error(request, "Unauthorized action.", extra_tags='cart')
        return redirect('view-cart')
    
    quantity = int(request.POST.get('quantity', 1))
    
    if quantity < 1:
        # Delete item if quantity is 0 or negative
        cart_item.delete()
        messages.success(request, "Item removed from cart.", extra_tags='cart')
    elif quantity > cart_item.product.stock:
        messages.error(request, f"Only {cart_item.product.stock} items available.", extra_tags='cart')
    else:
        cart_item.quantity = quantity
        cart_item.save()
        messages.success(request, "Cart updated.", extra_tags='cart')
    
    if request.headers.get('HX-Request') == 'true':
        context = {
            'cart_items': cart.items.all(),
            'cart_total': cart.get_total_price(),
            'cart_item_count': cart.get_item_count(),
        }
        return render(request, 'partials/ecommerce/cart_drawer_content.html', context)
    
    # Redirect back to the referring page with cart=open parameter
    next_url = request.META.get('HTTP_REFERER', '/')
    separator = '&' if '?' in next_url else '?'
    return redirect(next_url + separator + 'cart=open')


@require_http_methods(["POST"])
def remove_from_cart(request, item_id):
    """Remove an item from the cart."""
    cart_item = get_object_or_404(CartItem, id=item_id)
    
    # Check authorization
    cart = get_or_create_cart(request)
    if cart_item.cart != cart:
        if request.headers.get('HX-Request') == 'true':
            return JsonResponse({'success': False, 'message': 'Unauthorized action.'}, status=403)
        messages.error(request, "Unauthorized action.", extra_tags='cart')
        return redirect('view-cart')
    
    product_name = cart_item.product.name
    cart_item.delete()
    messages.success(request, f"{product_name} removed from cart.", extra_tags='cart')
    
    if request.headers.get('HX-Request') == 'true':
        context = {
            'cart_items': cart.items.all(),
            'cart_total': cart.get_total_price(),
            'cart_item_count': cart.get_item_count(),
        }
        return render(request, 'partials/ecommerce/cart_drawer_content.html', context)
    
    # Redirect back to the referring page with cart=open parameter
    next_url = request.META.get('HTTP_REFERER', '/')
    separator = '&' if '?' in next_url else '?'
    return redirect(next_url + separator + 'cart=open')


@login_required(login_url='login')
@require_http_methods(["GET"])
def checkout(request):
    """Display checkout page."""
    cart = get_or_create_cart(request)
    
    if not cart.items.exists():
        messages.error(request, "Your cart is empty.", extra_tags='cart')
        return redirect('view-cart')
    
    context = {
        'cart': cart,
        'items': cart.items.all(),
        'total_price': cart.get_total_price(),
    }
    return render(request, 'ecommerce/checkout.html', context)


@require_http_methods(["GET"])
def get_cart_drawer(request):
    """Return cart drawer content for HTMX requests."""
    cart = get_or_create_cart(request)
    context = {
        'cart_items': cart.items.all(),
        'cart_total': cart.get_total_price(),
        'cart_item_count': cart.get_item_count(),
    }
    return render(request, 'partials/ecommerce/cart_drawer_content.html', context)



import requests
import secrets
from django.conf import settings
from .models import Order, OrderItem
from django.core.mail import send_mail
from django.template.loader import render_to_string


@login_required(login_url='login')
@require_http_methods(["POST"])
def process_checkout(request):
    """Process checkout and initiate Paystack payment"""
    cart = get_or_create_cart(request)
    
    if not cart.items.exists():
        messages.error(request, "Your cart is empty.")
        return redirect('home')
    
    # Get shipping details
    shipping_address = request.POST.get('shipping_address', '').strip()
    shipping_city = request.POST.get('shipping_city', '').strip()
    shipping_state = request.POST.get('shipping_state', '').strip()
    shipping_phone = request.POST.get('shipping_phone', '').strip()
    
    if not all([shipping_address, shipping_city, shipping_state, shipping_phone]):
        messages.error(request, "Please fill all shipping details.")
        return redirect('checkout')
    
    # Create order with pending status
    total_amount = cart.get_total_price()
    payment_ref = f"WS-{secrets.token_urlsafe(16)}"
    
    order = Order.objects.create(
        user=request.user,
        total_amount=total_amount,
        payment_reference=payment_ref,
        shipping_address=shipping_address,
        shipping_city=shipping_city,
        shipping_state=shipping_state,
        shipping_phone=shipping_phone,
    )
    
    # Create order items from cart
    for cart_item in cart.items.all():
        OrderItem.objects.create(
            order=order,
            product=cart_item.product,
            product_name=cart_item.product.name,
            product_sku=cart_item.product.sku,
            quantity=cart_item.quantity,
            price=cart_item.price,
        )
    
    # Initialize Paystack payment
    paystack_url = "https://api.paystack.co/transaction/initialize"
    headers = {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }
    
    # Convert amount to kobo (Paystack uses kobo for NGN)
    amount_in_kobo = int(total_amount * 100)
    
    payload = {
        "email": request.user.email,
        "amount": amount_in_kobo,
        "reference": payment_ref,
        "callback_url": request.build_absolute_uri('/checkout/verify/'),
        "metadata": {
            "order_id": str(order.id),
            "customer_name": f"{request.user.first_name} {request.user.last_name}",
        }
    }
    
    try:
        response = requests.post(paystack_url, json=payload, headers=headers, timeout=10)
        response_data = response.json()
        
        if response_data.get('status'):
            # Clear cart after successful payment initialization
            cart.items.all().delete()
            
            # Redirect to Paystack payment page
            authorization_url = response_data['data']['authorization_url']
            return redirect(authorization_url)
        else:
            messages.error(request, "Payment initialization failed. Please try again.")
            order.delete()  # Remove the order if payment fails
            return redirect('checkout')
    
    except Exception as e:
        messages.error(request, f"Payment error: {str(e)}")
        order.delete()
        return redirect('checkout')


@login_required(login_url='login')
@require_http_methods(["GET"])
def verify_payment(request):
    """Verify Paystack payment and confirm order"""
    reference = request.GET.get('reference')
    
    if not reference:
        messages.error(request, "No payment reference found.")
        return redirect('home')
    
    # Verify payment with Paystack
    verify_url = f"https://api.paystack.co/transaction/verify/{reference}"
    headers = {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
    }
    
    try:
        response = requests.get(verify_url, headers=headers, timeout=10)
        response_data = response.json()
        
        if response_data.get('status') and response_data['data']['status'] == 'success':
            # Payment successful
            order = get_object_or_404(Order, payment_reference=reference)
            order.payment_status = 'completed'
            order.paystack_reference = response_data['data']['reference']
            order.status = 'processing'
            order.save()
            
            # Send order confirmation email
            send_order_confirmation_email(order)
            
            messages.success(request, f"Payment successful! Your order #{order.id} has been confirmed.")
            return redirect('order-confirmation', order_id=order.id)
        else:
            messages.error(request, "Payment verification failed.")
            return redirect('home')
    
    except Order.DoesNotExist:
        messages.error(request, "Order not found.")
        return redirect('home')
    except Exception as e:
        messages.error(request, f"Verification error: {str(e)}")
        return redirect('home')


@login_required(login_url='login')
@require_http_methods(["GET"])
def order_confirmation(request, order_id):
    """Display order confirmation page"""
    order = get_object_or_404(Order, id=order_id, user=request.user)
    context = {
        'order': order,
        'items': order.items.all(),
    }
    return render(request, 'ecommerce/order_confirmation.html', context)


@login_required(login_url='login')
@require_http_methods(["GET"])
def user_orders(request):
    """Display user's order history"""
    orders_qs = Order.objects.filter(user=request.user).order_by('-created_at').prefetch_related('items')
    
    from django.core.paginator import Paginator
    paginator = Paginator(orders_qs, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Partial append of order cards for infinite scroll
    is_partial = request.GET.get('partial') == '1'
    if is_partial:
        return render(request, 'partials/users/order_cards.html', {'orders': page_obj.object_list})
    
    context = {
        'orders': page_obj.object_list,
        'page_obj': page_obj,
    }
    return render(request, 'users/user_orders.html', context)


@login_required(login_url='login')
@require_http_methods(["GET"])
def order_detail(request, order_id):
    """Display single order details for tracking"""
    order = get_object_or_404(Order, id=order_id, user=request.user)
    context = {
        'order': order,
        'items': order.items.all(),
    }
    return render(request, 'users/order_detail.html', context)


def send_order_confirmation_email(order):
    """Send order confirmation email to customer"""
    subject = f"Order Confirmation - #{str(order.id)[:8]}"
    html_message = render_to_string('emails/order_confirmation.html', {
        'order': order,
        'items': order.items.all(),
        'user': order.user,
        'site_url': 'http://127.0.0.1:8000',  # Update for production
    })
    
    try:
        send_mail(
            subject,
            f'Thank you for your order! Order #{str(order.id)[:8]}',  # Plain text version
            settings.DEFAULT_FROM_EMAIL,
            [order.user.email],
            html_message=html_message,
            fail_silently=False,
        )
    except Exception as e:
        print(f"Failed to send order confirmation email: {e}")


def blog_list(request):
    """Public blog listing page with pagination and infinite scroll partials"""
    # Only show published posts on public site
    posts_qs = BlogPost.objects.filter(is_published=True).select_related('category').order_by('-created_at')
    
    # Filter by category
    category_slug = request.GET.get('category', '').strip()
    selected_category = None
    if category_slug:
        try:
            selected_category = BlogCategory.objects.get(slug=category_slug)
            posts_qs = posts_qs.filter(category=selected_category)
        except BlogCategory.DoesNotExist:
            selected_category = None
    
    # Pagination (9 per page)
    from django.core.paginator import Paginator
    paginator = Paginator(posts_qs, 9)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Return partial for infinite scroll
    is_partial = request.GET.get('partial') == '1' or request.headers.get('HX-Request') == 'true'
    if is_partial:
        return render(
            request,
            'partials/ecommerce/blog_cards.html',
            {
                'posts': page_obj.object_list,
            }
        )
    
    # Get all categories for filter tabs
    categories = BlogCategory.objects.all().order_by('name')
    
    return render(request, 'ecommerce/blog_list.html', {
        'posts': page_obj.object_list,
        'categories': categories,
        'selected_category': selected_category,
        'page_obj': page_obj,
        'total_pages': paginator.num_pages,
        'current_page': page_obj.number,
    })


def blog_detail(request, slug):
    """Public blog detail page"""
    post = get_object_or_404(BlogPost, slug=slug, is_published=True)
    
    # Get related posts from same category
    related_posts = BlogPost.objects.filter(
        category=post.category,
        is_published=True
    ).exclude(id=post.id).order_by('-created_at')[:3]
    
    return render(request, 'ecommerce/blog_detail.html', {
        'post': post,
        'related_posts': related_posts,
    })

def terms_of_service(request):
    """Display Terms of Service page"""
    return render(request, 'ecommerce/terms_of_service.html')

def privacy_policy(request):
    """Display Privacy Policy page"""
    return render(request, 'ecommerce/privacy_policy.html')

def return_policy(request):
    """Display Return Policy page"""
    return render(request, 'ecommerce/return_policy.html')

def delivery_policy(request):
    """Display Delivery Policy page"""
    return render(request, 'ecommerce/delivery_policy.html')
