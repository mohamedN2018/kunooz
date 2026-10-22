from django.conf import settings
from django.contrib.syndication.views import Feed
from django.utils.feedgenerator import Rss201rev2Feed
from django.utils.html import strip_tags

from .models import Category, Post, SiteSettings


class LatestPostsFeed(Feed):
    """خلاصة RSS لأحدث المنشورات (كل الأقسام أو قسم واحد عبر /feed/<type>/)."""
    feed_type = Rss201rev2Feed
    language = 'ar'

    def get_object(self, request, section=None):
        types = dict(Category.CATEGORY_TYPES)
        return section if section in types else None

    def title(self, section):
        site = SiteSettings.objects.first()
        name = site.site_name if site else 'كنوز'
        return f"{name} — {dict(Category.CATEGORY_TYPES)[section]}" if section else f"{name} — أحدث المنشورات"

    # روابط مطلقة على MAIN_DOMAIN؛ النسبية كانت تُكمَّل من جدول django_site (example.com)
    def link(self, section):
        return f"https://{settings.MAIN_DOMAIN}/" + (f'{section}/' if section else '')

    def feed_url(self, section):
        return f"https://{settings.MAIN_DOMAIN}/feed/" + (f'{section}/' if section else '')

    def description(self, section):
        site = SiteSettings.objects.first()
        return (site.site_description if site and site.site_description else 'منصة كنوز التعليمية')

    def items(self, section):
        qs = Post.objects.live().select_related('category', 'author').order_by('-publish_date')
        if section:
            qs = qs.filter(category__category_type=section)
        return qs[:30]

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return strip_tags(item.display_description)[:400]

    def item_pubdate(self, item):
        return item.publish_date

    def item_updateddate(self, item):
        return item.updated_at

    def item_author_name(self, item):
        return item.author.get_full_name() or item.author.username

    def item_categories(self, item):
        return [item.category.name] + [t.name for t in item.tags.all()]

    def item_link(self, item):
        return f"https://{settings.MAIN_DOMAIN}{item.get_absolute_url()}"
