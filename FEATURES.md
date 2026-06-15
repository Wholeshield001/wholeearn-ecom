# WholeShield Wellness — Application Features

## 1. Authentication & User Management

**Custom User Model**
- UUID primary keys throughout
- Email as login identifier (no username)
- Roles: `administrator`, `wholesaler`, `retailer`, `hospital`, `pharmacy`, `end_user`
- Fields: `email`, `first_name`, `last_name`, `phone`, `role`, `is_verified_kyc`, `reward_points`
- Auto-generated `unique_code` (prefix `USR`) and `referral_code` (prefix `REF`)
- `referred_by` self-referential FK to track who invited each user

**Registration**
- Email + password + role selection
- Account inactive until email verified
- 6-digit OTP emailed via Zoho SMTP, valid 15 minutes
- Max 3 failed OTP attempts before lockout
- Resend OTP endpoint
- Welcome email on successful verification

**Login / Logout**
- Email + password authentication
- "Remember me" toggle (session vs. 2-week persistent cookie)
- Role-based redirect: admins → admin dashboard, others → storefront

**Password Management**
- Change password (requires current password)
- Reset flow: request → OTP emailed (10-min expiry) → verify OTP → set new password
- Reset token: `secrets.token_urlsafe(32)` stored on user model

**User Dashboard**
- Total orders, pending orders, total spend
- Recent 10 order items
- Referred users list with purchase status indicator
- Monnify pending-order reconciliation runs on load

**Profile**
- Edit first name, last name, phone
- Inline password change

---

## 2. Products & Catalogue

**Product Model**
- Fields: `name`, `description` (CKEditor5 rich text), `category`, `sku`, `stock`, `weight_kg`, `discount` (%), `additional_info`
- Role-based pricing: `customer_price`, `wholesaler_price`, `retailer_price`, `hospital_price`, `pharmacy_price` — each role sees their own price, falls back to `customer_price`
- Gender targeting: `is_male`, `is_female`, `is_general` flags
- `is_best_seller` flag for homepage featured section

**Role-Based Minimum Quantities**
- End User: 1 | Retailer / Hospital / Pharmacy: 5 | Wholesaler: 10
- Enforced on add-to-cart

**Product Images**
- Multiple images per product
- Thumbnail designation with `is_thumbnail` flag

**Categories**
- UUID PK, name, description

**Storefront Listing**
- Pagination (12 per page)
- Filter by category, gender (men / women)
- Full-text search on product name
- HTMX-powered filters and infinite scroll (no full-page reloads)

**Product Detail Page**
- Role-adjusted pricing for authenticated users
- Related products from same category (up to 5)
- Minimum quantity display per role

---

## 3. Cart

