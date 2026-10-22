from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.http import JsonResponse, HttpResponse
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.core.cache import cache
from datetime import datetime, timedelta
import json
import csv
import re
from django.views.decorators.csrf import csrf_exempt
from django.contrib.admin.views.decorators import staff_member_required
from django.urls import reverse
from django.views.decorators.http import require_POST
from .models import Advertisement, AdPlacement
from .forms import AdvertisementForm, AdPlacementForm
from .utils import get_ad_analytics, clear_ad_cache, validate_ad_image, generate_ad_code
import logging

logger = logging.getLogger(__name__)


def is_ads_admin(user):
    """كان الكود يعتمد على user.user_type غير الموجود في نموذج User فلا أحد يملك الصلاحية."""
    return user.is_active and user.is_staff


def admin_redirect(model, action='changelist'):
    """يحوّل صفحات الإدارة القديمة (قوالبها غير موجودة) إلى لوحة Django للإعلانات."""
    @staff_member_required
    def view(request, pk=None):
        if action == 'change' and pk is not None:
            return redirect(reverse(f'admin:advertisements_{model}_change', args=[pk]))
        return redirect(reverse(f'admin:advertisements_{model}_{action}'))
    return view

# ==============================================
# وظائف تتبع الإعلانات (غير محمية بالصلاحيات)
# ==============================================


def render_ad_placement(request, code):
    """واجهة iframe القديمة (/ads/render/<code>/) — تستخدم نفس العرض الجديد."""
    from core.models import SiteSettings
    from .rendering import render_slot
    html = render_slot({'request': request, 'url_media': SiteSettings.objects.first()}, code)
    return HttpResponse(html or '<!-- no ads -->')


BOT_RE = re.compile(r'bot|crawl|spider|slurp|preview|facebookexternalhit|headless', re.I)


def _is_bot(request):
    return bool(BOT_RE.search(request.META.get('HTTP_USER_AGENT', '')))


@csrf_exempt  # sendBeacon من kz-ads.js لا يرسل CSRF؛ لا يغيّر إلا عدّاداً
def record_impression(request, ad_id):
    """تسجيل ظهور الإعلان (يُستدعى عند رؤية الإعلان فعلاً في الشاشة)"""
    if _is_bot(request) or request.user.is_staff:
        return HttpResponse(status=204)
    try:
        ad = get_object_or_404(Advertisement, id=ad_id)
        
        # التحقق من أن الإعلان نشط وفعال
        if ad.is_active():
            ad.record_impression()
            
            # إرجاع صورة 1x1 شفافة لتعقب الظهور
            response = HttpResponse(
                b'R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7',
                content_type='image/gif'
            )
            response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
            return response
        
        return HttpResponse(status=404)
    except Exception as e:
        # تسجيل الخطأ وإرجاع استجابة فارغة
        logger.exception("Error recording impression %s", ad_id)
        return HttpResponse(status=500)

def record_click(request, ad_id):
    """تسجيل نقرة على الإعلان"""
    try:
        ad = get_object_or_404(Advertisement, id=ad_id)
        
        # التحقق من أن الإعلان نشط وفعال
        if ad.is_active():
            if not (_is_bot(request) or request.user.is_staff):
                ad.record_click()
            
            # إعادة توجيه إلى رابط الإعلان مع إضافة معلمات التتبع
            redirect_url = ad.link
            if '?' in redirect_url:
                redirect_url += f'&utm_source=ads&utm_medium=banner&utm_campaign={ad.id}'
            else:
                redirect_url += f'?utm_source=ads&utm_medium=banner&utm_campaign={ad.id}'
            
            return redirect(redirect_url)
        
        # إذا كان الإعلان غير نشط، إعادة توجيه إلى الصفحة الرئيسية
        messages.warning(request, _('هذا الإعلان لم يعد متاحاً'))
        return redirect('/')
    except Exception as e:
        # تسجيل الخطأ وإعادة التوجيه إلى الصفحة الرئيسية
        logger.exception("Error recording ad click %s", ad_id)
        messages.error(request, _('حدث خطأ أثناء معالجة طلبك'))
        return redirect('/')

