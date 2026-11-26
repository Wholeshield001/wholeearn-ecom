from decimal import Decimal, InvalidOperation
from django import template

register = template.Library()


@register.filter(name='format_price')
def format_price(value):
    """Format a numeric price as a whole number with thousands commas (e.g. 25000.00 -> 25,000)."""
    if value is None or value == '':
        return '0'
    try:
        amount = Decimal(str(value))
        rounded = int(amount.quantize(Decimal('1')))
        return f"{rounded:,}"
    except (InvalidOperation, ValueError, TypeError):
        return str(value)

@register.filter(name='cloudinary_optimize')
def cloudinary_optimize(url, transformations="f_auto,q_auto"):
    """
    Optimizes Cloudinary image URLs by inserting transformation parameters.
    If the URL is hosted on Cloudinary, it inserts the transformation string right after '/upload/'.
    Otherwise (e.g., local storage in development), it returns the original URL.
    """
    if not url:
        return ""
    url_str = str(url)
    if "res.cloudinary.com" in url_str and "/upload/" in url_str:
        # Avoid duplicate insertions if transformation parameters are already present
        if f"/upload/{transformations}/" in url_str:
            return url_str
        return url_str.replace("/upload/", f"/upload/{transformations}/", 1)
    return url_str


@register.filter(name='min_quantity_for_role')
def min_quantity_for_role(product, role):
    if not role:
        return 1
    return product.get_min_quantity_for_role(role)


@register.filter(name='price_for_user')
def price_for_user(product, user):
    if not user or not user.is_authenticated:
        return product.customer_price
    return product.get_price_for_role(user.role)

