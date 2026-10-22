from .models import SiteSettings, heroSection
from django.db.models import Count, Q
from .models import Post, Comment, User
from django.utils import timezone
from datetime import timedelta

def site_settings(request):
    return {
        "url_media": SiteSettings.objects.first()
    }

def heroSections(request):
    hero = heroSection.objects.first()
    # إذا حُذف ملف الصورة من القرص نُخفيها بدل عرض صورة مكسورة (يظهر التدرج اللوني الافتراضي)
    hero_bg_available = bool(hero and hero.background_image and hero.background_image.storage.exists(hero.background_image.name))
    return {
        "hero_sections": hero,
        "hero_bg_available": hero_bg_available,
    }
