from django.db.models import F
from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone

from .models import DailyWebsiteVisit


class WebsiteVisitTrackingMiddleware:
    """
    Track daily page visits and unique visitors for storefront pages only.

    A "visit" is counted once per page navigation (HTML response), not for
    every asset, API, or AJAX request. This gives realistic page-view numbers.
    """

    # Paths that are never counted as page visits
    EXCLUDED_PREFIXES = (
        '/admin-dashboard/',
        '/admin/',
        '/static/',
        '/media/',
        '/favicon.ico',
        '/robots.txt',
        '/sitemap.xml',
        '/ckeditor5/',
    )

    # Suffixes that indicate non-page requests (assets, feeds, data)
    EXCLUDED_SUFFIXES = (
        '.js', '.css', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp',
        '.ico', '.woff', '.woff2', '.ttf', '.eot', '.map', '.json', '.xml',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Only count GET requests that return an HTML page
        if (
            request.method == 'GET'
            and not self._is_excluded_path(request.path)
            and self._is_html_response(response)
        ):
            self._track_visit(request)

        return response

    def _is_excluded_path(self, path):
        if any(path.startswith(prefix) for prefix in self.EXCLUDED_PREFIXES):
            return True
        if any(path.lower().endswith(suffix) for suffix in self.EXCLUDED_SUFFIXES):
            return True
        return False

    def _is_html_response(self, response):
        content_type = response.get('Content-Type', '')
        return 'text/html' in content_type

    def _track_visit(self, request):
        try:
            today = timezone.localdate()
            stat, _ = DailyWebsiteVisit.objects.get_or_create(date=today)

            # Count every HTML page load as one visit
            DailyWebsiteVisit.objects.filter(pk=stat.pk).update(
                total_visits=F('total_visits') + 1
            )

            # Count unique visitor once per session per day
            if not request.session.session_key:
                request.session.save()

            unique_key = f"visit_tracked_{today.isoformat()}"
            if not request.session.get(unique_key):
                request.session[unique_key] = True
                DailyWebsiteVisit.objects.filter(pk=stat.pk).update(
                    unique_visitors=F('unique_visitors') + 1
                )
        except (OperationalError, ProgrammingError):
            # Database table may not exist yet during deployment before migrations.
            return


class SiteMaintenanceMiddleware:
    """
    Checks if the storefront is enabled.
    If disabled, renders a maintenance page for non-staff users.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        # Always allow requests to admin, admin-dashboard, static, media, etc.
        if (
            path.startswith('/admin/') or
            path.startswith('/myaccessadmin/') or
            path.startswith('/admin-dashboard/') or
            path.startswith('/static/') or
            path.startswith('/media/') or
            path.startswith('/favicon.ico') or
            path.startswith('/ckeditor5/')
        ):
            return self.get_response(request)

        # Always allow staff and superusers to bypass maintenance mode
        if request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser):
            return self.get_response(request)

        try:
            from ecom.models import SiteConfiguration
            config = SiteConfiguration.get_solo()
            if not config.is_enabled:
                from django.shortcuts import render
                return render(
                    request,
                    'maintenance.html',
                    {'message': config.maintenance_message},
                    status=503
                )
        except Exception:
            # Table might not exist yet during initial migrations
            pass

        return self.get_response(request)
