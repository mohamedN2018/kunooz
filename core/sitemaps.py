from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from .models import Post


class HttpsDomainSitemap(Sitemap):
    """
    يستخدم MAIN_DOMAIN بدلاً من سجل django_site
    (الذي كان example.com فظهرت كل روابط الـ sitemap في الإنتاج على example.com).
    """
    protocol = "https"

    def get_domain(self, site=None):
        return settings.MAIN_DOMAIN


class StaticViewSitemap(HttpsDomainSitemap):
    changefreq = "daily"
    priority = 1.0

    def items(self):
        return ["home", "courses", "articles", "grants", "books", "about", "privacy", "advertise"]

    def location(self, item):
        return reverse(item)


class PostSitemap(HttpsDomainSitemap):
    changefreq = "weekly"
    priority = 0.9

    def items(self):
        return Post.objects.live().order_by("-publish_date", "-id")

    def lastmod(self, obj):
        return obj.updated_at

class TagSitemap(HttpsDomainSitemap):
    changefreq = "weekly"
    priority = 0.5

    def items(self):
        from .models import Tag
        # الوسوم التي لها منشور ظاهر فقط (صفحات فارغة تضر SEO)
        return Tag.objects.filter(posts__in=Post.objects.live()).distinct().order_by("name")
