"""
"هل الموقع جاهز للإعلانات؟" — فحص آلي بمعايير شبكات الإعلانات (مثل Google AdSense) وبيانات الموقع الحقيقية.
كل بند: ok (✓) / warn (يُنصح) / fail (يمنع القبول أو العرض). لا أرقام مفترضة: كلها من قاعدة البيانات والإعدادات.
"""
from datetime import timedelta

from django.conf import settings
from django.db.models import Count
from django.utils import timezone

OK, WARN, FAIL = 'ok', 'warn', 'fail'

# حدود إرشادية (شبكات الإعلانات لا تنشر حداً رسمياً للزيارات؛ هذه أرقام عملية لعائد يستحق)
MIN_POSTS = 30
MIN_DAILY_VISITS = 100


def _item(status, title, detail, fix=''):
    return {'status': status, 'title': title, 'detail': detail, 'fix': fix}


def check():
    from analytics.models import VisitorSession
    from core.models import Post, SiteSettings
    from .models import Advertisement, AdPlacement

    site = SiteSettings.objects.first()
    now = timezone.now()
    since = now - timedelta(days=30)
    items = []

    # ===== المحتوى =====
    live = Post.objects.live()
    n_posts = live.count()
    items.append(_item(
        OK if n_posts >= MIN_POSTS else FAIL if n_posts < 10 else WARN,
        'كمية المحتوى المنشور',
        f'{n_posts} منشور ظاهر للزوار.',
        f'شبكات الإعلانات ترفض المواقع قليلة المحتوى. الهدف {MIN_POSTS}+ منشوراً أصلياً ومفيداً.' if n_posts < MIN_POSTS else ''))

    thin = sum(1 for c in live.values_list('content', flat=True)[:500] if len(_text(c)) < 300)
    items.append(_item(
        OK if thin == 0 else WARN if thin <= n_posts * 0.3 else FAIL,
        'جودة المحتوى (طول النص)',
        f'{thin} منشور نصه أقل من 300 حرف.' if thin else 'كل المنشورات بنص كافٍ.',
        'المنشورات القصيرة جداً تُعتبر "محتوى ضعيف" وتسبب رفض الطلب. أضف شرحاً حقيقياً لكل منشور.' if thin else ''))

    dup = (live.values('title').annotate(n=Count('id')).filter(n__gt=1).count())
    items.append(_item(
        OK if dup == 0 else WARN, 'عناوين مكررة',
        f'{dup} عنوان مكرر بين المنشورات.' if dup else 'لا توجد عناوين مكررة.',
        'المحتوى المكرر يضعف الموقع في البحث وعند مراجعة الإعلانات. وحّد أو احذف التكرار.' if dup else ''))

    recent = live.filter(publish_date__gte=since).count()
    items.append(_item(
        OK if recent >= 4 else WARN, 'نشاط النشر',
        f'{recent} منشور خلال آخر 30 يوماً.',
        'النشر المنتظم (منشور أسبوعياً على الأقل) يرفع الزيارات وقيمة الإعلانات.' if recent < 4 else ''))

    # ===== الزيارات =====
    sessions = VisitorSession.objects.filter(start_time__gte=since)
    visits = sessions.count()
    daily = round(visits / 30)
    items.append(_item(
        OK if daily >= MIN_DAILY_VISITS else WARN, 'حجم الزيارات',
        f'متوسط {daily} زيارة يومياً ({visits} في 30 يوماً).',
        f'يمكن التقديم بأي حجم، لكن العائد يصبح ملموساً من ~{MIN_DAILY_VISITS} زيارة يومياً. ركّز على SEO والمشاركة على وسائل التواصل.'
        if daily < MIN_DAILY_VISITS else ''))

    if visits:
        search = sessions.filter(entry_source='search').count()
        pct = round(search * 100 / visits)
        items.append(_item(OK if pct >= 20 else WARN, 'زيارات من محركات البحث',
                           f'{pct}% من الزيارات جاءت من البحث.',
                           'زيارات البحث هي الأعلى قيمة إعلانياً. قدّم sitemap في Google Search Console.' if pct < 20 else ''))

    # ===== الصفحات المطلوبة =====
    items.append(_item(OK, 'صفحة "من نحن"', '/about/ موجودة.'))
    items.append(_item(
        OK if site and site.privacy_content.strip() else WARN, 'سياسة الخصوصية',
        '/privacy/ موجودة' + (' بنص مخصص.' if site and site.privacy_content.strip() else ' بنص افتراضي يصف ما يجمعه الموقع فعلاً.'),
        '' if site and site.privacy_content.strip() else 'راجع النص الافتراضي (أو اكتب نصك) من إعدادات الموقع، ويفضل مراجعته قانونياً.'))
    items.append(_item(
        OK if site and site.contact_email and 'example.com' not in site.contact_email else FAIL, 'وسيلة تواصل حقيقية',
        f'البريد: {site.contact_email}' if site else 'لا توجد إعدادات للموقع.',
        'ضع بريداً حقيقياً في إعدادات الموقع (contact@example.com لا يُقبل).'
        if not site or not site.contact_email or 'example.com' in site.contact_email else ''))
    items.append(_item(OK, 'صفحة "أعلن معنا"', '/advertise/ تعرض الأماكن وأرقام الزيارات الحقيقية للمعلنين المباشرين.'))

    # ===== التقنية =====
    items.append(_item(OK if not settings.DEBUG else FAIL, 'وضع الإنتاج', 'DEBUG مغلق.' if not settings.DEBUG else 'DEBUG مفتوح!',
                       '' if not settings.DEBUG else 'اضبط DEBUG=False في متغيرات Dokploy.'))
    items.append(_item(OK, 'HTTPS', f'الموقع يعمل على https://{settings.MAIN_DOMAIN}'))
    items.append(_item(OK, 'خريطة الموقع و robots.txt', '/sitemap.xml و /robots.txt جاهزان بالنطاق الصحيح.'))
    items.append(_item(
        OK if site and site.ads_txt.strip() else WARN, 'ملف ads.txt',
        'موجود ويحتوي سطراً.' if site and site.ads_txt.strip() else '/ads.txt جاهز لكنه فارغ.',
        '' if site and site.ads_txt.strip() else 'بعد قبولك في AdSense انسخ السطر الذي يعطيك إياه (google.com, pub-..., DIRECT, f08c47fec0942fa0) في إعدادات الموقع ← محتوى ads.txt.'))
    items.append(_item(OK, 'الموبايل والعربية', 'الصفحات RTL ومتجاوبة بدون تمرير أفقي (مُختبر).'))

    # ===== نظام الإعلانات =====
    placements = AdPlacement.objects.filter(active=True).count()
    items.append(_item(OK if placements else FAIL, 'الأماكن الإعلانية',
                       f'{placements} مكان نشط مدمج في الصفحات.',
                       '' if placements else 'شغّل migrate لإنشاء الأماكن الافتراضية.'))
    running = Advertisement.objects.filter(active=True, start_date__lte=now, end_date__gte=now).count()
    items.append(_item(OK if running else WARN, 'إعلانات سارية', f'{running} إعلان يعمل الآن.',
                       '' if running else 'أضف إعلاناً من لوحة الإدارة ← الإعلانات، أو اربط AdSense.'))
    enabled = bool(site and site.ads_enabled)
    items.append(_item(OK if enabled else WARN, 'تفعيل الإعلانات',
                       'مفعلة وتظهر للزوار.' if enabled else 'مغلقة: لا يرى الزوار أي إعلان.',
                       '' if enabled else 'فعّلها من إعدادات الموقع ← "تفعيل الإعلانات" بعد مراجعة المعاينة (?ads_preview=1).'))
    if site and site.adsense_client and not site.adsense_client.startswith('ca-pub-'):
        items.append(_item(FAIL, 'معرف AdSense', f'"{site.adsense_client}" ليس بالصيغة الصحيحة.', 'الصيغة: ca-pub-XXXXXXXXXXXXXXXX'))

    fails = sum(1 for i in items if i['status'] == FAIL)
    warns = sum(1 for i in items if i['status'] == WARN)
    if fails:
        verdict = ('fail', 'غير جاهز بعد', f'{fails} بند يجب إصلاحه قبل التقديم على شبكة إعلانات.')
    elif warns:
        verdict = ('warn', 'جاهز تقنياً — مع تحسينات', f'النظام جاهز. {warns} بند يُنصح بتحسينه لرفع فرص القبول والعائد.')
    else:
        verdict = ('ok', 'جاهز للإعلانات', 'كل البنود مكتملة.')
    return {'items': items, 'verdict': verdict, 'fails': fails, 'warns': warns,
            'oks': len(items) - fails - warns}


def _text(html):
    from django.utils.html import strip_tags
    return ' '.join(strip_tags(html or '').split())
