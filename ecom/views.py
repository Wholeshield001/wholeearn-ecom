import logging
import re
import secrets
import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.utils import timezone
from django.shortcuts import render, get_object_or_404, redirect
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from admin_dashboard.models import Product, Category, BlogPost, BlogCategory
from .models import Cart, CartItem, Order, OrderItem
from .services.payments import PaymentGatewayError, get_active_payment_provider, get_payment_provider
from .services.wallets import apply_withdrawal_status_update

logger = logging.getLogger(__name__)


def _verify_monnify_webhook_signature(request):
    """Verify Monnify webhook signature using secret key."""
    signature = (
        request.headers.get('Monnify-Signature')
        or request.headers.get('monnify-signature')
        or ''
    ).strip()
    if not signature:
        return False

    secret = getattr(settings, 'MONNIFY_WEBHOOK_SECRET', '') or settings.MONNIFY_SECRET_KEY
    if not secret:
        return False

    expected = hmac.new(
        key=secret.encode('utf-8'),
        msg=request.body,
        digestmod=hashlib.sha512,
    ).hexdigest()
    return hmac.compare_digest(expected.lower(), signature.lower())


def _extract_monnify_transfer_payload(payload):
    body = payload.get('responseBody') if isinstance(payload, dict) else None
    data = body if isinstance(body, dict) else payload

    reference = (
        (data or {}).get('reference')
        or (data or {}).get('transactionReference')
        or (data or {}).get('paymentReference')
        or payload.get('reference')
        or payload.get('transactionReference')
    )
    status = (
        (data or {}).get('status')
        or (data or {}).get('transactionStatus')
        or (data or {}).get('paymentStatus')
        or payload.get('status')
    )
    provider_reference = (
        (data or {}).get('transactionReference')
        or (data or {}).get('reference')
        or payload.get('transactionReference')
    )
    return reference, status, provider_reference


@csrf_exempt
@require_http_methods(["POST"])
def monnify_transfer_webhook(request):
    """Handle Monnify transfer webhook updates for wallet withdrawals."""
    if not _verify_monnify_webhook_signature(request):
        logger.warning("Monnify webhook rejected due to invalid signature")
        return JsonResponse({'ok': False, 'error': 'Invalid signature'}, status=401)

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except ValueError:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON payload'}, status=400)

    reference, status, provider_reference = _extract_monnify_transfer_payload(payload)
    if not reference or not status:
        return JsonResponse({'ok': False, 'error': 'Missing transfer reference or status'}, status=400)

    withdrawal = apply_withdrawal_status_update(
        reference=reference,
        status=status,
        provider_reference=provider_reference,
        raw_payload=payload,
    )
    if not withdrawal:
        return JsonResponse({'ok': False, 'error': 'Withdrawal request not found'}, status=404)

    return JsonResponse({'ok': True, 'reference': reference, 'status': withdrawal.status})


def _build_payment_callback_url(request):
    configured_base_url = settings.PAYMENT_CALLBACK_BASE_URL
    if configured_base_url:
        return f"{configured_base_url}/checkout/verify/"
    return request.build_absolute_uri('/checkout/verify/')


def _get_cart_total_weight(cart):
    total_weight = Decimal('0')
    for item in cart.items.select_related('product'):
        unit_weight = item.product.weight_kg if item.product and item.product.weight_kg else Decimal('1.00')
        total_weight += Decimal(str(unit_weight)) * item.quantity
    return max(total_weight, Decimal('0.01'))


def reconcile_recent_monnify_orders_for_user(request, user, *, max_orders=3, window_days=2, min_interval_seconds=45):
    """Reconcile recent pending Monnify orders for a user.

    This protects checkout completion when the gateway return redirect does not happen.
    """
    now = timezone.now()
    session_key = f"monnify_reconcile_last_ts_{user.id}"
    last_ts = request.session.get(session_key)
    if isinstance(last_ts, (int, float)) and (now.timestamp() - float(last_ts) < min_interval_seconds):
        return 0
    request.session[session_key] = now.timestamp()

    try:
        provider = get_payment_provider('monnify')
    except PaymentGatewayError:
        return 0

    cutoff = now - timedelta(days=window_days)
    pending_orders = (
        Order.objects.filter(
            user=user,
            payment_provider='monnify',
            payment_status='pending',
            created_at__gte=cutoff,
        )
        .order_by('-created_at')[:max_orders]
    )

    reconciled_count = 0
    for order in pending_orders:
        if not order.payment_reference:
            continue
        try:
            result = provider.verify_payment(
                reference=order.payment_reference,
                transaction_reference=order.gateway_reference,
            )
            if not result.get('success'):
                continue

            order.gateway_reference = result.get('provider_reference') or order.gateway_reference
            order.save(update_fields=['gateway_reference'])
            _finalize_successful_payment(order, request)
            reconciled_count += 1
        except PaymentGatewayError:
            continue
        except Exception:
            logger.exception("Automatic payment reconciliation failed for order %s", order.id)

    return reconciled_count


