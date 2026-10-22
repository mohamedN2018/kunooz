# analytics/views.py
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db.models import (
    Count, Sum, Avg, Min, Max, Q, F, 
    DurationField, ExpressionWrapper, 
    Case, When, FloatField, Value
)
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from .models import *
from django.utils import timezone
from django.contrib.auth.models import User
from core.models import *  # استبدل بما يتناسب مع مشروعك
from django.db.models.functions import (
    TruncDate, TruncHour, TruncDay, TruncWeek,
    TruncMonth, TruncYear, Concat, Extract
)
from datetime import datetime, timedelta, date
import json
import pytz
from collections import defaultdict

# ===== دوال مساعدة =====
def calculate_bounce_rate():
    """حساب معدل الارتداد"""
    total_sessions = VisitorSession.objects.count()
    bounce_sessions = VisitorSession.objects.filter(page_count=1).count()
    
    return (bounce_sessions / total_sessions * 100) if total_sessions > 0 else 0


def calculate_start_date(period):
    """حساب تاريخ البدء بناءً على الفترة"""
    today = timezone.now().date()
    
    if period == 'today':
        return today
    elif period == 'yesterday':
        return today - timedelta(days=1)
    elif period == '7d':
        return today - timedelta(days=7)
    elif period == '30d':
        return today - timedelta(days=30)
    elif period == '90d':
        return today - timedelta(days=90)
    elif period == '1y':
        return today - timedelta(days=365)
    else:
        return today - timedelta(days=30)

def get_monthly_analytics():
    monthly = (
        VisitorSession.objects
        .annotate(
            year=Extract('start_time', 'year'),
            month=Extract('start_time', 'month'),
            is_bounce=Case(
                When(page_count=1, then=1),
                default=0,
                output_field=FloatField()
            )
        )
        .values('year', 'month')
        .annotate(
            sessions=Count('id'),
            pageviews=Count('pageviews'),
            avg_duration=Avg('total_time_spent'),
            bounce_rate=Avg('is_bounce')  # ✅ هنا الصح
        )
        .order_by('-year', '-month')[:12]
    )

    return list(monthly)

def get_countries_data():
    """الحصول على بيانات الدول"""
    countries = Country.objects.annotate(
        total_visits=Count('visitorsession'),
        total_time=Sum('visitorsession__total_time_spent'),
        recent_visits=Count('visitorsession', filter=Q(
            visitorsession__start_time__gte=timezone.now() - timedelta(days=30)
        )),
    ).order_by('-total_visits')[:20]
    
    result = []
    total_all_visits = VisitorSession.objects.count() or 1
    
    for c in countries:
        result.append({
            'name': c.name,
            'flag': c.flag_emoji,
            'visits': c.total_visits,
            'recent_visits': c.recent_visits,
            'avg_time': str(c.avg_time_spent()),
            'percentage': (c.total_visits / total_all_visits * 100) if total_all_visits > 0 else 0,
        })
    
    return result


def get_time_analytics():
    """تحليل البيانات الزمنية"""
    # توزيع الزيارات على ساعات اليوم
    hourly = VisitorSession.objects.annotate(
        hour=Extract('start_time', 'hour')
    ).values('hour').annotate(
        count=Count('id'),
        avg_duration=Avg('total_time_spent')
    ).order_by('hour')
    
    # توزيع على أيام الأسبوع
    weekday = VisitorSession.objects.annotate(
        weekday=Extract('start_time', 'week_day')  # 1=Sunday, 7=Saturday
    ).values('weekday').annotate(
        count=Count('id')
    ).order_by('weekday')
    
    return {
        'hourly': list(hourly),
        'weekday': list(weekday),
    }


def get_top_pages():
    """أفضل الصفحات مشاهدة"""
    top_pages = PageView.objects.values('url', 'title').annotate(
        views=Count('id'),
        avg_time=Avg('time_spent'),
        bounce_rate=Avg(Case(
            When(is_bounce=True, then=1),
            default=0,
            output_field=FloatField()
        ))
    ).order_by('-views')[:10]
    
    return list(top_pages)


