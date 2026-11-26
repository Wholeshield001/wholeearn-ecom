from django.db.utils import OperationalError, ProgrammingError
from admin_dashboard.models import Category
from ecom.models import Cart, SocialMediaLink
from users.models import User


def cart_context(request):
    """Add cart information, storefront navigation/footer data, and common user CTA state to all templates."""
    cart_item_count = 0
    cart_items = []
    cart_total = 0
    show_kyc_cta = False
    kyc_cta_url_name = 'submit-kyc'

    if request.user.is_authenticated:
        try:
            cart = Cart.objects.get(user=request.user)
            cart_item_count = cart.get_item_count()
            cart_items = cart.items.all()
            cart_total = cart.get_total_price()
        except Cart.DoesNotExist:
            cart_item_count = 0

        # Partner KYC CTA logic:
        # - Show when KYC has not been submitted yet
        # - Hide once submitted (pending/approved)
        # - Show again if rejected
        partner_roles = {
            User.WHOLESALER,
            User.RETAILER,
            User.HOSPITAL,
            User.PHARMACY,
            User.ONLINE_VENDOR,
        }
        if request.user.role in partner_roles:
            not_submitted = request.user.kyc_submitted_at is None
            rejected = request.user.kyc_status == User.KYC_REJECTED
            show_kyc_cta = bool(not_submitted or rejected)
            if rejected:
                kyc_cta_url_name = 'submit-kyc'
            elif not_submitted:
                kyc_cta_url_name = 'submit-kyc'
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

    try:
        footer_categories = list(Category.objects.all().order_by('name'))
    except (OperationalError, ProgrammingError):
        footer_categories = []

    try:
        social_links = list(SocialMediaLink.objects.filter(is_active=True).order_by('display_order', 'name'))
    except (OperationalError, ProgrammingError):
        social_links = []

    return {
        'cart_item_count': cart_item_count,
        'cart_items': cart_items,
        'cart_total': cart_total,
        'show_kyc_cta': show_kyc_cta,
        'kyc_cta_url_name': kyc_cta_url_name,
        'footer_categories': footer_categories,
        'social_links': social_links,
    }
