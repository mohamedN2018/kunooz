from django.core.cache import cache
from django.shortcuts import render

from .models import SiteSettings

MAINTENANCE_CACHE_KEY = 'site_maintenance_mode'
# مسارات تعمل دائماً حتى يستطيع المشرف الدخول وإيقاف الوضع
ALWAYS_ALLOWED = ('/admin/', '/login/', '/logout/', '/static/', '/media/', '/robots.txt', '/health')


class MaintenanceModeMiddleware:
    """
    يفعّل "وضع الصيانة" من إعدادات الموقع (كان الخيار موجوداً دون أي تأثير).
    الزوار يرون صفحة صيانة (503)، والـ staff يتصفح الموقع عادياً.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._enabled() and not request.path.startswith(ALWAYS_ALLOWED):
            user = getattr(request, 'user', None)
            if not (user and user.is_authenticated and user.is_staff):
                response = render(request, 'errors/maintenance.html', status=503)
                response['Retry-After'] = '3600'
                return response
        return self.get_response(request)

    @staticmethod
    def _enabled():
        value = cache.get(MAINTENANCE_CACHE_KEY)
        if value is None:
            site = SiteSettings.objects.only('maintenance_mode').first()
            value = bool(site and site.maintenance_mode)
            cache.set(MAINTENANCE_CACHE_KEY, value, 30)
        return value