def get_recent_sessions():
    """أحدث الجلسات"""
    recent = VisitorSession.objects.select_related('country').order_by('-start_time')[:10]
    
    return [
        {
            'id': str(s.session_id),
            'start_time': s.start_time,
            'duration': str(s.duration),
            'pages': s.page_count,
            'country': s.country.name if s.country else 'غير معروف',
            'flag': s.country.flag_emoji if s.country else '🌐',
            'device': s.device_type,
            'is_active': s.is_active,
        }
        for s in recent
    ]


def calculate_country_trend(country_code, period):
    """حساب اتجاه الدولة (زيادة/نقصان)"""
    today = timezone.now().date()
    
    if period == '7d':
        current_start = today - timedelta(days=7)
        previous_start = current_start - timedelta(days=7)
    elif period == '30d':
        current_start = today - timedelta(days=30)
        previous_start = current_start - timedelta(days=30)
    else:
        return 0
    
    # الزيارات في الفترة الحالية
    current_visits = VisitorSession.objects.filter(
        country__code=country_code,
        start_time__gte=current_start
    ).count()
    
    # الزيارات في الفترة السابقة
    previous_visits = VisitorSession.objects.filter(
        country__code=country_code,
        start_time__gte=previous_start,
        start_time__lt=current_start
    ).count()
    
    if previous_visits > 0:
        return ((current_visits - previous_visits) / previous_visits * 100)
    elif current_visits > 0:
        return 100
    else:
        return 0


def get_country_coordinates(country_code, coord_type='lat'):
    """الحصول على إحداثيات الدولة"""
    coordinates = {
        'EG': {'lat': 26.8206, 'lng': 30.8025},  # مصر
        'SA': {'lat': 23.8859, 'lng': 45.0792},  # السعودية
        'AE': {'lat': 23.4241, 'lng': 53.8478},  # الإمارات
        'QA': {'lat': 25.3548, 'lng': 51.1839},  # قطر
        'KW': {'lat': 29.3117, 'lng': 47.4818},  # الكويت
        'US': {'lat': 37.0902, 'lng': -95.7129}, # الولايات المتحدة
        'GB': {'lat': 55.3781, 'lng': -3.4360},  # المملكة المتحدة
        'FR': {'lat': 46.2276, 'lng': 2.2137},   # فرنسا
        'DE': {'lat': 51.1657, 'lng': 10.4515},  # ألمانيا
        'TR': {'lat': 38.9637, 'lng': 35.2433},  # تركيا
        'IN': {'lat': 20.5937, 'lng': 78.9629},  # الهند
        'CN': {'lat': 35.8617, 'lng': 104.1954}, # الصين
        'RU': {'lat': 61.5240, 'lng': 105.3188}, # روسيا
        'BR': {'lat': -14.2350, 'lng': -51.9253},# البرازيل
    }
    
    country_coords = coordinates.get(country_code, {'lat': 0, 'lng': 0})
    return country_coords[coord_type]


def get_hourly_analytics(start_date):
    """تحليل بيانات الساعات"""
    hourly = VisitorSession.objects.filter(
        start_time__gte=start_date
    ).annotate(
        hour=Extract('start_time', 'hour')
    ).values('hour').annotate(
        sessions=Count('id'),
        pageviews=Count('pageviews'),
        avg_duration=Avg('total_time_spent')
    ).order_by('hour')
    
    # ملء الساعات الفارصة
    result = []
    for hour in range(24):
        data = next((h for h in hourly if h['hour'] == hour), {
            'hour': hour,
            'sessions': 0,
            'pageviews': 0,
            'avg_duration': timedelta(0),
        })
        
        result.append({
            'hour': hour,
            'hour_display': f'{hour:02d}:00',
            'sessions': data['sessions'],
            'pageviews': data['pageviews'],
            'avg_duration': str(data['avg_duration'] or timedelta(0)),
        })
    
    return result


def get_daily_analytics(start_date):
    """تحليل بيانات الأيام"""
    daily = VisitorSession.objects.filter(
        start_time__gte=start_date
    ).annotate(
        date=TruncDate('start_time')
    ).values('date').annotate(
        sessions=Count('id'),
        pageviews=Count('pageviews'),
        avg_duration=Avg('total_time_spent'),
        unique_visitors=Count('ip_address', distinct=True)
    ).order_by('date')
    
    return list(daily)


