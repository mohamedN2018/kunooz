"""بيانات منظمة (JSON-LD) آمنة: تُبنى كقاموس Python وتُرمَّز بـ json (يتعامل مع علامات الاقتباس والسطور)."""
import json

from django import template
from django.conf import settings
from django.urls import NoReverseMatch, reverse
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe

register = template.Library()

SECTION_URLS = {'courses': 'courses', 'articles': 'articles', 'grants': 'grants', 'books': 'books'}


def _abs(path):
    return f"https://{settings.MAIN_DOMAIN}{path}"


def _dump(data):
    # يمنع إغلاق وسم script من داخل المحتوى
    text = json.dumps(data, ensure_ascii=False)
    for ch in '<>&':
        text = text.replace(ch, chr(92) + 'u%04x' % ord(ch))
    return mark_safe(f'<script type="application/ld+json">{text}</script>')


@register.simple_tag
def post_jsonld(post, site=None):
    site_name = getattr(site, 'site_name', None) or 'كنوز'
    image = post.get_main_image
    article = {
        '@context': 'https://schema.org',
        '@type': 'Article',
        'headline': post.display_title[:110],
        'description': strip_tags(post.display_description)[:300],
        'inLanguage': 'ar',
        'author': {'@type': 'Person', 'name': post.author.get_full_name() or post.author.username},
        'publisher': {'@type': 'Organization', 'name': site_name},
        'mainEntityOfPage': {'@type': 'WebPage', '@id': _abs(post.get_absolute_url())},
    }
    if post.publish_date:
        article['datePublished'] = post.publish_date.isoformat()
    if post.updated_at:
        article['dateModified'] = post.updated_at.isoformat()
    if image:
        article['image'] = [_abs(image.url)]
    if site is not None and getattr(site, 'site_logo', None):
        article['publisher']['logo'] = {'@type': 'ImageObject', 'url': _abs(site.site_logo.url)}
    tags = [t.name for t in post.tags.all()]
    if tags:
        article['keywords'] = ', '.join(tags)
    article['articleSection'] = post.category.name

    crumbs = [{'name': 'الرئيسية', 'url': _abs(reverse('home'))}]
    section = SECTION_URLS.get(post.category.category_type)
    if section:
        try:
            crumbs.append({'name': post.category.get_category_type_display(), 'url': _abs(reverse(section))})
        except NoReverseMatch:
            pass
    crumbs.append({'name': post.title, 'url': _abs(post.get_absolute_url())})
    breadcrumb = {
        '@context': 'https://schema.org',
        '@type': 'BreadcrumbList',
        'itemListElement': [
            {'@type': 'ListItem', 'position': i, 'name': c['name'], 'item': c['url']}
            for i, c in enumerate(crumbs, 1)
        ],
    }
    return _dump(article) + _dump(breadcrumb)


@register.simple_tag
def website_jsonld(site=None):
    site_name = getattr(site, 'site_name', None) or 'كنوز'
    return _dump({
        '@context': 'https://schema.org',
        '@type': 'WebSite',
        'name': site_name,
        'url': _abs('/'),
        'inLanguage': 'ar',
        'potentialAction': {
            '@type': 'SearchAction',
            'target': {'@type': 'EntryPoint', 'urlTemplate': _abs('/search/') + '?q={search_term_string}'},
            'query-input': 'required name=search_term_string',
        },
    })
