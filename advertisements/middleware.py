from django.utils.deprecation import MiddlewareMixin
from django.core.cache import cache
import hashlib

class AdTrackingMiddleware(MiddlewareMixin):
    """
    ميدلوار لتتبع ظهور الإعلانات ومنع الاحتيال
    """
    def process_request(self, request):
        # تتبع طلبات الظهورات والنقرات
        if request.path.startswith('/ads/impression/') or request.path.startswith('/ads/click/'):
            # استخراج معرف الإعلان من الرابط
            ad_id = request.path.split('/')[-2]
            
            # إنشاء مفتاح فريد لهذا المستخدم للإعلان
            user_key = self._get_user_key(request, ad_id)
            
            if request.path.startswith('/ads/impression/'):
                # التحقق من عدم تسجيل الظهور مؤخراً لنفس المستخدم
                impression_key = f'impression_{user_key}'
                if not cache.get(impression_key):
                    cache.set(impression_key, True, 3600)  # ساعة واحدة
                else:
                    # تجاهل الظهور المكرر
                    return None
            
            elif request.path.startswith('/ads/click/'):
                # التحقق من عدم تسجيل النقرة مؤخراً
                click_key = f'click_{user_key}'
                if not cache.get(click_key):
                    cache.set(click_key, True, 300)  # 5 دقائق
                else:
                    # تجاهل النقرة المكررة
                    return None
        
        return None
    
    def _get_user_key(self, request, ad_id):
        """
        توليد مفتاح فريد للمستخدم بناءً على معلوماته
        """
        # استخدام IP + User-Agent + Ad ID
        ip = request.META.get('REMOTE_ADDR', '')
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        key_string = f"{ip}_{user_agent}_{ad_id}"
        return hashlib.md5(key_string.encode()).hexdigest()
