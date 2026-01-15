import logging
from django.core.cache import cache
from django.utils import timezone
from django.db.models import Sum
from .models import Advertisement
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

def get_ad_analytics(start_date=None, end_date=None):
    """
    الحصول على تحليلات الإعلانات لفترة محددة
    """
    if not start_date:
        start_date = timezone.now() - timedelta(days=30)
    if not end_date:
        end_date = timezone.now()
    
    ads = Advertisement.objects.filter(
        start_date__gte=start_date,
        end_date__lte=end_date
    )
    
    analytics = {
        'total_impressions': ads.aggregate(Sum('impressions'))['impressions__sum'] or 0,
        'total_clicks': ads.aggregate(Sum('clicks'))['clicks__sum'] or 0,
        'total_ads': ads.count(),
        'active_ads': sum(1 for ad in ads if ad.is_active()),
        'by_type': {},
        'by_placement': {},
    }
    
    # تحليل حسب النوع
    for ad_type, _ in Advertisement.AD_TYPE_CHOICES:
        type_ads = ads.filter(ad_type=ad_type)
        analytics['by_type'][ad_type] = {
            'count': type_ads.count(),
            'impressions': type_ads.aggregate(Sum('impressions'))['impressions__sum'] or 0,
            'clicks': type_ads.aggregate(Sum('clicks'))['clicks__sum'] or 0,
        }
    
    # تحليل حسب المكان
    placements = set(ads.values_list('placement__name', flat=True))
    for placement in placements:
        placement_ads = ads.filter(placement__name=placement)
        analytics['by_placement'][placement] = {
            'count': placement_ads.count(),
            'impressions': placement_ads.aggregate(Sum('impressions'))['impressions__sum'] or 0,
            'clicks': placement_ads.aggregate(Sum('clicks'))['clicks__sum'] or 0,
        }
    
    return analytics

def clear_ad_cache(placement_code=None):
    """
    مسح الكاش الخاص بالإعلانات
    """
    if placement_code:
        cache.delete(f'ad_{placement_code}_*')
    else:
        # مسح كل كاش الإعلانات
        cache.delete_many([key for key in cache.keys('ad_*')])
    
    # مسح إحصائيات الكاش
    cache.delete('active_ads_count')
    logger.info(f"Ad cache cleared for placement: {placement_code or 'all'}")

def validate_ad_image(image):
    """
    التحقق من صحة صورة الإعلان
    """
    import os
    from PIL import Image
    
    # التحقق من الامتداد
    allowed_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
    ext = os.path.splitext(image.name)[1].lower()
    
    if ext not in allowed_extensions:
        return False, _('Invalid image format. Allowed: JPG, PNG, GIF, WebP')
    
    # التحقق من الحجم (5MB كحد أقصى)
    if image.size > 5 * 1024 * 1024:
        return False, _('Image size should not exceed 5MB')
    
    # محاولة فتح الصورة للتحقق من صحتها
    try:
        img = Image.open(image)
        img.verify()  # التحقق من أن الصورة صالحة
        return True, None
    except Exception as e:
        logger.error(f"Invalid image: {e}")
        return False, _('Invalid or corrupted image')
    
    return True, None

def generate_ad_code(ad_type, content, link, ad_id):
    """
    توليد كود HTML/JavaScript للإعلان
    """
    base_url = '/ads/'  # تأكد من ضبط هذا حسب إعداداتك
    
    if ad_type == 'banner':
        return f'''
        <div class="ad-banner" data-ad-id="{ad_id}">
            <a href="{base_url}click/{ad_id}/" target="_blank" 
               onclick="this.parentNode.querySelector('.ad-impression').src='{base_url}impression/{ad_id}/';">
                <img src="{content}" alt="Advertisement" class="img-fluid">
            </a>
            <img src="{base_url}impression/{ad_id}/" class="ad-impression" style="display:none;">
        </div>
        '''
    
    elif ad_type == 'text':
        return f'''
        <div class="ad-text" data-ad-id="{ad_id}">
            <a href="{base_url}click/{ad_id}/" target="_blank" 
               onclick="this.parentNode.querySelector('.ad-impression').src='{base_url}impression/{ad_id}/';"
               class="text-ad-link">
                {content}
            </a>
            <img src="{base_url}impression/{ad_id}/" class="ad-impression" style="display:none;">
        </div>
        '''
    
    elif ad_type == 'html':
        # HTML مخصص - نضيف فقط تتبع
        return f'''
        <div data-ad-id="{ad_id}">
            {content}
            <script>
            document.addEventListener('DOMContentLoaded', function() {{
                var adDiv = document.querySelector('[data-ad-id="{ad_id}"]');
                var links = adDiv.querySelectorAll('a');
                links.forEach(function(link) {{
                    link.addEventListener('click', function() {{
                        var img = new Image();
                        img.src = '{base_url}click/{ad_id}/';
                    }});
                }});
                
                // تسجيل الظهور
                var impression = new Image();
                impression.src = '{base_url}impression/{ad_id}/';
            }});
            </script>
        </div>
        '''
    
    elif ad_type == 'video':
        return f'''
        <div class="ad-video" data-ad-id="{ad_id}">
            <video width="100%" controls onclick="window.open('{base_url}click/{ad_id}/', '_blank');">
                <source src="{content}" type="video/mp4">
                Your browser does not support the video tag.
            </video>
            <img src="{base_url}impression/{ad_id}/" class="ad-impression" style="display:none;">
        </div>
        '''
    
    return ''
