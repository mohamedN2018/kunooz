from django import template
from django.utils import timezone
from django.core.cache import cache
from advertisements.models import Advertisement
import random

register = template.Library()

@register.inclusion_tag('advertisements/ad_display.html', takes_context=True)
def show_ad(context, placement_code, count=1):
    """
    عرض إعلانات في مكان محدد
    الاستخدام في القالب: {% show_ad 'header' %}
    """
    cache_key = f'ad_{placement_code}_{count}'
    ads = cache.get(cache_key)
    
    if not ads:
        ads = list(Advertisement.objects.filter(
            placement__code=placement_code,
            active=True,
            start_date__lte=timezone.now(),
            end_date__gte=timezone.now()
        ).select_related('placement'))
        
        # ترتيب عشوائي للإعلانات
        if ads:
            ads = random.sample(ads, min(count, len(ads)))
            cache.set(cache_key, ads, 60)  # كاش لمدة دقيقة
    
    request = context.get('request')
    return {
        'ads': ads,
        'request': request,
        'count': count
    }

@register.filter
def calculate_ctr(ad):
    """حساب نسبة النقر للظهور"""
    if ad.impressions > 0:
        return round((ad.clicks / ad.impressions) * 100, 2)
    return 0

@register.filter
def days_remaining(ad):
    """حساب الأيام المتبقية للإعلان"""
    if ad.end_date:
        remaining = (ad.end_date.date() - timezone.now().date()).days
        return max(0, remaining)
    return 0

@register.filter
def ad_status_class(ad):
    """إرجاع كلاس CSS لحالة الإعلان"""
    if not ad.active:
        return 'bg-secondary'
    if not ad.is_active():
        return 'bg-warning'
    return 'bg-success'

@register.filter
def ad_status_text(ad):
    """إرجاع نص حالة الإعلان"""
    if not ad.active:
        return _('Inactive')
    if not ad.is_active():
        return _('Expired')
    return _('Active')
