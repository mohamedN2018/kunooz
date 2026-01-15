from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from .models import Advertisement, AdPlacement
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Advertisement)
def clear_ad_cache_on_save(sender, instance, **kwargs):
    """
    مسح الكاش عند حفظ إعلان جديد أو تعديله
    """
    if instance.placement:
        # مسح كاش هذا المكان المحدد
        cache.delete(f'ad_{instance.placement.code}_*')
    
    # مسح إحصائيات الكاش
    cache.delete('active_ads_count')
    logger.info(f'Ad cache cleared after save: {instance.title}')

@receiver(post_delete, sender=Advertisement)
def clear_ad_cache_on_delete(sender, instance, **kwargs):
    """
    مسح الكاش عند حذف إعلان
    """
    if instance.placement:
        cache.delete(f'ad_{instance.placement.code}_*')
    
    cache.delete('active_ads_count')
    logger.info(f'Ad cache cleared after delete: {instance.title}')

@receiver(post_save, sender=AdPlacement)
@receiver(post_delete, sender=AdPlacement)
def clear_placement_cache(sender, instance, **kwargs):
    """
    مسح كاش الأماكن عند التغيير
    """
    cache.delete(f'ad_{instance.code}_*')
    logger.info(f'Placement cache cleared: {instance.code}')