def get_weekday_analytics(start_date):
    """تحليل بيانات أيام الأسبوع"""
    weekdays_arabic = ['الأحد', 'الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت']
    
    weekday = VisitorSession.objects.filter(
        start_time__gte=start_date
    ).annotate(
        weekday=Extract('start_time', 'week_day') - 1  # تعديل ليتوافق مع Python (0=Sunday)
    ).values('weekday').annotate(
        sessions=Count('id'),
        pageviews=Count('pageviews'),
        avg_duration=Avg('total_time_spent')
    ).order_by('weekday')
    
    result = []
    for day in range(7):
        data = next((w for w in weekday if w['weekday'] == day), {
            'weekday': day,
            'sessions': 0,
            'pageviews': 0,
            'avg_duration': timedelta(0),
        })
        
        result.append({
            'day': day,
            'day_name': weekdays_arabic[day],
            'sessions': data['sessions'],
            'pageviews': data['pageviews'],
            'avg_duration': str(data['avg_duration'] or timedelta(0)),
        })
    
    return result


def calculate_peak_time(data, group_by):
    """حساب وقت الذروة"""
    if not data:
        return None
    
    if group_by == 'hour':
        peak = max(data, key=lambda x: x['sessions'])
        return {
            'time': f'{peak["hour"]:02d}:00',
            'sessions': peak['sessions'],
        }
    elif group_by == 'weekday':
        peak = max(data, key=lambda x: x['sessions'])
        return {
            'day': peak['day_name'],
            'sessions': peak['sessions'],
        }
    else:
        peak = max(data, key=lambda x: x['sessions'])
        return {
            'date': peak['date'].strftime('%Y-%m-%d'),
            'sessions': peak['sessions'],
        }


def calculate_avg_duration(start_date):
    """حساب متوسط مدة الجلسة"""
    avg = VisitorSession.objects.filter(
        start_time__gte=start_date
    ).aggregate(
        avg=Avg('total_time_spent')
    )['avg']
    
    return avg or timedelta(0)


def get_realtime_visitors():
    """الحصول على الزوار المتصلين حالياً"""
    # الزوار النشطين خلال آخر 5 دقائق
    active_threshold = timezone.now() - timedelta(minutes=5)
    
    realtime_visitors = RealTimeVisitor.objects.filter(
        last_activity__gte=active_threshold
    ).select_related('session', 'session__country')
    
    visitors_data = []
    
    for rv in realtime_visitors:
        time_on_page = rv.time_on_page.total_seconds()
        session = rv.session
        
        visitors_data.append({
            'session_id': str(session.session_id),
            'current_page': rv.current_page,
            'time_on_page': time_on_page,
            'country': session.country.name if session.country else 'غير معروف',
            'flag': session.country.flag_emoji if session.country else '🌐',
            'city': session.city,
            'device': session.device_type,
            'browser': session.browser,
            'is_new': (timezone.now() - session.start_time).seconds < 60,  # أقل من دقيقة
            'last_activity': rv.last_activity,
        })
    
    return visitors_data


def calculate_geographic_data():
    """حساب البيانات الجغرافية"""
    countries = Country.objects.annotate(
        visits_count=Count('visitorsession')
    ).order_by('-visits_count')[:10]
    
    total_visits = sum(c.visits_count for c in countries)
    
    geographic_data = {
        'countries': [
            {
                'name': c.name,
                'code': c.code,
                'flag': c.flag_emoji,
                'visits': c.visits_count,
                'percentage': (c.visits_count / total_visits * 100) if total_visits > 0 else 0,
                'avg_time': str(c.avg_time_spent()),
            }
            for c in countries
        ],
        'total_countries': countries.count(),
        'total_visits': total_visits,
        'top_country': {
            'name': countries[0].name if countries else 'لا توجد بيانات',
            'visits': countries[0].visits_count if countries else 0,
        }
    }
    
    return geographic_data



# ===== قالب عام للصفحات الفرعية =====
# هذه الصفحات لم يكن لها قوالب (كانت تُرجع خطأ 500)؛ نعرض بياناتها الحقيقية في قالب جدولي موحد.
def render_report(request, template_name, title, context, tables):
    """tables: قائمة (عنوان, صفوف dict, أعمدة [(key, label)])"""
    context = dict(context)
    context['report_title'] = title
    context['report_tables'] = [
        {
            'title': t_title,
            'columns': [label for _, label in cols],
            'rows': [[row.get(key, '') if isinstance(row, dict) else getattr(row, key, '') for key, _ in cols] for row in rows],
        }
        for t_title, rows, cols in tables
    ]
    return render(request, [template_name, 'analytics/report.html'], context)

