# Order & Payment System Documentation

## Overview
Complete e-commerce order and payment system with Paystack integration, order tracking, and admin management capabilities.

## Features Implemented

### 1. **Payment Processing with Paystack**
- Integrated Paystack payment gateway for secure payments
- Payment initialization with order creation
- Payment verification callback handler
- Automatic order status updates after successful payment
- Support for Nigerian Naira (₦) currency

### 2. **Order Management**
- Complete order lifecycle management (pending → processing → shipped → delivered)
- Order creation with cart snapshot
- Unique order IDs and payment references
- Order history for users
- Detailed order tracking

### 3. **User Features**
- **Checkout**: Shipping information form with address, city, state, and phone
- **Payment**: Secure redirect to Paystack for payment processing
- **Order Confirmation**: Success page with order details after payment
- **Order History**: View all past orders with status badges
- **Order Tracking**: Detailed order timeline and tracking information
- **Email Notifications**: HTML email confirmation after successful order

### 4. **Dashboard Integration**
- Real order metrics (total orders, pending orders, revenue)
- Recent order items display
- Updated to use real Order model instead of cart items

## Database Models

### Order Model
```python
class Order(models.Model):
    id = UUIDField (primary key)
    user = ForeignKey to User
    total_amount = DecimalField
    status = CharField (pending, processing, shipped, delivered, cancelled)
    payment_status = CharField (pending, completed, failed, refunded)
    payment_reference = CharField (unique)
    paystack_reference = CharField
    shipping_address = TextField
    shipping_city = CharField
    shipping_state = CharField
    shipping_phone = CharField
    tracking_number = CharField
    tracking_notes = TextField
    created_at = DateTimeField
    updated_at = DateTimeField
```

### OrderItem Model
```python
class OrderItem(models.Model):
    id = UUIDField (primary key)
    order = ForeignKey to Order
    product = ForeignKey to Product (SET_NULL)
    product_name = CharField (snapshot)
    product_sku = CharField (snapshot)
    quantity = PositiveIntegerField
    price = DecimalField (snapshot)
```

## URL Routes

### Customer Routes
- `/checkout/` - Checkout page with shipping form
- `/checkout/process/` - Process checkout and initialize payment (POST)
- `/checkout/verify/` - Payment verification callback from Paystack
- `/order/confirmation/<uuid>/` - Order confirmation page
- `/orders/` - User's order history
- `/orders/<uuid>/` - Order detail and tracking page

### Dashboard Routes
- `/dashboard/` - User dashboard with order metrics
- `/order-history/` - Order history (same as /orders/)

## Templates Created

1. **templates/ecommerce/order_confirmation.html**
   - Success message with checkmark icon
   - Order details with items and total
   - Shipping address display
   - Payment reference
   - Links to order tracking and continue shopping

2. **templates/users/user_orders.html**
   - List of all user orders
   - Status badges (pending, processing, shipped, delivered, cancelled)
   - Payment status indicators
   - Tracking numbers when available
   - Clickable rows to view order details
   - Empty state with call-to-action

3. **templates/users/order_detail.html**
   - Order timeline visualization
   - Status progression indicators
   - Order items with product images
   - Shipping and payment information
   - Tracking number and notes display
   - Back to orders navigation

4. **templates/users/order_history.html** (Updated)
   - Table view of all orders
   - Order ID, date, items count, total, status
   - "View Details" action links
   - Tabs navigation (Dashboard, Order History, Settings, Create Ticket)

5. **templates/emails/order_confirmation.html**
   - HTML email template
   - Order summary with items
   - Shipping address
   - Payment reference
   - "Track Your Order" button
   - Responsive design for email clients

## Payment Flow

### 1. Checkout Process
```
User fills shipping form → Submit → process_checkout view
↓
Create Order record with status='pending', payment_status='pending'
↓
Create OrderItem records from cart (snapshot product data)
↓
Generate unique payment_reference
↓
Call Paystack Initialize API
↓
Clear user's cart
↓
Redirect to Paystack payment page
```

### 2. Payment Verification
```
User completes payment on Paystack → Paystack redirects to verify-payment
↓
Extract reference from query params
↓
Call Paystack Verify API
↓
Check payment status
↓
Update Order: payment_status='completed', status='processing'
↓
Send order confirmation email
↓
Redirect to order confirmation page
```

## Environment Variables Required
```bash
PAYSTACK_SECRET_KEY=sk_test_xxxxxxxxxxxxx
PAYSTACK_PUBLIC_KEY=pk_test_xxxxxxxxxxxxx
```

## Key Functions

