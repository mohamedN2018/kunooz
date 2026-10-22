"""
حسابات لوحة "حركة الزوار": من دخل، من خرج، كم متصل الآن، زوار فريدون/جدد/عائدون، المصادر، الأجهزة...
كل الدوال تأخذ نطاقاً زمنياً (start, end) فتتفق الأرقام في كل أجزاء اللوحة.
"""
from collections import OrderedDict
from datetime import datetime, time, timedelta

from django.db.models import Avg, Count, F, Q
from django.db.models.functions import TruncDate, TruncHour
from django.utils import timezone

from .middleware import SESSION_TIMEOUT_SECONDS
from .models import PageView, VisitorSession

ONLINE_WINDOW = timedelta(minutes=5)

RANGES = OrderedDict([
    ('today', 'اليوم'),
    ('yesterday', 'أمس'),
    ('7d', 'آخر 7 أيام'),
    ('30d', 'آخر 30 يوماً'),
    ('90d', 'آخر 90 يوماً'),
])

SOURCE_LABELS = {'direct': 'مباشر', 'search': 'محركات البحث', 'social': 'شبكات التواصل', 'referral': 'مواقع أخرى', '': 'غير محدد'}
DEVICE_LABELS = {'mobile': 'موبايل', 'desktop': 'كمبيوتر', 'tablet': 'تابلت'}


def resolve_range(key):
    key = key if key in RANGES else '7d'
    tz = timezone.get_current_timezone()
    today = timezone.localdate()
    midnight = lambda d: timezone.make_aware(datetime.combine(d, time.min), tz)
    if key == 'today':
        start, end = midnight(today), timezone.now()
    elif key == 'yesterday':
        start, end = midnight(today - timedelta(days=1)), midnight(today)
    else:
        days = int(key[:-1])
        start, end = midnight(today - timedelta(days=days - 1)), timezone.now()
    return key, start, end


def close_stale_sessions():
    """
    الجلسة التي لم يصلها أي نشاط منذ 30 دقيقة تُعتبر "خرج" (لمن أغلق المتصفح دون إشارة مغادرة).
    تُستدعى عند فتح اللوحة؛ لا تحتاج cron.
    """
    cutoff = timezone.now() - timedelta(seconds=SESSION_TIMEOUT_SECONDS)
    stale = VisitorSession.objects.filter(is_active=True).filter(
        Q(last_seen__lt=cutoff) | Q(last_seen__isnull=True, start_time__lt=cutoff)
    )
    # وقت الخروج = آخر نشاط (وليس لحظة الإغلاق)
    stale.filter(last_seen__isnull=False).update(is_active=False, end_time=F('last_seen'))
    stale.filter(last_seen__isnull=True).update(is_active=False, end_time=F('start_time'))


def online_now():
    since = timezone.now() - ONLINE_WINDOW
    return (VisitorSession.objects.filter(is_active=True)
            .filter(Q(last_seen__gte=since) | Q(last_seen__isnull=True, start_time__gte=since))
            .select_related('country', 'user'))


def _bucket_series(qs, field, start, end, hourly):
    trunc = TruncHour(field) if hourly else TruncDate(field)
    rows = qs.annotate(b=trunc).values('b').annotate(n=Count('id')).order_by('b')
    counts = {}
    for r in rows:
        b = r['b']
        if b is None:
            continue
        key = timezone.localtime(b).replace(minute=0, second=0, microsecond=0) if hourly else b
        counts[key] = counts.get(key, 0) + r['n']
    labels, points = [], []
    if hourly:
        cur = timezone.localtime(start).replace(minute=0, second=0, microsecond=0)
        stop = timezone.localtime(end)
        while cur <= stop:
            labels.append(cur.strftime('%H:00'))
            points.append(counts.get(cur, 0))
            cur += timedelta(hours=1)
    else:
        cur, stop = timezone.localtime(start).date(), timezone.localtime(end).date()
        while cur <= stop:
            labels.append(cur.strftime('%m/%d'))
            points.append(counts.get(cur, 0))
            cur += timedelta(days=1)
    return labels, points


def _top(qs, field, labels=None, limit=8):
    rows = qs.values(field).annotate(n=Count('id')).order_by('-n')[:limit]
    total = qs.count() or 1
    out = []
    for r in rows:
        key = r[field]
        name = (labels or {}).get(key, key) if key not in (None, '') else 'غير معروف'
        out.append({'name': name, 'count': r['n'], 'pct': round(r['n'] * 100 / total)})
    return out


def _path(url):
    if not url:
        return ''
    from urllib.parse import urlparse
    p = urlparse(url)
    return p.path + (('?' + p.query) if p.query else '')