# ===== Views الرئيسية =====
@staff_member_required
def advanced_analytics_dashboard(request):
    """اللوحة الرئيسية: حركة الزوار (دخول/خروج/متصلون الآن) لنطاق زمني قابل للاختيار."""
    from . import reports as traffic
    return render(request, 'analytics/traffic_dashboard.html', traffic.traffic_report(request.GET.get('range', '7d')))


@staff_member_required
def legacy_analytics_dashboard(request):
    """اللوحة القديمة (خرائط وتقارير) — متاحة على /analytics/dashboard/advanced/"""
    # حساب الإحصائيات الأساسية
    today = timezone.now().date()
    yesterday = today - timedelta(days=1)
    
    # إحصائيات إجمالية
    total_sessions = VisitorSession.objects.count()
    active_sessions = VisitorSession.objects.filter(is_active=True).count()
    total_pageviews = PageView.objects.count()
    today_pageviews = PageView.objects.filter(timestamp__date=today).count()
    
    # حساب متوسط مدة الجلسة
    avg_duration_agg = VisitorSession.objects.aggregate(
        avg=Avg('total_time_spent')
    )
    avg_session_duration = avg_duration_agg['avg'] or timedelta(0)
    
    # حساب معدل الارتداد
    bounce_rate = calculate_bounce_rate()
    
    stats = {
        'total_sessions': total_sessions,
        'active_sessions': active_sessions,
        'total_pageviews': total_pageviews,
        'today_pageviews': today_pageviews,
        'avg_session_duration': avg_session_duration,
        'bounce_rate': bounce_rate,
    }
    
    # بيانات الرسم البياني للشهر
    monthly_data = get_monthly_analytics()
    
    # بيانات الدول
    countries_data = get_countries_data()
    
    # بيانات الوقت
    time_analytics = get_time_analytics()
    
    # أفضل الصفحات
    top_pages = get_top_pages()
    
    # أحدث الجلسات
    recent_sessions = get_recent_sessions()
    
    # الزوار المتصلين حالياً
    realtime_visitors = get_realtime_visitors()
    
    # البيانات الجغرافية
    geographic_data = calculate_geographic_data()
    
    # بيانات الإحصائيات حسب الوقت
    hourly_data = get_hourly_analytics(timezone.now().date() - timedelta(days=7))
    
    # أوقات الذروة
    peak_time_data = calculate_peak_time(hourly_data, 'hour')
    
    context = {
        'stats': stats,
        'monthly_data': monthly_data,
        'countries_data': countries_data,
        'time_analytics': time_analytics,
        'top_pages': top_pages,
        'recent_sessions': recent_sessions,
        'realtime_visitors': realtime_visitors,
        'geographic_data': geographic_data,
        'hourly_data': hourly_data,
        'peak_time': peak_time_data,
        'today': today,
        'yesterday': yesterday,
        'current_time': timezone.now(),
    }
    
    return render(request, 'analytics/advanced_dashboard.html', context)