# ==============================================
# وظائف لوحة التحكم والإدارة
# ==============================================

@login_required
@user_passes_test(is_ads_admin)
def ad_dashboard(request):
    """لوحة تحكم الإعلانات"""
    # الحصول على معاملات البحث والتصفية
    search_query = request.GET.get('q', '')
    placement_filter = request.GET.get('placement', '')
    status_filter = request.GET.get('status', '')
    ad_type_filter = request.GET.get('type', '')
    
    # بناء الاستعلام
    ads = Advertisement.objects.all().select_related('placement')
    
    if search_query:
        ads = ads.filter(
            Q(title__icontains=search_query) |
            Q(text_content__icontains=search_query) |
            Q(advertiser_name__icontains=search_query)
        )
    
    if placement_filter:
        ads = ads.filter(placement__code=placement_filter)
    
    if status_filter == 'active':
        ads = ads.filter(active=True)
    elif status_filter == 'inactive':
        ads = ads.filter(active=False)
    elif status_filter == 'expired':
        ads = ads.filter(end_date__lt=timezone.now())
    elif status_filter == 'upcoming':
        ads = ads.filter(start_date__gt=timezone.now())
    
    if ad_type_filter:
        ads = ads.filter(ad_type=ad_type_filter)
    
    # الترتيب
    sort_by = request.GET.get('sort', '-created_at')
    if sort_by in ['title', 'start_date', 'end_date', 'impressions', 'clicks', 'priority']:
        ads = ads.order_by(sort_by)
    elif sort_by == '-title':
        ads = ads.order_by('-title')
    else:
        ads = ads.order_by('-created_at')
    
    # الإحصائيات
    total_ads = Advertisement.objects.count()
    active_ads = sum(1 for ad in Advertisement.objects.all() if ad.is_active())
    
    # إحصائيات من الكاش لتحسين الأداء
    stats_cache_key = f'ad_stats_{request.user.id}'
    stats = cache.get(stats_cache_key)
    
    if not stats:
        total_impressions = Advertisement.objects.aggregate(Sum('impressions'))['impressions__sum'] or 0
        total_clicks = Advertisement.objects.aggregate(Sum('clicks'))['clicks__sum'] or 0
        
        # نسبة النقر
        ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
        
        # الإعلانات المنتهية قريبًا (خلال 7 أيام)
        warning_date = timezone.now() + timedelta(days=7)
        expiring_ads = Advertisement.objects.filter(
            end_date__lte=warning_date,
            end_date__gte=timezone.now(),
            active=True
        ).count()
        
        stats = {
            'total_impressions': total_impressions,
            'total_clicks': total_clicks,
            'ctr': round(ctr, 2),
            'expiring_ads': expiring_ads,
        }
        cache.set(stats_cache_key, stats, 300)  # 5 دقائق
    
    # الحصول على قائمة الأماكن للفلتر
    placements = AdPlacement.objects.filter(active=True)
    
    # التقسيم للصفحات (Pagination)
    page = request.GET.get('page', 1)
    try:
        page = int(page)
    except ValueError:
        page = 1
    
    items_per_page = 20
    total_items = ads.count()
    total_pages = (total_items + items_per_page - 1) // items_per_page
    start_idx = (page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    
    ads_paginated = ads[start_idx:end_idx]
    
    context = {
        'ads': ads_paginated,
        'total_ads': total_ads,
        'active_ads': active_ads,
        'total_impressions': stats['total_impressions'],
        'total_clicks': stats['total_clicks'],
        'ctr': stats['ctr'],
        'expiring_ads_count': stats['expiring_ads'],
        'placements': placements,
        'search_query': search_query,
        'placement_filter': placement_filter,
        'status_filter': status_filter,
        'ad_type_filter': ad_type_filter,
        'sort_by': sort_by,
        'current_page': page,
        'total_pages': total_pages,
        'has_previous': page > 1,
        'has_next': page < total_pages,
        'AD_TYPE_CHOICES': Advertisement.AD_TYPE_CHOICES,
        'user_can_delete': request.user.is_superuser,
    }
    
    return render(request, 'advertisements/dashboard.html', context)

@login_required
@user_passes_test(is_ads_admin)
def analytics_dashboard(request):
    """لوحة تحليل متقدمة للإعلانات"""
    
    # الحصول على معاملات الفترة من الرابط
    period = request.GET.get('period', '30days')
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    
    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            custom_range = True
        except ValueError:
            custom_range = False
            start_date = timezone.now() - timedelta(days=30)
            end_date = timezone.now()
    else:
        custom_range = False
        if period == 'today':
            start_date = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = timezone.now()
        elif period == 'yesterday':
            start_date = timezone.now() - timedelta(days=1)
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=1)
        elif period == '7days':
            start_date = timezone.now() - timedelta(days=7)
            end_date = timezone.now()
        elif period == '90days':
            start_date = timezone.now() - timedelta(days=90)
            end_date = timezone.now()
        else:  # 30days افتراضي
            start_date = timezone.now() - timedelta(days=30)
            end_date = timezone.now()
    
    # الحصول على التحليلات
    analytics = get_ad_analytics(start_date, end_date)
    
    # الإعلانات الأفضل أداءً (أعلى CTR)
    top_ads = Advertisement.objects.filter(
        start_date__gte=start_date,
        end_date__lte=end_date,
        impressions__gt=0
    ).annotate(
        ctr_calc=Sum('clicks') * 100.0 / Sum('impressions')
    ).order_by('-ctr_calc')[:10]
    
    # الإعلانات الأسوأ أداءً
    worst_ads = Advertisement.objects.filter(
        start_date__gte=start_date,
        end_date__lte=end_date,
        impressions__gt=100  # على الأقل 100 ظهور لتكون ذات دلالة
    ).annotate(
        ctr_calc=Sum('clicks') * 100.0 / Sum('impressions')
    ).order_by('ctr_calc')[:10]
    
    # إحصائيات حسب المكان
    placement_stats = []
    for placement in AdPlacement.objects.filter(active=True):
        placement_ads = Advertisement.objects.filter(
            placement=placement,
            start_date__gte=start_date,
            end_date__lte=end_date
        )
        if placement_ads.exists():
            total_impressions = placement_ads.aggregate(Sum('impressions'))['impressions__sum'] or 0
            total_clicks = placement_ads.aggregate(Sum('clicks'))['clicks__sum'] or 0
            ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
            
            placement_stats.append({
                'placement': placement,
                'ads_count': placement_ads.count(),
                'impressions': total_impressions,
                'clicks': total_clicks,
                'ctr': round(ctr, 2)
            })
    
    # تحليل الأداء اليومي (آخر 30 يوم)
    daily_data = []
    for i in range(30):
        date = timezone.now() - timedelta(days=i)
        day_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = date.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        day_ads = Advertisement.objects.filter(
            start_date__lte=day_end,
            end_date__gte=day_start,
            active=True
        )
        
        day_impressions = day_ads.aggregate(Sum('impressions'))['impressions__sum'] or 0
        day_clicks = day_ads.aggregate(Sum('clicks'))['clicks__sum'] or 0
        day_ctr = (day_clicks / day_impressions * 100) if day_impressions > 0 else 0
        
        daily_data.append({
            'date': day_start.strftime('%Y-%m-%d'),
            'impressions': day_impressions,
            'clicks': day_clicks,
            'ctr': round(day_ctr, 2)
        })
    
    daily_data.reverse()  # ترتيب من الأقدم إلى الأحدث
    
    context = {
        'analytics': analytics,
        'top_ads': top_ads,
        'worst_ads': worst_ads,
        'placement_stats': sorted(placement_stats, key=lambda x: x['ctr'], reverse=True),
        'daily_data': daily_data,
        'period': period,
        'start_date': start_date.strftime('%Y-%m-%d') if not custom_range else start_date_str,
        'end_date': end_date.strftime('%Y-%m-%d') if not custom_range else end_date_str,
        'custom_range': custom_range,
        'today': timezone.now().strftime('%Y-%m-%d'),
        'thirty_days_ago': (timezone.now() - timedelta(days=30)).strftime('%Y-%m-%d'),
        'seven_days_ago': (timezone.now() - timedelta(days=7)).strftime('%Y-%m-%d'),
    }
    
    return render(request, 'advertisements/analytics.html', context)

