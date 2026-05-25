import logging
from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)

# Lagos province code in the Speedaf areas database
LAGOS_PROVINCE_CODE = getattr(settings, 'LAGOS_PROVINCE_CODE', 'NGR00023')

# Map Speedaf numeric `action` codes → Order.STATUS_CHOICES keys.
# Source: https://apis.speedaf.com/doc/en/track_query.html  (Action list)
SPEEDAF_STATUS_MAP = {
    '10':   'ordered',              # Ordered
    '150':  'inbound',              # Inbound (at Speedaf warehouse)
    '181':  'packaged',             # Packaged
    '190':  'outbound',             # Outbound (left warehouse)
    '1':    'picked',               # Picked from sender
    '2':    'departed',             # Departed from hub
    '3':    'arrived',              # Arrived at hub
    '402':  'customs_declaration',  # Customs declaration
    '220':  'flight_departed',      # Flight departed
    '230':  'flight_landed',        # Flight landed
    '360':  'in_clearance',         # In clearance
    '401':  'clearance_exception',  # Clearance exception
    '370':  'clearance_completed',  # Clearance completed
    '4':    'in_delivery',          # In delivery / out for delivery
    '16':   'delivered',            # Delivered by franchisee
    '18':   'delivered',            # Self collect
    '5':    'delivered',            # Collected / Delivered
    '-10':  'cancelled',            # Cancelled
    '-710': 'returning',            # Returning to sender
    '730':  'returned',             # Returned to sender
}

# Statuses that mean the shipment is still active and worth polling
ACTIVE_STATUSES = {
    'ordered', 'inbound', 'packaged', 'outbound',
    'picked', 'departed', 'arrived',
    'customs_declaration', 'flight_departed', 'flight_landed',
    'in_clearance', 'clearance_exception', 'clearance_completed',
    'in_delivery', 'returning',
}


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def poll_speedaf_tracking(self, scope='all'):
    """
    Periodic task: query Speedaf tracking for active orders with a waybill number.

    scope='lagos'    — only orders shipping within Lagos (NGR00023), polled hourly
    scope='national' — only orders shipping outside Lagos, polled daily at midnight
    scope='all'      — all active orders (for manual/ad-hoc runs)
    """
    from ecom.models import Order
    from ecom.services.speedaf import SpeedAFClient

    base_qs = Order.objects.filter(
        tracking_number__isnull=False,
        status__in=list(ACTIVE_STATUSES),
    ).exclude(tracking_number='')

    if scope == 'lagos':
        orders = base_qs.filter(shipping_state=LAGOS_PROVINCE_CODE)
    elif scope == 'national':
        orders = base_qs.exclude(shipping_state=LAGOS_PROVINCE_CODE)
    else:
        orders = base_qs

    if not orders.exists():
        logger.info("poll_speedaf_tracking[%s]: no active orders with tracking numbers.", scope)
        return

    client = SpeedAFClient()
    updated = 0
    errors = 0
    order_list = list(orders)  # evaluate once

    for order in order_list:
        try:
            data = client.track_shipment(order.tracking_number)
        except Exception as exc:
            logger.error(
                "poll_speedaf_tracking: exception calling track_shipment | order=%s tracking=%s error=%s",
                order.id, order.tracking_number, exc,
            )
            errors += 1
            continue

        if data is None:
            logger.warning(
                "poll_speedaf_tracking: tracking failed | order=%s tracking=%s",
                order.id, order.tracking_number,
            )
            errors += 1
            continue

        # track_shipment returns the tracks list directly (newest-first per Speedaf)
        events = data if isinstance(data, list) else []

        if not events:
            logger.debug(
                "poll_speedaf_tracking: no events yet | order=%s tracking=%s",
                order.id, order.tracking_number,
            )
            continue

        # Events are newest-first; take the latest one.
        latest = events[0] if isinstance(events[0], dict) else {}
        # Speedaf uses numeric `action` code; stringify for map lookup
        track_code = str(latest.get('action') or '')
        description = latest.get('msgEng') or latest.get('actionName') or track_code
        event_time = latest.get('time') or ''

        new_status = SPEEDAF_STATUS_MAP.get(track_code)  # None means "don't change status"
        notes = f"[{event_time}] {description}" if event_time else description

        update_fields = ['tracking_notes', 'updated_at']
        order.tracking_notes = notes

        if new_status and new_status != order.status:
            old_status = order.status
            order.status = new_status
            update_fields.append('status')
            logger.info(
                "poll_speedaf_tracking: status updated | order=%s tracking=%s %s→%s note=%s",
                order.id, order.tracking_number, old_status, new_status, notes,
            )

        order.save(update_fields=update_fields)
        updated += 1

    logger.info(
        "poll_speedaf_tracking[%s]: complete | checked=%d updated=%d errors=%d",
        scope, len(order_list), updated, errors,
    )


@shared_task(bind=True, max_retries=7)
def send_order_confirmation_email_task(self, order_id):
    """Send order confirmation email asynchronously via Celery.

    Uses exponential backoff: 60 s, 120 s, 240 s, 480 s, 960 s, 1920 s, 3840 s.
    This handles transient SMTP timeouts caused by slow or intermittent networks.
    """
    import uuid
    from django.conf import settings
    from django.core.mail import send_mail
    from django.template.loader import render_to_string
    from ecom.models import Order

    try:
        order = Order.objects.select_related('user').prefetch_related('items__product').get(pk=order_id)
    except Order.DoesNotExist:
        logger.error("send_order_confirmation_email_task: order %s not found", order_id)
        return

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
            f'Thank you for your order! Order #{str(order.id)[:8]}',
            settings.DEFAULT_FROM_EMAIL,
            [order.user.email],
            html_message=html_message,
            fail_silently=False,
        )
        logger.info("send_order_confirmation_email_task: sent for order %s", order_id)
    except Exception as exc:
        # Exponential backoff: 60s * 2^attempt → 60, 120, 240, 480, 960, 1920, 3840 s
        countdown = 60 * (2 ** self.request.retries)
        logger.warning(
            "send_order_confirmation_email_task: failed for order %s (attempt %d): %s — retrying in %ds",
            order_id, self.request.retries + 1, exc, countdown,
        )
        raise self.retry(exc=exc, countdown=countdown)
