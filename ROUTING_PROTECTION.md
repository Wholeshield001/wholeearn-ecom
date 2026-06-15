# Authentication & Authorization Routing Protection

## Overview
All protected routes now require users to be authenticated and have appropriate permissions before accessing them.

## User Dashboard Routes (users/urls.py)

All routes require `@login_required(login_url='login')` decorator:

- **`/dashboard/`** - User dashboard (main overview)
- **`/profile/`** - User profile management
- **`/change-password/`** - Change password page
- **`/create-ticket/`** - Create support ticket
- **`/order-history/`** - View order history

**What happens if not logged in:**
- User is redirected to `/login/` with a message to log in
- After login, user is returned to the requested page

**Public routes (no login required):**
- `/signup/` - User registration
- `/verify-otp/` - OTP verification during signup
- `/resend-otp/` - Resend OTP
- `/login/` - User login
- `/password-reset/` - Password reset request
- `/password-reset/verify/` - Verify reset code
- `/password-reset/new/` - Set new password
- `/logout/` - Logout user

---

## Admin Dashboard Routes (admin_dashboard/urls.py)

All protected routes use the custom `@admin_required` decorator, which:
1. Checks if user is authenticated
2. Verifies user has `ADMINISTRATOR` role
3. Redirects to admin login if not authenticated
4. Redirects to home if authenticated but not an admin

### Protected Admin Routes:
- **Dashboard**: `/admin/` 
- **Categories**: `/admin/categories/`, `/admin/categories/add/`, `/admin/categories/<id>/edit/`, `/admin/categories/<id>/delete/`
- **Products**: `/admin/products/`, `/admin/products/add/`, `/admin/products/<id>/edit/`, `/admin/products/<id>/delete/`
- **Product Images**: `/admin/products/<id>/images/set-thumbnail/`, `/admin/products/<id>/images/delete/`, `/admin/products/<id>/images/add/`
- **Notifications**: `/admin/notifications/`
- **Wholesalers**: `/admin/wholesalers/`, `/admin/wholesalers/<id>/detail/`
- **Retailers**: `/admin/retailers/`, `/admin/retailers/<id>/detail/`
- **Analytics**: `/admin/analytics/`
- **Orders**: `/admin/orders/`, `/admin/orders/<id>/detail/`, `/admin/orders/track/`
- **Tickets**: `/admin/tickets/`, `/admin/tickets/<id>/detail/`
- **Blog**: `/admin/blog-categories/`, `/admin/blog-categories/add/`, `/admin/blog/edit/<id>/`, `/admin/blog/delete/<id>/`, `/admin/blog/list/`

**What happens if not logged in:**
- User is redirected to `/admin/login/` with message: "You must be logged in to access this page."

**What happens if logged in but not admin:**
- User is redirected to home page with message: "You do not have permission to access this page. Admin access required."

### Public Admin Routes (no authentication required):
- `/admin/login/` - Admin login
- `/admin/logout/` - Admin logout
- `/admin/forgot-password/` - Forgot password
- `/admin/verify-otp/` - Verify OTP for password reset
- `/admin/resend-otp/` - Resend OTP
- `/admin/reset-password/` - Reset password
- `/admin/password-reset-success/` - Success confirmation page

---

## E-Commerce Public Routes (ecom/urls.py)

All public routes - no authentication required:
- **`/`** - Home page
- **`/products/`** - Product listing with infinite scroll
- **`/products/<id>/`** - Product detail page
- **`/cart/`** - Shopping cart (guest cart uses session)
- **`/cart/add/`** - Add to cart
- **`/cart/drawer/`** - Cart drawer partial
- **`/cart/update/`** - Update cart item
- **`/cart/remove/`** - Remove from cart
- **`/checkout/`** - Checkout page (requires authentication)
- **`/checkout/process/`** - Process checkout
- **`/checkout/verify/`** - Verify payment
- **`/blog/`** - Blog list (only published posts)
- **`/blog/<slug>/`** - Blog detail page

**Special case - Checkout:**
- While the route doesn't have explicit decorator, checkout requires a valid cart and authenticated user
- Guest users can browse but must log in before completing purchase

---

## Custom Admin Decorator Implementation

```python
def admin_required(view_func):
    """Decorator to ensure user is authenticated and has admin role"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'You must be logged in to access this page.')
            return redirect('admin_login')
        
        if request.user.role != User.ADMINISTRATOR:
            messages.error(request, 'You do not have permission to access this page. Admin access required.')
            return redirect('home')
        
        return view_func(request, *args, **kwargs)
    return wrapper
```

---

## User Experience Flow

### New User or Not Logged In:
1. Visit any protected route (dashboard, admin, etc.)
2. Automatically redirected to login page
3. Clear message displayed
4. After login, redirected back to originally requested page

### Logged In User with Wrong Role:
1. Visit admin dashboard as regular customer
2. Redirected to home page
3. Error message explains permission denied

### Admin User:
1. Can access all admin routes freely
2. Seamless navigation within admin dashboard
3. Logout returns to admin login page

---

## Testing the Protection

### Test User Dashboard Protection:
```bash
curl -L http://localhost:8000/dashboard/
# Should redirect to /login/
```

### Test Admin Protection:
```bash
curl -L http://localhost:8000/admin/
# Should redirect to /admin/login/ if not authenticated
# Should redirect to home if authenticated but not admin
```

### Test Public Access:
```bash
curl http://localhost:8000/products/
# Should return 200 OK without authentication
```

---

## Summary

✅ **User Dashboard**: Protected - requires login via `@login_required`
✅ **Admin Dashboard**: Protected - requires admin role via `@admin_required` 
✅ **E-Commerce**: Public - all pages accessible to guests
✅ **Auth Pages**: Public - login/signup/password reset accessible
✅ **Error Handling**: Clear messages guide users to log in or contact admin
