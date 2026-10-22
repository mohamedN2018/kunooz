"""
ينشئ الأماكن الإعلانية الموجودة فعلاً في قوالب الموقع ({% ad_slot '...' %}).
إضافة فقط: المكان الموجود بنفس الكود لا يُلمس، والتراجع يحذف فقط الأماكن الفارغة التي أنشأها.
"""
from django.db import migrations

PLACEMENTS = [
    # code, name, type, width, height, max_ads, priority, description
    ('header_banner', 'بانر أعلى الصفحات', 'header', 728, 90, 1, 10,
     'أسفل القائمة العلوية في كل الصفحات. المقاس القياسي 728×90 (Leaderboard)، ويصغر على الموبايل.'),
    ('home_middle', 'وسط الصفحة الرئيسية', 'between_posts', 970, 250, 1, 9,
     'بين أقسام الصفحة الرئيسية. 970×250 (Billboard) أو 728×90.'),
    ('post_top', 'أعلى المنشور', 'in_content', 728, 90, 1, 8,
     'تحت عنوان المنشور مباشرة وقبل المحتوى. أعلى ظهور في صفحات المنشورات.'),
    ('post_bottom', 'نهاية المنشور', 'in_content', 728, 250, 1, 7,
     'بعد محتوى المنشور وقبل المشاركة والتعليقات. مناسب للإعلانات النصية والبانرات.'),
    ('list_between', 'بين المنشورات في القوائم', 'between_posts', 728, 90, 1, 6,
     'داخل قوائم الكورسات/المقالات/المنح/الكتب بعد أول 6 منشورات.'),
    ('footer_banner', 'أعلى التذييل', 'footer', 728, 90, 1, 5,
     'قبل تذييل الموقع في كل الصفحات.'),
    ('sidebar_left', 'شريط جانبي (شاشات كبيرة)', 'sidebar', 160, 600, 1, 4,
     'عمودي ثابت على يسار الشاشة للشاشات العريضة فقط (≥ 1536px). 160×600 (Skyscraper).'),
]


def create(apps, schema_editor):
    AdPlacement = apps.get_model('advertisements', 'AdPlacement')
    for code, name, ptype, w, h, max_ads, priority, desc in PLACEMENTS:
        AdPlacement.objects.get_or_create(code=code, defaults=dict(
            name=name, placement_type=ptype, width=w, height=h, max_ads=max_ads, priority=priority,
            description=desc, active=True))


def remove(apps, schema_editor):
    AdPlacement = apps.get_model('advertisements', 'AdPlacement')
    AdPlacement.objects.filter(code__in=[p[0] for p in PLACEMENTS], advertisement__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('advertisements', '0003_daily_stats'),
    ]

    operations = [
        migrations.RunPython(create, remove),
    ]