def home(request):
    if request.user.is_authenticated:
        reconcile_recent_monnify_orders_for_user(request, request.user)

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
    
    # Get role-based price for this user
    role_price = product.get_price_for_role(user_role) if user_role else product.customer_price

    # Add or update cart item
    cart_item, created = CartItem.objects.get_or_create(
        cart=cart,
        product=product,
        defaults={'price': role_price, 'quantity': quantity}
    )
    
    if not created:
        # Item already in cart — refresh price to current role price in case it changed
        cart_item.price = role_price
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


import os
import json

def get_speedaf_areas():
    """Helper to load SpeedAF areas"""
    try:
        from django.conf import settings
        path = os.path.join(settings.BASE_DIR, 'ecom', 'services', 'speedaf_areas.json')
        with open(path, 'r') as f:
            return json.load(f)
    except Exception:
        return []

@require_http_methods(["GET"])
def htmx_speedaf_cities(request):
    """HTMX endpoint to return cities options."""
    state_code = request.GET.get('shipping_state', '')
    cities = []
    if state_code:
        areas = get_speedaf_areas()
        for state in areas:
            if state['code'] == state_code:
                cities = state.get('cities', [])
                break
    
    html = '<option value="">Select City...</option>'
    for city in cities:
        html += f'<option value="{city["code"]}">{city["name"]}</option>'
        
    from django.http import HttpResponse
    return HttpResponse(html)

