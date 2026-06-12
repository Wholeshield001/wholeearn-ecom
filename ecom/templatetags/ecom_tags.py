from django import template

register = template.Library()

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