@login_required
@user_passes_test(is_ads_admin)
def create_ad(request):
    """إنشاء إعلان جديد"""
    if request.method == 'POST':
        form = AdvertisementForm(request.POST, request.FILES)
        
        if form.is_valid():
            ad = form.save(commit=False)
            
            # إذا كان المستخدم ليس أدمن، نجعل الإعلان غير نشط بانتظار المراجعة
            if not request.user.is_superuser:
                ad.active = False
                ad.notes = f"Pending review by admin. Created by {request.user.username}"
                messages.info(request, _('Your ad has been submitted for review. It will be activated after approval.'))
            
            # التحقق من صحة الصورة إذا كانت من نوع بانر
            if ad.ad_type == 'banner' and 'image' in request.FILES:
                is_valid, error_msg = validate_ad_image(request.FILES['image'])
                if not is_valid:
                    messages.error(request, error_msg)
                    context = {
                        'form': form,
                        'title': _('Create New Advertisement'),
                    }
                    return render(request, 'advertisements/form.html', context)
            
            ad.save()
            form.save_m2m()
            
            # مسح الكاش
            clear_ad_cache(ad.placement.code)
            
            messages.success(request, _('Advertisement created successfully'))
            
            if request.user.is_superuser:
                return redirect('advertisements:dashboard')
            else:
                return redirect('advertisements:preview', pk=ad.pk)
        else:
            messages.error(request, _('Please correct the errors below.'))
    else:
        form = AdvertisementForm()
    
    context = {
        'form': form,
        'title': _('Create New Advertisement'),
        'action_url': 'advertisements:create',
        'submit_text': _('Create Advertisement'),
    }
    
    return render(request, 'advertisements/form.html', context)