- One-to-one with authenticated user; session-based for anonymous users
- Price snapshot at time of adding (price changes don't affect active carts)
- Prevents duplicate product entries (`unique_together`)
- Add, update quantity, remove items
- Cart item count globally available via context processor

**Cart Drawer**
- Slide-out sidebar (not a separate page)
- Served via HTMX as a partial — no full-page reload on open/update/remove

---

## 4. Checkout

- Login required
- Collects: shipping address, city (Speedaf city code), state (Speedaf province code), phone
- HTMX cascading dropdown: selecting a state populates cities from local `speedaf_areas.json`
- Real-time Speedaf shipping fee quote (weight × destination)
- Referrer automatically captured from `request.user.referred_by`
- Supports both Paystack redirect flow and Monnify Web SDK (AJAX) flow

---

## 5. Payments

**Paystack**
- Initialize transaction via API, verify via reference
- Amount sent in kobo
- `paystack_reference` stored on Order

**Monnify**
- OAuth2 token auth
- Initialize transaction, verify by payment or transaction reference
- Browser-side Web SDK (no server-side redirect)
- Payment methods: CARD, ACCOUNT_TRANSFER, USSD
- **Automatic reconciliation**: on user dashboard/order page load, checks up to 3 recent pending Monnify orders (within 2 days), rate-limited to once per 45 seconds via session

**Provider Switching**
- `PaymentProviderConfig` singleton — admin switches Paystack ↔ Monnify without code changes or redeployment

**Payment References**
- Format: `WS-{secrets.token_urlsafe(16)}`
- Retry payment generates a new reference for abandoned transactions

---

## 6. Orders

**Order Model**
- 19 status values matching Speedaf action codes:
  `pending` → `ordered` → `inbound` → `packaged` → `outbound` → `picked` → `departed` → `arrived` → `customs_declaration` → `flight_departed` → `flight_landed` → `in_clearance` → `clearance_exception` → `clearance_completed` → `in_delivery` → `delivered` / `returning` / `returned` / `cancelled`
- Payment status: `pending`, `completed`, `failed`, `refunded`
- Shipping fields: address, city, state, phone, fee
- SpeedAF fields: `speedaf_order_id`, `tracking_number`, `tracking_notes`
- Referral fields: `referral_code_used`, `referrer` FK
- `status_badge_class` property returns Tailwind CSS colour classes for badges

**Inventory Management**
- Atomically deducts stock on payment completion using `Greatest(stock - qty, 0)` (prevents negative stock)
- `inventory_deducted` flag prevents double-deduction

**Post-Payment Flow**
- Mark order paid → create SpeedAF shipping order → save tracking number → send confirmation email → clear cart

**Order History (User)**
- Paginated (10/page) with infinite scroll
- Per-order detail page: items, shipping info, 5-step Speedaf-aware timeline, tracking notes

---

## 7. Shipping — SpeedAF Express Integration

**Authentication**
- MD5 signature: `md5(timestamp + appKey + sortedJSON)` sent as `{ data, sign }` with `?appCode=` query param

**Shipping Rate Quote**
- Endpoint: `/open-api/fee/getFee`
- Returns NGN fee based on weight + sender/destination city codes

**Create Shipping Order**
- Endpoint: `/open-api/express/order/createOrder`
- Auto-retry with multiple `(ship_type, tax_method)` combinations to handle SpeedAF configuration mismatches
- Returns `(speedaf_order_id, waybill_number)`

**Shipment Tracking**
- Endpoint: `/open-api/express/track/query`
- Returns full event history per waybill (newest-first)
- Maps 20 Speedaf action codes to order status values

**Periodic Tracking Polls (Celery)**
- `scope='lagos'`: hourly | `scope='national'`: daily midnight | `scope='all'`: manual
- Only polls orders in active (non-terminal) statuses
- Updates `order.status` + `order.tracking_notes` on change
- Schedules are defined in `CELERY_BEAT_SCHEDULE` (currently commented out for manual testing)

**Areas Lookup**
- Local `speedaf_areas.json` with all Nigerian provinces and cities
- Cascading province → city dropdown in checkout
- Sender location auto-normalization validates configured city/province pair

---

## 8. Admin Dashboard

**Access Control**
- `admin_required` decorator (role check + login required)
- Separate login at `/admin-dashboard/login/`
- Admin password reset OTP printed to server log (not emailed)
- Admin invite: creates account with temp password, sends login email

**Overview**
- KPIs: total orders, pending orders, total users, revenue, reward points issued, referral orders
- Top 5 referrers by successful referral orders
- Top 5 selling products (units sold + stock)
- Monthly sales chart: current year vs previous year
- Last 7 days daily revenue chart
- Recent notifications (orders + tickets)

**Product Management**
- List with units sold, revenue, stock status (in-stock / low-stock ≤10 / out-of-stock)
- Add / edit product (CKEditor5 description, images, thumbnail, role prices)
- Delete product
- Manage product images (set thumbnail, add, delete)
- Export to CSV (all role prices, units sold, revenue)

**Category Management**
- List, add, edit, delete (HTMX partial forms)

**Order Management**
- List filtered by status group
- Order detail with items breakdown and delivery fee
- Tracking board with 8-step progress map and manual status override
- Delete / cancel order
- Export to CSV

**User Segment Management** (separate pages per role)
- Wholesalers, Retailers, Hospitals, Pharmacies, End Users, all Customers
- User list with `total_orders` + `total_spent` annotations, active/inactive stats
- User detail: full profile, last 10 orders, reward point ledger, referral stats
- Export to CSV per segment

**Blog Management**
- Post list, add/edit (CKEditor5, cover image, category, publish toggle)
- Delete post, toggle publish
- Category CRUD with auto-slug

**Analytics**
- Monthly user signups chart for current year

**Reward Settings**
- Configure `points_per_purchase` and `referral_bonus_points`
- Shows total points issued, users with points, total referral orders

**Payment Settings**
- Switch active provider (Paystack ↔ Monnify) via DB config — no redeployment needed

**Notifications Centre**
- Lists recent orders + recent tickets
- Filter by type (all / orders / tickets)
- Session-based dismissal, delete individual notifications

---

## 9. Referral & Rewards System

- Every user gets a `referral_code` auto-generated on save
- Referral captured: `user.referred_by` FK set at signup if referral code was used
- `referral_code_used` + `referrer` FK stored on each Order
- **`RewardPointConfig`** singleton (admin-configurable): `points_per_purchase` + `referral_bonus_points`
- **Point awarding** (currently disabled — can be re-enabled in `ecom/models.py`):
  - Purchase reward: buyer earns `points_per_purchase` on payment completion
  - Referral bonus: referrer earns `referral_bonus_points` on referred user's **first** completed purchase
  - Both guarded by `purchase_points_awarded` / `referral_points_awarded` flags + atomic transactions
- **`RewardPointLedger`**: immutable audit log of every credit (linked to User + Order, reason: `purchase` or `referral`)
- Profile page shows reward balance + paginated ledger (HTMX "load more")

---

## 10. Blog (Public)

- Published posts listing, paginated (9/page)
- Category filter tabs
- Infinite scroll via HTMX
- Post detail with related posts (same category, up to 3)
- Auto-slug with collision-safe incrementing (`slug-1`, `slug-2`, …)
- Cover image upload

---

## 11. Support Tickets

**User Side**
- Create ticket: title, description, priority (low / medium / high / urgent)
- View own tickets and admin response
- Confirmation email on creation

**Admin Side**
- All tickets list
- Ticket detail: assign to admin, set status (open → in_progress → resolved → closed), write response
- Response email sent to user
- Tickets shown in admin notification centre

---

## 12. Emails

- **Backend**: Zoho SMTP (`smtp.zoho.com:587`, TLS)

| Template | Trigger |
|---|---|
| Verification OTP | Signup |
| Welcome | Email verified |
| Password Reset OTP | Reset request |
| Order Confirmation | Payment completed |
| Ticket Confirmation | Support ticket created |
| Ticket Response | Admin responds |

---

## 13. Static / Legal Pages

- Terms of Service
- Privacy Policy
- Return Policy
- Delivery Policy

---

## 14. Tech Stack

| Component | Technology |
|---|---|
| Framework | Django 5.2.8 |
| Database | SQLite (local) / PostgreSQL (production) |
| CSS | Tailwind CSS via `django-tailwind` |
| Reactivity | HTMX (cart, filters, dropdowns, infinite scroll) |
| Rich Text Editor | django-ckeditor-5 |
| Task Queue | Celery + Redis |
| Scheduled Tasks | django-celery-beat (DatabaseScheduler) |
| Django Admin UI | Unfold (teal theme) |
| Container | Docker + docker-compose (web, celery, celery-beat, db, redis) |
| Production Server | Gunicorn + Nginx |
| Config | python-decouple (`.env`) |

---

## 15. Security

- `admin_required` decorator on all admin views (role + authentication check)
- OTP rate-limiting (3 failed attempts → lockout) and expiry enforcement
- `secrets` module for OTP codes, tokens, payment references (not `random`)
- HTTPS-only session and CSRF cookies in production
- HSTS with preload (`31536000` seconds, subdomains + preload)
- `X-Frame-Options: DENY`
- `SECURE_BROWSER_XSS_FILTER`, `SECURE_CONTENT_TYPE_NOSNIFF`
- Atomic DB transactions for inventory deduction and reward point awarding
- Cart ownership verified before update/remove operations