@login_required(login_url='login')
@require_http_methods(["GET"])
def checkout(request):
    """Display checkout page."""
    reconcile_recent_monnify_orders_for_user(request, request.user)

    # Enforce KYC for partners
    partner_roles = {
        getattr(request.user, 'WHOLESALER', 'wholesaler'),
        getattr(request.user, 'RETAILER', 'retailer'),
        getattr(request.user, 'HOSPITAL', 'hospital'),
        getattr(request.user, 'PHARMACY', 'pharmacy'),
        getattr(request.user, 'ONLINE_VENDOR', 'online_vendor'),
    }
    if getattr(request.user, 'role', None) in partner_roles:
        if getattr(request.user, 'kyc_status', None) != 'approved':
            messages.error(request, "You must complete your KYC before you can buy products.")
            return redirect('kyc-status')

    cart = get_or_create_cart(request)

    if not cart.items.exists():
        messages.error(request, "Your cart is empty.", extra_tags='cart')
        return redirect('view-cart')

    try:
        payment_provider = get_active_payment_provider()
    except PaymentGatewayError:
        payment_provider = get_payment_provider('paystack')

    context = {
        'cart': cart,
        'items': cart.items.all(),
        'total_price': cart.get_total_price(),
        'speedaf_states': get_speedaf_areas(),
        'payment_provider_name': payment_provider.display_name,
        'payment_provider_key': payment_provider.key,
        'monnify_api_key': settings.MONNIFY_API_KEY,
        'monnify_contract_code': settings.MONNIFY_CONTRACT_CODE,
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



from django.core.mail import send_mail
from django.template.loader import render_to_string
from .services.speedaf import SpeedAFClient

@login_required(login_url='login')
@require_http_methods(["POST"])
def get_shipping_quote(request):
    """HTMX view to calculate shipping rate dynamically"""
    city = request.POST.get('shipping_city', '').strip()
    state = request.POST.get('shipping_state', '').strip()
    
    if not (city and state):
        cart = get_or_create_cart(request)
        cart_total = cart.get_total_price()
        return render(request, 'partials/ecommerce/shipping_quote.html', {
            'shipping_fee': None,
            'grand_total': cart_total,
            'total_price': cart_total,
        })
    
    client = SpeedAFClient()
    cart = get_or_create_cart(request)
    total_weight = _get_cart_total_weight(cart)
    shipping_fee = client.calculate_shipping_rate(city, state, weight=float(total_weight))

    if shipping_fee is None:
        cart_total = cart.get_total_price()
        return render(request, 'partials/ecommerce/shipping_quote.html', {
            'shipping_fee': None,
            'grand_total': cart_total,
            'total_price': cart_total,
        })
    
    cart_total = cart.get_total_price()
    grand_total = cart_total + Decimal(str(shipping_fee))
    
    return render(request, 'partials/ecommerce/shipping_quote.html', {
        'shipping_fee': shipping_fee,
        'grand_total': grand_total,
        'total_price': cart_total,
    })


@login_required(login_url='login')
@require_http_methods(["POST"])
def process_checkout(request):
    """Process checkout and initiate payment with configured provider."""
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    # Check KYC requirement for non-END_USER partners
    if request.user.is_authenticated:
        from users.models import User
        if request.user.role != User.END_USER:
            # Partner role - must have approved KYC
            if request.user.kyc_status != User.KYC_APPROVED:
                if is_ajax:
                    return JsonResponse({
                        'ok': False,
                        'error': 'Your KYC verification is required before checkout. Please submit your KYC documents.',
                        'kyc_status': request.user.kyc_status
                    }, status=403)
                messages.error(request, "Your KYC verification is required before checkout. Please submit your KYC documents.")
                return redirect('submit-kyc')
    
    cart = get_or_create_cart(request)
    
    if not cart.items.exists():
        if is_ajax:
            return JsonResponse({'ok': False, 'error': 'Your cart is empty.'}, status=400)
        messages.error(request, "Your cart is empty.")
        return redirect('home')
    
    # Get and validate shipping details
    shipping_address = request.POST.get('shipping_address', '').strip()
    shipping_city = request.POST.get('shipping_city', '').strip()
    shipping_state = request.POST.get('shipping_state', '').strip()
    shipping_phone = request.POST.get('shipping_phone', '').strip()
    if not all([shipping_address, shipping_city, shipping_state, shipping_phone]):
        if is_ajax:
            return JsonResponse({'ok': False, 'error': 'Please fill all shipping details.'}, status=400)
        messages.error(request, "Please fill all shipping details.")
        return redirect('checkout')

    if len(shipping_address) > 255 or len(shipping_city) > 100 or len(shipping_state) > 100:
        if is_ajax:
            return JsonResponse({'ok': False, 'error': 'Shipping address fields are too long.'}, status=400)
        messages.error(request, "Shipping address fields are too long.")
        return redirect('checkout')

    if not re.fullmatch(r'[\d\+\s\-\.]{1,20}', shipping_phone):
        if is_ajax:
            return JsonResponse({'ok': False, 'error': 'Enter a valid phone number.'}, status=400)
        messages.error(request, "Enter a valid phone number.")
        return redirect('checkout')

    referrer = request.user.referred_by
    referral_code = referrer.referral_code if referrer else None
    
    # Calculate shipping fee
    client = SpeedAFClient()
    total_weight = _get_cart_total_weight(cart)
    shipping_fee = client.calculate_shipping_rate(shipping_city, shipping_state, weight=float(total_weight))

    if shipping_fee is None:
        if is_ajax:
            return JsonResponse({'ok': False, 'error': 'Unable to get live shipping quote from SpeedAF. Please try again.'}, status=502)
        messages.error(request, "Unable to get live shipping quote from SpeedAF. Please try again.")
        return redirect('checkout')
    
    # Create order with pending status
    cart_total = cart.get_total_price()
    total_amount = cart_total + Decimal(str(shipping_fee))
    payment_ref = f"WS-{secrets.token_urlsafe(16)}"
    
    try:
        payment_provider = get_active_payment_provider()
    except PaymentGatewayError as e:
        if is_ajax:
            return JsonResponse({'ok': False, 'error': f'Payment configuration error: {str(e)}'}, status=400)
        messages.error(request, f"Payment configuration error: {str(e)}")
        return redirect('checkout')

    from django.db import transaction as db_transaction
    with db_transaction.atomic():
        order = Order.objects.create(
            user=request.user,
            payment_provider=payment_provider.key,
            shipping_fee=shipping_fee,
            total_amount=total_amount,
            payment_reference=payment_ref,
            referral_code_used=referral_code or None,
            referrer=referrer,
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

    # Monnify Web SDK performs its own transaction initialization in the browser.
    # Do not pre-initialize via API here for AJAX flow, otherwise the same reference
    # is initialized twice and Monnify can fail with a 500 init error.
    if is_ajax and payment_provider.key == 'monnify':
        return JsonResponse(
            {
                'ok': True,
                'provider': 'monnify',
                'order_id': str(order.id),
                'payment_reference': payment_ref,
                'transaction_reference': None,
                'authorization_url': None,
                'monnify': {
                    'amount': float(total_amount),
                    'currency': 'NGN',
                    'reference': payment_ref,
                    'customer_full_name': f"{request.user.first_name} {request.user.last_name}".strip() or request.user.email,
                    'customer_email': request.user.email,
                    'api_key': settings.MONNIFY_API_KEY,
                    'contract_code': settings.MONNIFY_CONTRACT_CODE,
                    'payment_description': 'WholeShield order payment',
                    'metadata': {
                        'order_id': str(order.id),
                    },
                },
            }
        )
    
    try:
        init_data = payment_provider.initialize_payment(
            amount=total_amount,
            email=request.user.email,
            reference=payment_ref,
            callback_url=_build_payment_callback_url(request),
            metadata={
                "order_id": str(order.id),
                "customer_name": f"{request.user.first_name} {request.user.last_name}".strip() or request.user.email,
            },
        )
        order.gateway_reference = init_data.get('provider_reference')
        order.save(update_fields=['gateway_reference'])

        return redirect(init_data['authorization_url'])
    except PaymentGatewayError as e:
        if is_ajax:
            return JsonResponse({'ok': False, 'error': f'Payment initialization failed: {str(e)}'}, status=400)
        messages.error(request, f"Payment initialization failed: {str(e)}")
        order.delete()
        return redirect('checkout')


def _finalize_successful_payment(order, request):
    """Mark order paid and run post-payment actions once.

    Uses select_for_update inside an atomic block so that concurrent calls
    (e.g. gateway redirect + Monnify reconciliation arriving at the same time)
    only finalise the order once. Returns True if this call did the work,
    False if it was already completed by a concurrent request.
    """
    from django.db import transaction as db_transaction

    with db_transaction.atomic():
        # Lock the row so any concurrent finalise call blocks until we finish.
        locked = Order.objects.select_for_update().get(pk=order.pk)
        if locked.payment_status == 'completed':
            # Already finalised — copy updated fields back so callers see them.
            order.payment_status = locked.payment_status
            order.status = locked.status
            return False

        locked.payment_status = 'completed'
        locked.status = 'ordered'

        try:
            client = SpeedAFClient()
            speedaf_id, waybill = client.create_shipping_order(locked)
            if speedaf_id:
                locked.speedaf_order_id = speedaf_id
            if waybill:
                locked.tracking_number = waybill
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "SpeedAF shipping order creation failed for order %s", locked.id
            )

        locked.save()
        # Reflect changes back onto the original object passed by the caller.
        order.payment_status = locked.payment_status
        order.status = locked.status
        order.speedaf_order_id = locked.speedaf_order_id
        order.tracking_number = locked.tracking_number

    # Run side-effects outside the lock so they don't hold the DB row.
    # Queue email via Celery so a transient SMTP hiccup doesn't block the
    # response or lose the notification — the task retries automatically.
    from ecom.tasks import send_order_confirmation_email_task
    send_order_confirmation_email_task.delay(str(order.pk))
    cart = get_or_create_cart(request)
    cart.items.all().delete()
    return True


_SAFE_REF_RE = re.compile(r'^[\w\-|.]{1,200}$')


@require_http_methods(["GET"])
def verify_payment(request):
    """Verify payment and confirm order for active/saved provider."""
    logger.info("[verify_payment] incoming params: %s", dict(request.GET))

    reference = request.GET.get('reference') or request.GET.get('paymentReference')
    transaction_reference = request.GET.get('transactionReference') or request.GET.get('transaction_reference')

    # Sanitise – reject any reference that contains unusual characters
    if reference and not _SAFE_REF_RE.match(reference):
        messages.error(request, 'Invalid payment reference.')
        return redirect('home')
    if transaction_reference and not _SAFE_REF_RE.match(transaction_reference):
        messages.error(request, 'Invalid transaction reference.')
        return redirect('home')

    logger.info("[verify_payment] reference=%r  transaction_reference=%r", reference, transaction_reference)

    order = None
    if reference:
        order = Order.objects.filter(payment_reference=reference).first()
        logger.info("[verify_payment] order lookup by reference=%r -> %s", reference, order)

    provider_key = order.payment_provider if order else None
    if not provider_key and transaction_reference and not reference:
        provider_key = 'monnify'
    logger.info("[verify_payment] using provider_key=%r", provider_key)
    provider = get_payment_provider(provider_key)

    try:
        result = provider.verify_payment(
            reference=reference,
            transaction_reference=transaction_reference,
            request=request,
        )
        logger.info("[verify_payment] provider result: %s", result)

        payment_reference = result.get('payment_reference') or reference
        if not order:
            order = get_object_or_404(Order, payment_reference=payment_reference)

        order.gateway_reference = result.get('provider_reference') or order.gateway_reference
        if provider.key == 'paystack':
            order.paystack_reference = result.get('provider_reference') or order.paystack_reference

        if result.get('success'):
            _finalize_successful_payment(order, request)
            messages.success(request, f"Payment successful! Your order #{order.id} has been confirmed.")
            if request.user.is_authenticated and request.user == order.user:
                return redirect('order-confirmation', order_id=order.id)
            return render(
                request,
                'ecommerce/order_confirmation.html',
                {
                    'order': order,
                    'items': order.items.all(),
                },
            )
        logger.warning("[verify_payment] payment not successful, status=%r raw=%s", result.get('status'), result.get('raw'))
        order.payment_status = 'failed'
        order.save(update_fields=['payment_status', 'gateway_reference', 'paystack_reference'])
        messages.error(request, "Payment verification failed.")
        return redirect('home')

    except Order.DoesNotExist:
        logger.error("[verify_payment] Order not found for payment_reference=%r", payment_reference if 'payment_reference' in dir() else reference)
        messages.error(request, "Order not found.")
        return redirect('home')
    except PaymentGatewayError as e:
        logger.exception("[verify_payment] PaymentGatewayError: %s", e)
        messages.error(request, f"Verification error: {str(e)}")
        return redirect('home')
    except Exception as e:
        logger.exception("[verify_payment] Unexpected error: %s", e)
        messages.error(request, f"Verification error: {str(e)}")
        return redirect('home')


@login_required(login_url='login')
@require_http_methods(["POST"])
def retry_payment(request, order_id):
    """Retry payment for a pending order"""
    order = get_object_or_404(Order, id=order_id, user=request.user, payment_status='pending')

    try:
        payment_provider = get_active_payment_provider()
    except PaymentGatewayError as e:
        messages.error(request, f"Payment configuration error: {str(e)}")
        return redirect('order-detail', order_id=order.id)

    # Generate a new payment reference because Paystack rejects duplicates for abandoned transactions
    new_ref = f"WS-{secrets.token_urlsafe(16)}"
    order.payment_reference = new_ref
    order.payment_provider = payment_provider.key
    order.save(update_fields=['payment_reference', 'payment_provider'])

    try:
        init_data = payment_provider.initialize_payment(
            amount=order.total_amount,
            email=request.user.email,
            reference=new_ref,
            callback_url=_build_payment_callback_url(request),
            metadata={
                "order_id": str(order.id),
                "customer_name": f"{request.user.first_name} {request.user.last_name}".strip() or request.user.email,
            },
        )
        order.gateway_reference = init_data.get('provider_reference')
        order.save(update_fields=['gateway_reference'])
        return redirect(init_data['authorization_url'])
    except PaymentGatewayError as e:
        messages.error(request, f"Payment initialization failed: {str(e)}")
        return redirect('order-detail', order_id=order.id)


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
    reconcile_recent_monnify_orders_for_user(request, request.user)

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
    reconcile_recent_monnify_orders_for_user(request, request.user)

    order = get_object_or_404(Order, id=order_id, user=request.user)
    context = {
        'order': order,
        'items': order.items.all(),
    }
    return render(request, 'users/order_detail.html', context)


def send_order_confirmation_email(order):
    """Send order confirmation email to customer (synchronous fallback)."""
    subject = f"Order Confirmation - #{str(order.id)[:8]}"
    site_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')
    html_message = render_to_string('emails/order_confirmation.html', {
        'order': order,
        'items': order.items.all(),
        'user': order.user,
        'site_url': site_url,
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