@login_required
@user_passes_test(is_ads_admin)
def edit_ad(request, pk):
    """تعديل الإعلان"""
    ad = get_object_or_404(Advertisement, pk=pk)
    
    
    if request.method == 'POST':
        form = AdvertisementForm(request.POST, request.FILES, instance=ad)
        
        if form.is_valid():
            # التحقق من صحة الصورة إذا كانت من نوع بانر
            if ad.ad_type == 'banner' and 'image' in request.FILES:
                is_valid, error_msg = validate_ad_image(request.FILES['image'])
                if not is_valid:
                    messages.error(request, error_msg)
                    context = {
                        'form': form,
                        'title': _('Edit Advertisement'),
                        'ad': ad,
                        'action_url': 'advertisements:edit',
                        'pk': pk,
                        'submit_text': _('Update Advertisement'),
                    }
                    return render(request, 'advertisements/form.html', context)
            
            form.save()
            
            # مسح الكاش
            clear_ad_cache(ad.placement.code)
            
            messages.success(request, _('Advertisement updated successfully'))
            return redirect('advertisements:dashboard')
        else:
            messages.error(request, _('Please correct the errors below.'))
    else:
        form = AdvertisementForm(instance=ad)
    
    context = {
        'form': form,
        'title': _('Edit Advertisement'),
        'ad': ad,
        'action_url': 'advertisements:edit',
        'pk': pk,
        'submit_text': _('Update Advertisement'),
    }
    
    return render(request, 'advertisements/form.html', context)

@login_required
@user_passes_test(is_ads_admin)
def preview_ad(request, pk):
    """معاينة الإعلان"""
    ad = get_object_or_404(Advertisement, pk=pk)
    
    
    # توليد كود HTML للإعلان
    ad_html = generate_ad_code(ad.ad_type, ad.get_content_for_api(), ad.link, ad.id)
    
    context = {
        'ad': ad,
        'ad_html': ad_html,
        'preview': True,
        'can_edit': True,  # الوصول للـ staff فقط
    }
    
    return render(request, 'advertisements/preview.html', context)

