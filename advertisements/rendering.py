"""
عرض الإعلانات داخل الصفحات (بدل iframe): {% load ad_tags %}{% ad_slot 'post_bottom' %}

- لا يظهر شيء إلا إذا فُعّلت الإعلانات من إعدادات الموقع، أو للمشرف مع ?ads_preview=1 (مربعات توضح الأماكن).
- الظهور يُحسب في المتصفح عند رؤية الإعلان فعلاً (50% منه لمدة ثانية) عبر static/js/kz-ads.js،
  لا عند تحميل الصفحة؛ فلا تُحسب البوتات ولا الإعلانات أسفل الصفحة التي لم يصلها الزائر.
"""
import random
import re

from django.core.cache import cache
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import Advertisement, AdPlacement

CACHE_KEY = 'kz_ad_slots'
CACHE_SECONDS = 60
YOUTUBE_RE = re.compile(r'(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)([\w-]{11})')


def clear_cache():
    cache.delete(CACHE_KEY)


def _slots():
    """كل الأماكن النشطة وإعلاناتها السارية الآن (مُخزّنة دقيقة واحدة)."""
    data = cache.get(CACHE_KEY)
    if data is not None:
        return data
    now = timezone.now()
    data = {}
    for p in AdPlacement.objects.filter(active=True):
        data[p.code] = {'name': p.name, 'width': p.width, 'height': p.height, 'max': p.max_ads or 1, 'ads': []}
    ads = (Advertisement.objects.filter(active=True, start_date__lte=now, end_date__gte=now, placement__active=True)
           .select_related('placement'))
    for ad in ads:
        if ad.placement.code in data:
            data[ad.placement.code]['ads'].append({'id': ad.id, 'priority': ad.priority, 'html': str(_ad_html(ad))})
    cache.set(CACHE_KEY, data, CACHE_SECONDS)
    return data


def _link_attrs(ad):
    rel = 'sponsored noopener' + (' nofollow' if ad.nofollow else '')
    return f'/ads/click/{ad.id}/', rel, mark_safe(' target="_blank"' if ad.target_blank else '')


def _ad_html(ad):
    click, rel, target = _link_attrs(ad)
    if ad.ad_type == 'banner' and ad.image:
        return format_html(
            '<a href="{}" rel="{}"{}><img src="{}" alt="{}" loading="lazy" decoding="async" '
            'width="{}" height="{}" class="kz-ad-img"></a>',
            click, rel, target, ad.image.url, ad.title, ad.placement.width, ad.placement.height)
    if ad.ad_type == 'text':
        return format_html('<a href="{}" rel="{}"{} class="kz-ad-text"><strong>{}</strong><span>{}</span></a>',
                           click, rel, target, ad.title, ad.text_content)
    if ad.ad_type == 'html':
        # كود يدخله المشرف فقط من لوحة الإدارة (مثل وحدة AdSense أو شبكة أخرى)؛ يُعرض كما هو
        return mark_safe(ad.html_code)
    if ad.ad_type == 'video' and ad.video_url:
        m = YOUTUBE_RE.search(ad.video_url)
        if m:
            return format_html(
                '<div class="kz-ad-video"><iframe src="https://www.youtube-nocookie.com/embed/{}" title="{}" '
                'loading="lazy" allow="encrypted-media; picture-in-picture" allowfullscreen></iframe></div>'
                '<a href="{}" rel="{}"{} class="kz-ad-cta">{}</a>',
                m.group(1), ad.title, click, rel, target, ad.title)
        return format_html('<video src="{}" muted playsinline controls preload="none" class="kz-ad-img"></video>'
                           '<a href="{}" rel="{}"{} class="kz-ad-cta">{}</a>', ad.video_url, click, rel, target, ad.title)
    return format_html('<a href="{}" rel="{}"{} class="kz-ad-text"><strong>{}</strong></a>', click, rel, target, ad.title)


def ads_visible(context):
    request = context.get('request')
    site = context.get('url_media')
    user = getattr(request, 'user', None)
    preview = bool(request and user and user.is_authenticated and user.is_staff and request.GET.get('ads_preview'))
    return bool(site and getattr(site, 'ads_enabled', False)), preview


def render_slot(context, code):
    enabled, preview = ads_visible(context)
    if not (enabled or preview):
        return ''

    slot = _slots().get(code)
    if slot is None:
        if preview:
            return format_html('<div class="kz-ad-slot kz-ad-preview"><span>المكان "{}" غير موجود أو غير نشط</span></div>', code)
        return ''

    ads = list(slot['ads'])
    random.shuffle(ads)  # تدوير الإعلانات المتساوية في الأولوية
    ads.sort(key=lambda a: -a['priority'])
    ads = ads[:slot['max']]

    if not ads:
        if preview:
            return format_html(
                '<div class="kz-ad-slot kz-ad-preview" style="min-height:{}px"><span>مكان إعلاني: {} '
                '<small>({} · {}×{})</small></span></div>',
                min(slot['height'], 250), slot['name'], code, slot['width'], slot['height'])
        return ''

    inner = mark_safe(''.join(
        str(format_html('<div class="kz-ad" data-ad-id="{}"{}>{}</div>', a['id'],
                        mark_safe(' data-preview="1"') if preview and not enabled else '', mark_safe(a['html'])))
        for a in ads))
    return format_html('<aside class="kz-ad-slot" data-slot="{}" aria-label="إعلان"><span class="kz-ad-label">إعلان</span>{}</aside>',
                       code, inner)