@staff_member_required
def simple_analytics_dashboard(request):
    """لوحة تحليلات مبسطة"""
    today = timezone.now().date()
    
    # الإحصائيات الأساسية
    stats = {
        'total_visitors': VisitorSession.objects.count(),
        'today_visitors': VisitorSession.objects.filter(start_time__date=today).count(),
        'total_pageviews': PageView.objects.count(),
        'today_pageviews': PageView.objects.filter(timestamp__date=today).count(),
        'avg_session_time': VisitorSession.objects.aggregate(
            avg=Avg('total_time_spent')
        )['avg'] or timedelta(0),
        'bounce_rate': calculate_bounce_rate(),
    }
    
    # أفضل 5 دول
    top_countries = Country.objects.annotate(
        visits_count=Count('visitorsession')
    ).order_by('-visits_count')[:5]

    # أفضل 5 صفحات
    top_pages = PageView.objects.values('title', 'url').annotate(
        views=Count('id')
    ).order_by('-views')[:5]
    
    # توزيع الأجهزة
    devices = VisitorSession.objects.values('device_type').annotate(
        count=Count('id')
    ).order_by('-count')
    
    context = {
        'stats': stats,
        'top_countries': top_countries,
        'top_pages': top_pages,
        'devices': devices,
        'today': today,
    }
    
    return render_report(request, 'analytics/simple_dashboard.html', 'لوحة تحليلات مبسطة', context, [
        ('الإحصائيات', [{'k': 'إجمالي الزوار', 'v': stats['total_visitors']}, {'k': 'زوار اليوم', 'v': stats['today_visitors']},
                        {'k': 'إجمالي المشاهدات', 'v': stats['total_pageviews']}, {'k': 'مشاهدات اليوم', 'v': stats['today_pageviews']},
                        {'k': 'معدل الارتداد %', 'v': round(stats['bounce_rate'], 1)}], [('k', 'المؤشر'), ('v', 'القيمة')]),
        ('أفضل الدول', top_countries, [('name', 'الدولة'), ('visits_count', 'الزيارات')]),
        ('أفضل الصفحات', top_pages, [('url', 'الرابط'), ('views', 'المشاهدات')]),
        ('الأجهزة', devices, [('device_type', 'الجهاز'), ('count', 'العدد')]),
    ])


@staff_member_required
def country_analytics(request, country_code=None):
    """تحليلات مفصلة لدولة معينة"""
    if country_code:
        country = get_object_or_404(Country, code=country_code)
        
        # إحصائيات الدولة
        country_stats = {
            'total_visits': VisitorSession.objects.filter(country=country).count(),
            'avg_session_time': VisitorSession.objects.filter(country=country).aggregate(
                avg=Avg('total_time_spent')
            )['avg'] or timedelta(0),
            'popular_pages': PageView.objects.filter(session__country=country).values(
                'title', 'url'
            ).annotate(
                views=Count('id')
            ).order_by('-views')[:10],
            'device_distribution': VisitorSession.objects.filter(country=country).values(
                'device_type'
            ).annotate(
                count=Count('id')
            ).order_by('-count'),
            'time_distribution': VisitorSession.objects.filter(country=country).annotate(
                hour=Extract('start_time', 'hour')
            ).values('hour').annotate(
                count=Count('id')
            ).order_by('hour'),
        }
        
        context = {
            'country': country,
            'stats': country_stats,
        }
        
        return render_report(request, 'analytics/country_detail.html', f'تحليلات {country.name}', context, [
            ('أشهر الصفحات', country_stats['popular_pages'], [('url', 'الرابط'), ('views', 'المشاهدات')]),
            ('الأجهزة', country_stats['device_distribution'], [('device_type', 'الجهاز'), ('count', 'العدد')]),
        ])
    
    else:
        # قائمة جميع الدول
        countries = Country.objects.annotate(
            total_visits=Count('visitorsession'),
            avg_time=Avg('visitorsession__total_time_spent'),
            latest_visit=Max('visitorsession__start_time'),
        ).order_by('-total_visits')
        
        context = {
            'countries': countries,
        }
        
        return render_report(request, 'analytics/countries_list.html', 'الدول', context, [
            ('الدول حسب الزيارات', countries, [('name', 'الدولة'), ('code', 'الكود'), ('total_visits', 'الزيارات'), ('latest_visit', 'آخر زيارة')]),
        ])


@staff_member_required
def time_analytics(request):
    """تحليلات الوقت"""
    # توزيع الساعات
    hourly_data = get_hourly_analytics(timezone.now().date() - timedelta(days=30))
    
    # توزيع الأيام
    daily_data = get_daily_analytics(timezone.now().date() - timedelta(days=30))
    
    # توزيع أيام الأسبوع
    weekday_data = get_weekday_analytics(timezone.now().date() - timedelta(days=90))
    
    # وقت الذروة
    peak_hourly = calculate_peak_time(hourly_data, 'hour')
    peak_weekday = calculate_peak_time(weekday_data, 'weekday')
    
    context = {
        'hourly_data': hourly_data,
        'daily_data': daily_data,
        'weekday_data': weekday_data,
        'peak_hourly': peak_hourly,
        'peak_weekday': peak_weekday,
    }
    
    return render_report(request, 'analytics/time_analytics.html', 'تحليلات الوقت', context, [
        ('حسب الساعة (آخر 30 يوم)', hourly_data, [('hour_display', 'الساعة'), ('sessions', 'الجلسات'), ('pageviews', 'المشاهدات')]),
        ('حسب اليوم', daily_data, [('date', 'التاريخ'), ('sessions', 'الجلسات'), ('pageviews', 'المشاهدات'), ('unique_visitors', 'زوار فريدون')]),
        ('حسب أيام الأسبوع (آخر 90 يوم)', weekday_data, [('day_name', 'اليوم'), ('sessions', 'الجلسات'), ('pageviews', 'المشاهدات')]),
    ])