@login_required
@user_passes_test(is_ads_admin)
def manage_placements(request):
    """إدارة أماكن الإعلانات"""
    placements = AdPlacement.objects.all().order_by('priority', 'name')
    
    if request.method == 'POST':
        form = AdPlacementForm(request.POST)
        if form.is_valid():
            placement = form.save()
            
            # مسح الكاش
            clear_ad_cache(placement.code)
            
            messages.success(request, _('Ad placement created successfully'))
            return redirect('advertisements:placements')
        else:
            messages.error(request, _('Please correct the errors below.'))
    else:
        form = AdPlacementForm()
    
    # إحصائيات الأماكن
    placements_with_stats = []
    for placement in placements:
        active_ads = Advertisement.objects.filter(
            placement=placement,
            active=True,
            start_date__lte=timezone.now(),
            end_date__gte=timezone.now()
        ).count()
        
        total_ads = Advertisement.objects.filter(placement=placement).count()
        
        placements_with_stats.append({
            'placement': placement,
            'active_ads': active_ads,
            'total_ads': total_ads,
            'fill_rate': (active_ads / placement.max_ads * 100) if placement.max_ads > 0 else 0,
        })
    
    context = {
        'placements': placements_with_stats,
        'form': form,
    }
    
    return render(request, 'advertisements/placements.html', context)

@login_required
@user_passes_test(is_ads_admin)
@require_POST
def toggle_ad_status(request, pk):
    """تفعيل/تعطيل الإعلان"""
    ad = get_object_or_404(Advertisement, pk=pk)
    
    # تغيير حالة الإعلان
    ad.active = not ad.active
    ad.save()
    
    # مسح الكاش
    clear_ad_cache(ad.placement.code)
    
    status = _('تفعيل') if ad.active else _('إيقاف')
    messages.success(request, f'تم {status} الإعلان')
    
    return redirect('advertisements:dashboard')

@login_required
@user_passes_test(is_ads_admin)
@require_POST
def delete_ad(request, pk):
    """حذف الإعلان"""
    ad = get_object_or_404(Advertisement, pk=pk)
    
    # حفظ معلومات لحذف الكاش
    placement_code = ad.placement.code
    
    # الحذف
    ad.delete()
    
    # مسح الكاش
    clear_ad_cache(placement_code)
    
    messages.success(request, _('تم حذف الإعلان'))
    return redirect('advertisements:dashboard')

@login_required
@user_passes_test(is_ads_admin)
@require_POST
def bulk_actions(request):
    """إجراءات جماعية على الإعلانات"""
    if request.method == 'POST':
        action = request.POST.get('action')
        ad_ids = request.POST.getlist('ad_ids')
        
        if not ad_ids:
            messages.error(request, _('لم يتم اختيار أي إعلان'))
            return redirect('advertisements:dashboard')
        
        ads = Advertisement.objects.filter(id__in=ad_ids)
        
        # الحصول على جميع أكواد الأماكن المتأثرة
        affected_placements = set(ads.values_list('placement__code', flat=True))
        
        if action == 'activate':
            ads.update(active=True)
            message = _('تم تفعيل الإعلانات المختارة')
        elif action == 'deactivate':
            ads.update(active=False)
            message = _('تم إيقاف الإعلانات المختارة')
        elif action == 'delete':
            count = ads.count()
            ads.delete()
            message = f'تم حذف {count} إعلان'
        else:
            messages.error(request, _('إجراء غير صالح'))
            return redirect('advertisements:dashboard')
        
        # مسح كاش جميع الأماكن المتأثرة
        for placement_code in affected_placements:
            clear_ad_cache(placement_code)
        
        messages.success(request, message)
    
    return redirect('advertisements:dashboard')

# ==============================================
# وظائف API والتقارير
# ==============================================

