from ecom.models import Cart


def cart_context(request):
    """Add cart information to all templates."""
    cart_item_count = 0
    cart_items = []
    cart_total = 0
    
    if request.user.is_authenticated:
        try:
            cart = Cart.objects.get(user=request.user)
            cart_item_count = cart.get_item_count()
            cart_items = cart.items.all()
            cart_total = cart.get_total_price()
        except Cart.DoesNotExist:
            cart_item_count = 0
    else:
        # Check for anonymous user cart via session
        if hasattr(request, 'session') and request.session.session_key:
            try:
                cart = Cart.objects.get(session_id=request.session.session_key)
                cart_item_count = cart.get_item_count()
                cart_items = cart.items.all()
                cart_total = cart.get_total_price()
            except Cart.DoesNotExist:
                cart_item_count = 0
    
    return {
        'cart_item_count': cart_item_count,
        'cart_items': cart_items,
        'cart_total': cart_total,
    }
