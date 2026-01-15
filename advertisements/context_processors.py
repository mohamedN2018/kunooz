from django.utils.translation import gettext_lazy as _
from django.conf import settings

def settings_context(request):
    return {
        'advertisements_enabled': settings.ADVERTISEMENTS_ENABLED,
    }


def ad_context(request):
    """
    معالج سياق لإضافة معلومات الإعلانات إلى جميع القوالب
    """
    from django.core.cache import cache
    from django.utils import timezone
    
    context = {}
    
    # إضافة تعداد الإعلانات النشطة (مخبأ لأداء أفضل)
    if request.user.is_authenticated and request.user.user_type in ['admin', 'editor']:
        cache_key = 'active_ads_count'
        active_count = cache.get(cache_key)
        
        if active_count is None:
            from .models import Advertisement
            active_count = sum(1 for ad in Advertisement.objects.all() if ad.is_active())
            cache.set(cache_key, active_count, 300)  # 5 دقائق
        
        context['active_ads_count'] = active_count
    
    return context