### process_checkout(request)
- Validates shipping information
- Creates Order and OrderItem records
- Initializes Paystack payment
- Returns: Redirect to Paystack payment page

### verify_payment(request)
- Verifies payment with Paystack API
- Updates order status
- Sends confirmation email
- Returns: Redirect to order confirmation

### send_order_confirmation_email(order)
- Renders HTML email template
- Sends email using Django's send_mail
- Includes order details, items, shipping info

## Admin Features (Ready for Implementation)
The Order model includes fields ready for admin management:
- `tracking_number` - For adding shipment tracking
- `tracking_notes` - For status update notes
- `status` - Can be updated by admin (pending → processing → shipped → delivered)

**Next Steps for Admin**:
- Create admin views to list all orders
- Create form to update order status and tracking
- Add admin templates for order management

## Testing the System

### 1. Test Checkout Flow
```bash
# Start the server
python manage.py runserver

# Steps:
1. Add items to cart
2. Go to checkout
3. Fill shipping information
4. Click "Proceed to Payment"
5. Use Paystack test card: 4084084084084081
6. Complete payment
7. Verify redirect to order confirmation
8. Check email for confirmation
```

### 2. Test Order Tracking
```
1. Visit /orders/ to see order history
2. Click "View Details" on an order
3. View order timeline and tracking
4. Check order status badges
```

### 3. Test Dashboard
```
1. Visit /dashboard/
2. Verify order metrics are displayed
3. Check recent order items table
4. Verify all numbers are accurate
```

## Email Configuration
The system uses Django's email backend. Ensure these settings are configured in `settings.py`:

```python
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST')
EMAIL_PORT = config('EMAIL_PORT')
EMAIL_USE_TLS = True
EMAIL_HOST_USER = config('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL')
```

## Important Notes

### Currency Handling
- Display: Nigerian Naira (₦)
- Paystack API: Requires amount in kobo (multiply by 100)
- Example: ₦1,000 = 100,000 kobo

### Order Snapshots
OrderItem stores product information at the time of order:
- `product_name` - Product name won't change if product is renamed
- `product_sku` - SKU snapshot for reference
- `price` - Price at time of purchase

This ensures order history remains accurate even if products are updated or deleted.

### Cart Behavior
The cart is cleared after successful payment initialization (not after verification). This ensures:
- Cart is empty even if user abandons payment
- User can't accidentally order same items twice
- Clean state for next shopping session

### Payment References
- `payment_reference`: Internal unique reference (16-char random string)
- `paystack_reference`: Paystack's transaction reference (returned from API)

Both are stored for reconciliation and support purposes.

## File Structure
```
ecom/
├── models.py (Order, OrderItem models)
├── views.py (payment and order views)
└── urls.py (checkout and order routes)

users/
├── views.py (dashboard, order_history updated)
└── urls.py (dashboard routes)

templates/
├── ecommerce/
│   ├── checkout.html (updated with shipping form)
│   └── order_confirmation.html (new)
├── users/
│   ├── user_orders.html (new)
│   ├── order_detail.html (new)
│   ├── order_history.html (updated)
│   └── dashboard.html (updated)
└── emails/
    └── order_confirmation.html (new)

migrations/
└── ecom/migrations/0002_order_orderitem.py
```

## Dependencies
- **Django**: Web framework
- **requests**: For Paystack API calls (already installed)
- **Paystack**: Payment gateway integration
- **python-decouple**: For environment variables

## Production Checklist
- [ ] Update `site_url` in send_order_confirmation_email() from localhost to production domain
- [ ] Set production Paystack keys (live keys instead of test)
- [ ] Configure production email SMTP settings
- [ ] Set up proper error logging for payment failures
- [ ] Add order notification for admins
- [ ] Implement webhook for payment status updates
- [ ] Add order cancellation functionality
- [ ] Build admin order management interface
- [ ] Set up automated tracking number emails
- [ ] Add order invoice generation

## Future Enhancements
1. **Admin Order Management**
   - List all orders with filters
   - Update order status and tracking
   - Bulk order processing
   - Order analytics

2. **Customer Enhancements**
   - Order cancellation (for pending orders)
   - Reorder functionality
   - Print invoice/receipt
   - Save multiple shipping addresses

3. **Payment Features**
   - Multiple payment methods
   - Partial refunds
   - Payment retry for failed transactions
   - Installment payments

4. **Notification System**
   - SMS notifications for order updates
   - WhatsApp order tracking
   - Push notifications
   - Email tracking updates

## Support
For issues or questions about the order/payment system:
1. Check Django logs for error messages
2. Verify Paystack test keys are correctly configured
3. Test email configuration with Django shell
4. Check database for Order records after payment