def traffic_report(range_key):
    close_stale_sessions()
    key, start, end = resolve_range(range_key)
    hourly = key in ('today', 'yesterday')

    entered = VisitorSession.objects.filter(start_time__gte=start, start_time__lt=end)
    exited = VisitorSession.objects.filter(is_active=False, end_time__gte=start, end_time__lt=end)
    views = PageView.objects.filter(timestamp__gte=start, timestamp__lt=end)

    sessions_n = entered.count()
    unique_n = entered.exclude(visitor_id=None).values('visitor_id').distinct().count()
    legacy_n = entered.filter(visitor_id=None).count()  # جلسات قبل إضافة معرف الزائر
    returning_n = entered.filter(is_returning=True).count()
    bounces = entered.filter(page_count__lte=1).count()
    avg = entered.filter(is_active=False).aggregate(a=Avg('total_time_spent'))['a']

    labels, entries = _bucket_series(entered, 'start_time', start, end, hourly)
    _, exits = _bucket_series(exited, 'end_time', start, end, hourly)

    # مدة المقارنة السابقة بنفس الطول
    span = end - start
    prev_n = VisitorSession.objects.filter(start_time__gte=start - span, start_time__lt=start).count()

    online = list(online_now()[:50])

    exits_recent = list(VisitorSession.objects.filter(is_active=False, end_time__isnull=False)
                        .select_related('country', 'user').order_by('-end_time')[:15])
    entries_recent = list(VisitorSession.objects.select_related('country', 'user').order_by('-start_time')[:15])

    return {
        'range_key': key,
        'ranges': RANGES,
        'start': start,
        'end': end,
        'kpis': {
            'online': len(online),
            'sessions': sessions_n,
            'unique': unique_n + legacy_n,
            'new': max(sessions_n - returning_n, 0),
            'returning': returning_n,
            'exits': exited.count(),
            'pageviews': views.count(),
            'pages_per_session': round(views.count() / sessions_n, 1) if sessions_n else 0,
            'bounce_rate': round(bounces * 100 / sessions_n) if sessions_n else 0,
            'avg_duration': _fmt_duration(avg),
            'logged_in': entered.exclude(user=None).count(),
            'change_pct': (round((sessions_n - prev_n) * 100 / prev_n) if prev_n else None),
        },
        'chart': {'labels': labels, 'entries': entries, 'exits': exits, 'hourly': hourly},
        'online': [_visitor_row(s) for s in online],
        'entries_recent': [_visitor_row(s) for s in entries_recent],
        'exits_recent': [_visitor_row(s) for s in exits_recent],
        'sources': _top(entered, 'entry_source', SOURCE_LABELS),
        'devices': _top(entered, 'device_type', DEVICE_LABELS),
        'browsers': _top(entered, 'browser'),
        'countries': _top(entered, 'country__name'),
        'top_pages': [{'name': _path(r['url']) or '/', 'count': r['n']} for r in
                      views.values('url').annotate(n=Count('id')).order_by('-n')[:10]],
        'landing_pages': [{'name': _path(r['landing_page']) or '/', 'count': r['n']} for r in
                          entered.values('landing_page').annotate(n=Count('id')).order_by('-n')[:8]],
        'exit_pages': [{'name': _path(r['exit_page']) or '/', 'count': r['n']} for r in
                       exited.exclude(exit_page=None).values('exit_page').annotate(n=Count('id')).order_by('-n')[:8]],
        'referrers': [{'name': r['referrer'][:80], 'count': r['n']} for r in
                      entered.exclude(referrer=None).values('referrer').annotate(n=Count('id')).order_by('-n')[:8]],
    }


def _fmt_duration(td):
    if not td:
        return '0:00'
    secs = int(td.total_seconds())
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'


def _visitor_row(s):
    now = timezone.now()
    end = s.end_time or s.last_seen or now
    return {
        'id': str(s.session_id),
        'who': (s.user.get_full_name() or s.user.username) if s.user_id else ('زائر عائد' if s.is_returning else 'زائر جديد'),
        'is_user': bool(s.user_id),
        'country': f"{s.country.flag_emoji or ''} {s.country.name}".strip() if s.country_id else '🌐 غير معروف',
        'device': DEVICE_LABELS.get(s.device_type, s.device_type or '—'),
        'browser': s.browser or '—',
        'source': SOURCE_LABELS.get(s.entry_source or '', 'غير محدد'),
        'landing': _path(s.landing_page) or '/',
        'exit': _path(s.exit_page or (s.landing_page if s.page_count <= 1 else '')) or '—',
        'pages': s.page_count,
        'duration': _fmt_duration(max(end - s.start_time, timedelta(0))),
        'entered': timezone.localtime(s.start_time).strftime('%Y/%m/%d %H:%M'),
        'left': timezone.localtime(s.end_time).strftime('%Y/%m/%d %H:%M') if s.end_time else '',
        'seen_ago': int((now - (s.last_seen or s.start_time)).total_seconds()),
    }