@login_required
@user_passes_test(is_ads_admin)
def export_analytics(request):
    """تصدير تحليلات الإعلانات كملف CSV"""
    
    # الحصول على معاملات الفترة
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    
    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        except ValueError:
            start_date = timezone.now() - timedelta(days=30)
            end_date = timezone.now()
    else:
        start_date = timezone.now() - timedelta(days=30)
        end_date = timezone.now()
    
    # استجابة CSV
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="ad_analytics_{start_date.strftime("%Y%m%d")}_to_{end_date.strftime("%Y%m%d")}.csv"'
    
    # كتابة BOM لتفعيل UTF-8 في Excel
    response.write('\ufeff')
    
    writer = csv.writer(response)
    
    # كتابة العنوان
    writer.writerow([
        _('عنوان الإعلان'), _('النوع'), _('المكان'), _('المعلن'),
        _('تاريخ البدء'), _('تاريخ الانتهاء'), _('مرات الظهور'), _('النقرات'),
        _('نسبة النقر'), _('الحالة'), _('تاريخ الإنشاء')
    ])
    
    # الحصول على الإعلانات في الفترة المحددة
    ads = Advertisement.objects.filter(
        start_date__gte=start_date,
        end_date__lte=end_date
    ).select_related('placement')
    
    for ad in ads:
        ctr = ad.get_ctr()
        status = _('نشط') if ad.is_active() else _('غير نشط')
        
        writer.writerow([
            ad.title,
            ad.get_ad_type_display(),
            ad.placement.name,
            ad.advertiser_name,
            ad.start_date.strftime('%Y-%m-%d %H:%M'),
            ad.end_date.strftime('%Y-%m-%d %H:%M'),
            ad.impressions,
            ad.clicks,
            f'{ctr:.2f}%',
            status,
            ad.created_at.strftime('%Y-%m-%d %H:%M')
        ])
    
    return response

def ad_json_feed(request, placement_code=None):
    """تغذية JSON للإعلانات (للاستخدام في API أو AJAX)"""
    
    # التحقق من الصلاحيات إذا كان الطلب من داخل النظام
    # عدد الإعلانات المطلوبة
    try:
        count = int(request.GET.get('count', 3))
    except (TypeError, ValueError):
        count = 3
    count = max(count, 1)
    count = min(count, 10)  # حد أقصى 10 إعلانات
    
    # إنشاء استعلام للإعلانات النشطة
    ads_query = Advertisement.objects.filter(
        active=True,
        start_date__lte=timezone.now(),
        end_date__gte=timezone.now()
    ).select_related('placement')
    
    if placement_code:
        ads_query = ads_query.filter(placement__code=placement_code)
    
    # تطبيق الأولوية ثم عشوائية
    ads = list(ads_query.order_by('-priority'))
    
    # إذا كان هناك أكثر من العدد المطلوب، نختار عشوائياً مع مراعاة الأولوية
    if len(ads) > count:
        # فرز حسب الأولوية أولاً
        ads.sort(key=lambda x: x.priority, reverse=True)
        
        # أخذ أعلى الأولويات
        high_priority = [ad for ad in ads if ad.priority >= 3]
        medium_priority = [ad for ad in ads if ad.priority == 2]
        low_priority = [ad for ad in ads if ad.priority <= 1]
        
        selected_ads = []
        
        # توزيع الإعلانات حسب الأولوية
        if high_priority:
            selected_ads.extend(high_priority[:min(count, len(high_priority))])
        
        if len(selected_ads) < count and medium_priority:
            import random
            needed = count - len(selected_ads)
            selected_ads.extend(random.sample(medium_priority, min(needed, len(medium_priority))))
        
        if len(selected_ads) < count and low_priority:
            import random
            needed = count - len(selected_ads)
            selected_ads.extend(random.sample(low_priority, min(needed, len(low_priority))))
        
        ads = selected_ads
    
    # تحضير بيانات JSON
    ads_data = []
    base_url = request.build_absolute_uri('/')[:-1]  # إزالة الشرطة الأخيرة
    
    for ad in ads:
        # تحديد المحتوى حسب النوع
        if ad.ad_type == 'banner' and ad.image:
            content = request.build_absolute_uri(ad.image.url)
        elif ad.ad_type == 'text':
            content = ad.text_content
        elif ad.ad_type == 'html':
            content = ad.html_code
        elif ad.ad_type == 'video':
            content = ad.video_url
        else:
            content = ''
        
        ads_data.append({
            'id': ad.id,
            'uuid': str(ad.uuid),
            'title': ad.title,
            'type': ad.ad_type,
            'content': content,
            'link': ad.link,
            'impression_url': f'{base_url}/ads/impression/{ad.id}/',
            'click_url': f'{base_url}/ads/click/{ad.id}/',
            'width': ad.placement.width,
            'height': ad.placement.height,
            'placement': ad.placement.code,
            'target_blank': ad.target_blank,
            'nofollow': ad.nofollow,
            'html_code': generate_ad_code(ad.ad_type, content, ad.link, ad.id),
        })
    
    return JsonResponse({
        'success': True,
        'ads': ads_data,
        'count': len(ads_data),
        'timestamp': timezone.now().isoformat(),
        'server_time': timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
    })

