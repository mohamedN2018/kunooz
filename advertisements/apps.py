from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

class AdvertisementsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'advertisements'
    verbose_name = _('Advertisement Management')
    
    def ready(self):
        # استيراد إشارات (signals) إذا كانت موجودة
        try:
            import advertisements.signals
        except ImportError:
            pass