@staff_member_required
def page_analytics(request):
    """تحليلات الصفحات"""
    # أفضل الصفحات
    top_pages = PageView.objects.values('title', 'url').annotate(
        views=Count('id'),
        avg_time=Avg('time_spent'),
        bounce_rate=Avg(Case(
            When(is_bounce=True, then=1),
            default=0,
            output_field=FloatField()
        ))
    ).order_by('-views')[:20]
    
    # صفحات الهبوط الأكثر شيوعاً
    landing_pages = VisitorSession.objects.values('landing_page').annotate(
        count=Count('id'),
        avg_time=Avg('total_time_spent')
    ).order_by('-count')[:10]
    
    context = {
        'top_pages': top_pages,
        'landing_pages': landing_pages,
    }
    
    return render_report(request, 'analytics/page_analytics.html', 'تحليلات الصفحات', context, [
        ('أكثر الصفحات مشاهدة', top_pages, [('url', 'الرابط'), ('views', 'المشاهدات'), ('avg_time', 'متوسط الوقت')]),
        ('صفحات الهبوط', landing_pages, [('landing_page', 'الصفحة'), ('count', 'الجلسات')]),
    ])


@staff_member_required
def device_analytics(request):
    """تحليلات الأجهزة"""
    # توزيع الأجهزة
    devices = VisitorSession.objects.values('device_type').annotate(
        count=Count('id'),
        avg_time=Avg('total_time_spent'),
        bounce_rate=Avg(Case(
            When(page_count=1, then=1),
            default=0,
            output_field=FloatField()
        ))
    ).order_by('-count')
    
    # توزيع المتصفحات
    browsers = VisitorSession.objects.values('browser').annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    
    # توزيع أنظمة التشغيل
    operating_systems = VisitorSession.objects.values('os').annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    
    context = {
        'devices': devices,
        'browsers': browsers,
        'operating_systems': operating_systems,
    }
    
    return render_report(request, 'analytics/device_analytics.html', 'تحليلات الأجهزة', context, [
        ('الأجهزة', devices, [('device_type', 'الجهاز'), ('count', 'الجلسات')]),
        ('المتصفحات', browsers, [('browser', 'المتصفح'), ('count', 'الجلسات')]),
        ('أنظمة التشغيل', operating_systems, [('os', 'النظام'), ('count', 'الجلسات')]),
    ])


@staff_member_required
def session_details(request, session_id):
    """تفاصيل جلسة محددة"""
    session = get_object_or_404(VisitorSession, session_id=session_id)
    
    # مشاهدات الصفحات للجلسة
    pageviews = PageView.objects.filter(session=session).order_by('timestamp')
    
    # إحصائيات الجلسة
    session_stats = {
        'duration': str(session.duration),
        'page_count': session.page_count,
        'avg_time_per_page': str(session.duration / session.page_count) if session.page_count > 0 else '0',
        'is_bounce': session.page_count == 1,
    }
    
    context = {
        'session': session,
        'pageviews': pageviews,
        'session_stats': session_stats,
    }
    
    return render_report(request, 'analytics/session_detail.html', 'تفاصيل الجلسة', context, [
        ('الصفحات', pageviews, [('url', 'الرابط'), ('timestamp', 'الوقت'), ('time_spent', 'المدة')]),
    ])