# ==============================================
# وظائف مساعدة إضافية
# ==============================================

@login_required
@user_passes_test(is_ads_admin)
def edit_placement(request, pk):
    """تعديل مكان الإعلان"""
    placement = get_object_or_404(AdPlacement, pk=pk)
    
    if request.method == 'POST':
        form = AdPlacementForm(request.POST, instance=placement)
        if form.is_valid():
            form.save()
            
            # مسح الكاش
            clear_ad_cache(placement.code)
            
            messages.success(request, _('تم تحديث مكان الإعلان'))
            return redirect('advertisements:placements')
    else:
        form = AdPlacementForm(instance=placement)
    
    context = {
        'form': form,
        'title': _('Edit Ad Placement'),
        'placement': placement,
    }
    
    return render(request, 'advertisements/placement_form.html', context)

@login_required
@user_passes_test(is_ads_admin)
@require_POST
def delete_placement(request, pk):
    """حذف مكان الإعلان"""
    placement = get_object_or_404(AdPlacement, pk=pk)
    
    # التحقق من عدم وجود إعلانات مرتبطة
    if placement.advertisement_set.exists():
        messages.error(request, _('لا يمكن حذف مكان يحتوي على إعلانات. انقل الإعلانات أو احذفها أولاً.'))
        return redirect('advertisements:placements')
    
    # حفظ الكود لحذف الكاش
    placement_code = placement.code
    
    # الحذف
    placement.delete()
    
    # مسح الكاش
    clear_ad_cache(placement_code)
    
    messages.success(request, _('تم حذف مكان الإعلان'))
    return redirect('advertisements:placements')


# ==============================================
# وظائف إضافية لنظام الإعلانات مع التكامل مع المقالات
# ==============================================

@login_required
@user_passes_test(is_ads_admin)
def create_ad_with_targeting(request):
    """إنشاء إعلان جديد مع تحديد وسوم مستهدفة"""
    if request.method == 'POST':
        form = AdvertisementForm(request.POST, request.FILES)
        
        if form.is_valid():
            ad = form.save(commit=False)
            
            # حفظ المستخدم الذي أنشأ الإعلان
            if request.user.is_authenticated:
                ad.created_by = request.user
            
            # إذا كان المستخدم ليس أدمن، نجعل الإعلان غير نشط بانتظار المراجعة
            if not request.user.is_superuser:
                ad.active = False
                ad.notes = f"Pending review by admin. Created by {request.user.username}"
                messages.info(request, _('Your ad has been submitted for review. It will be activated after approval.'))
            
            # التحقق من صحة الصورة إذا كانت من نوع بانر
            if ad.ad_type == 'banner' and 'image' in request.FILES:
                is_valid, error_msg = validate_ad_image(request.FILES['image'])
                if not is_valid:
                    messages.error(request, error_msg)
                    context = {
                        'form': form,
                        'title': _('Create New Advertisement'),
                    }
                    return render(request, 'advertisements/form_with_targeting.html', context)
            
            ad.save()
            form.save_m2m()  # حفظ الوسوم
            
            # مسح الكاش
            clear_ad_cache(ad.placement.code)
            
            messages.success(request, _('Advertisement created successfully with targeted ads.'))
            
            if request.user.is_superuser:
                return redirect('advertisements:dashboard')
            else:
                return redirect('advertisements:preview', pk=ad.pk)
        else:
            messages.error(request, _('Please correct the errors below.'))
    else:
        form = AdvertisementForm()
    
    context = {
        'form': form,
        'title': _('Create New Advertisement with Targeting'),
        'action_url': 'advertisements:create_with_targeting',
        'submit_text': _('Create Targeted Advertisement'),
    }
    
    return render(request, 'advertisements/form_with_targeting.html', context)


