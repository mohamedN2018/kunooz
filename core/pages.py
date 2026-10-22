"""صفحات ثابتة: من نحن، سياسة الخصوصية، أعلن معنا، و ads.txt (مطلوبة لقبول الموقع في شبكات الإعلانات)."""
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from .models import Category, Post, SiteSettings


def _site():
    return SiteSettings.objects.first()


@require_GET
def about(request):
    site = _site()
    counts = dict(Post.objects.live().values_list('category__category_type').annotate(n=Count('id')))
    return render(request, 'pages/about.html', {
        'site': site,
        'counts': [(label, counts.get(key, 0)) for key, label in Category.CATEGORY_TYPES],
    })


@require_GET
def privacy(request):
    return render(request, 'pages/privacy.html', {'site': _site(), 'updated': timezone.localdate()})


@require_GET
def advertise(request):
    from advertisements.models import AdPlacement
    from analytics.models import PageView, VisitorSession
    since = timezone.now() - timezone.timedelta(days=30)
    sessions = VisitorSession.objects.filter(start_time__gte=since)
    return render(request, 'pages/advertise.html', {
        'site': _site(),
        'placements': AdPlacement.objects.filter(active=True).order_by('-priority'),
        # أرقام حقيقية من التحليلات (آخر 30 يوماً) — لا أرقام تقديرية
        'monthly_visits': sessions.count(),
        'monthly_unique': sessions.exclude(visitor_id=None).values('visitor_id').distinct().count()
                          + sessions.filter(visitor_id=None).count(),
        'monthly_pageviews': PageView.objects.filter(timestamp__gte=since).count(),
        'posts_count': Post.objects.live().count(),
    })


@require_GET
def ads_txt(request):
    site = _site()
    body = (site.ads_txt.strip() + '\n') if site and site.ads_txt.strip() else '# لا توجد شبكات إعلانات مسجلة بعد\n'
    return HttpResponse(body, content_type='text/plain; charset=utf-8')