@staff_member_required
def export_analytics(request, format='csv'):
    """تصدير بيانات التحليلات"""
    from django.http import HttpResponse
    import csv
    
    if format == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="analytics_{timezone.now().date()}.csv"'
        response.write('﻿')
        
        writer = csv.writer(response)
        
        # كتابة عنوان الملف
        writer.writerow(['إحصائيات الموقع', f'التاريخ: {timezone.now().date()}'])
        writer.writerow([])
        
        # إحصائيات عامة
        writer.writerow(['الإحصائيات العامة'])
        writer.writerow(['إجمالي الجلسات', VisitorSession.objects.count()])
        writer.writerow(['إجمالي مشاهدات الصفحات', PageView.objects.count()])
        writer.writerow(['معدل الارتداد', f'{calculate_bounce_rate():.2f}%'])
        writer.writerow([])
        
        # الدول
        writer.writerow(['الدول حسب عدد الزيارات'])
        writer.writerow(['الدولة', 'عدد الزيارات', 'متوسط الوقت'])
        
        countries = Country.objects.annotate(
            visits_count=Count('visitorsession')
        ).order_by('-visits_count')[:20]
        
        for country in countries:
            writer.writerow([
                country.name,
                country.visits_count,
                str(country.avg_time_spent())
            ])
        
        return response
    
    elif format == 'pdf':
        # يمكنك إضافة مكتبة مثل reportlab لإنشاء PDF
        return HttpResponse('تصدير PDF قيد التطوير')
    
    else:
        return HttpResponse('صيغة غير مدعومة')


@staff_member_required
def realtime_analytics(request):
    """الزوار المتصلين حالياً"""
    realtime_visitors = get_realtime_visitors()
    
    # تجميع حسب الدولة
    countries_count = {}
    devices_count = {}
    
    for visitor in realtime_visitors:
        country = visitor['country']
        device = visitor['device']
        
        countries_count[country] = countries_count.get(country, 0) + 1
        devices_count[device] = devices_count.get(device, 0) + 1
    
    context = {
        'realtime_visitors': realtime_visitors,
        'total_online': len(realtime_visitors),
        'countries_count': countries_count,
        'devices_count': devices_count,
        'last_update': timezone.now(),
    }
    
    return render_report(request, 'analytics/realtime_analytics.html', f'المتصلون الآن ({len(realtime_visitors)})', context, [
        ('الزوار النشطون (آخر 5 دقائق)', realtime_visitors, [('current_page', 'الصفحة'), ('country', 'الدولة'), ('device', 'الجهاز'), ('browser', 'المتصفح')]),
    ])


@staff_member_required
def analytics_settings(request):
    """إعدادات لوحة التحليلات"""
    # النموذج السابق لم يكن يحفظ أي شيء؛ إعدادات التتبع الفعلية في متغيرات البيئة (ANALYTICS_ENABLED)
    messages.info(request, 'إعدادات التتبع تُدار من متغير البيئة ANALYTICS_ENABLED في الخادم.')
    return redirect('analytics_dashboard')

# ===== حركة الزوار: الدخول والخروج والمتصلون الآن =====
from django.core.paginator import Paginator
from . import reports as traffic


@staff_member_required
def visitors_log(request):
    """سجل كل زيارة: من دخل ومتى، من أين، ماذا تصفح، ومتى خرج."""
    traffic.close_stale_sessions()
    key, start, end = traffic.resolve_range(request.GET.get('range', '7d'))
    qs = VisitorSession.objects.filter(start_time__gte=start, start_time__lt=end).select_related('country', 'user')
    status = request.GET.get('status', '')
    if status == 'online':
        qs = qs.filter(pk__in=traffic.online_now().values('pk'))
    elif status == 'left':
        qs = qs.filter(is_active=False)
    if request.GET.get('who') == 'users':
        qs = qs.exclude(user=None)
    elif request.GET.get('who') == 'returning':
        qs = qs.filter(is_returning=True)
    page = Paginator(qs.order_by('-start_time'), 50).get_page(request.GET.get('page'))
    return render(request, 'analytics/visitors_log.html', {
        'rows': [traffic._visitor_row(s) for s in page],
        'page_obj': page,
        'range_key': key,
        'ranges': traffic.RANGES,
        'status': status,
        'who': request.GET.get('who', ''),
        'total': page.paginator.count,
    })


@staff_member_required
def live_json(request):
    """للتحديث التلقائي في اللوحة كل 15 ثانية."""
    traffic.close_stale_sessions()
    online = [traffic._visitor_row(s) for s in traffic.online_now()[:50]]
    today = traffic.traffic_report('today')['kpis']
    return JsonResponse({'online': online, 'online_count': len(online), 'today': today,
                         'updated': timezone.localtime().strftime('%H:%M:%S')})