# ==============================================
# تقرير الإعلانات وفحص الجاهزية (للـ staff)
# ==============================================
from django.contrib.admin.views.decorators import staff_member_required as _staff


@_staff
def ads_report(request):
    from analytics.reports import RANGES, resolve_range
    from .models import AdDailyStat
    from .readiness import check

    key, start, end = resolve_range(request.GET.get('range', '30d'))
    stats = AdDailyStat.objects.filter(date__gte=timezone.localtime(start).date(), date__lte=timezone.localtime(end).date())
    by_ad = {r['ad']: r for r in stats.values('ad').annotate(i=Sum('impressions'), c=Sum('clicks'))}
    now = timezone.now()
    ads = []
    for ad in Advertisement.objects.select_related('placement').order_by('-active', '-end_date'):
        r = by_ad.get(ad.id, {})
        imp, clk = r.get('i') or 0, r.get('c') or 0
        if not ad.active:
            state = ('موقوف', 'off')
        elif ad.start_date > now:
            state = ('مجدول', 'sched')
        elif ad.end_date < now:
            state = ('انتهى', 'off')
        else:
            state = ('يعمل', 'on')
        ads.append({'ad': ad, 'imp': imp, 'clk': clk, 'ctr': round(clk * 100 / imp, 2) if imp else 0,
                    'state': state, 'days_left': ad.days_remaining()})
    totals = stats.aggregate(i=Sum('impressions'), c=Sum('clicks'))
    placements = []
    for p in AdPlacement.objects.all().order_by('-active', '-priority'):
        running = sum(1 for a in ads if a['ad'].placement_id == p.id and a['state'][1] == 'on')
        imp = sum(a['imp'] for a in ads if a['ad'].placement_id == p.id)
        placements.append({'p': p, 'running': running, 'imp': imp})
    daily = list(stats.values('date').annotate(i=Sum('impressions'), c=Sum('clicks')).order_by('date'))
    return render(request, 'advertisements/report.html', {
        'readiness': check(),
        'ads': ads,
        'placements': placements,
        'totals': {'imp': totals['i'] or 0, 'clk': totals['c'] or 0,
                   'ctr': round((totals['c'] or 0) * 100 / totals['i'], 2) if totals['i'] else 0},
        'daily': daily,
        'range_key': key,
        'ranges': RANGES,
    })


@_staff
def ad_csv(request, pk):
    """تقرير يومي لإعلان واحد (للإرسال للمعلن)."""
    from .models import AdDailyStat
    ad = get_object_or_404(Advertisement, pk=pk)
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="ad_{ad.pk}_report.csv"'
    response.write('﻿')
    w = csv.writer(response)
    w.writerow(['التاريخ', 'مرات الظهور', 'النقرات', 'نسبة النقر %'])
    for s in AdDailyStat.objects.filter(ad=ad).order_by('date'):
        w.writerow([s.date.isoformat(), s.impressions, s.clicks, round(s.clicks * 100 / s.impressions, 2) if s.impressions else 0])
    return response
