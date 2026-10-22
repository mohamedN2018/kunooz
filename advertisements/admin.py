from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import Advertisement, AdPlacement, AdDailyStat

@admin.register(AdPlacement)
class AdPlacementAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'placement_type', 'width', 'height', 'max_ads', 'priority', 'active', 'ad_count')
    fields = ('name', 'code', 'placement_type', 'width', 'height', 'max_ads', 'priority', 'active', 'description')
    list_filter = ('placement_type', 'active')
    search_fields = ('name', 'code', 'description')
    list_editable = ('active',)
    
    def ad_count(self, obj):
        return obj.advertisement_set.count()
    ad_count.short_description = _('عدد الإعلانات')

@admin.register(Advertisement)
class AdvertisementAdmin(admin.ModelAdmin):
    list_display = ('title', 'ad_type', 'placement', 'start_date', 
                   'end_date', 'impressions', 'clicks', 'ctr', 'status')
    list_filter = ('ad_type', 'placement', 'active', 'start_date')
    search_fields = ('title', 'text_content', 'html_code')
    date_hierarchy = 'start_date'
    readonly_fields = ('impressions', 'clicks', 'created_at', 'updated_at')
    fieldsets = (
        (_('المعلومات الأساسية'), {
            'fields': ('title', 'placement', 'ad_type', 'link', 'active', 'priority', 'target_blank', 'nofollow')
        }),
        (_('المحتوى'), {
            'fields': ('image', 'text_content', 'html_code', 'video_url'),
            'description': _('املأ الحقول الخاصة بنوع الإعلان المختار فقط')
        }),
        (_('الجدولة'), {
            'fields': ('start_date', 'end_date')
        }),
        ('المعلن', {
            'fields': ('advertiser_name', 'advertiser_email', 'notes')
        }),
        (_('الإحصائيات'), {
            'fields': ('impressions', 'clicks'),
            'classes': ('collapse',)
        }),
    )
    
    def ctr(self, obj):
        if obj.impressions > 0:
            return f"{(obj.clicks / obj.impressions * 100):.2f}%"
        return "0%"
    ctr.short_description = _('نسبة النقر')
    
    def status(self, obj):
        return obj.is_active()
    status.boolean = True
    status.short_description = _('نشط')
    
    def save_model(self, request, obj, form, change):
        if not change:
            # يمكنك إضافة منطق هنا عند إنشاء إعلان جديد
            pass
        super().save_model(request, obj, form, change)


class AdDailyStatInline(admin.TabularInline):
    model = AdDailyStat
    extra = 0
    can_delete = False
    readonly_fields = ('date', 'impressions', 'clicks')
    ordering = ('-date',)
    max_num = 0


AdvertisementAdmin.inlines = [AdDailyStatInline]


@admin.register(AdDailyStat)
class AdDailyStatAdmin(admin.ModelAdmin):
    list_display = ('ad', 'date', 'impressions', 'clicks')
    list_filter = ('date', 'ad__placement')
    date_hierarchy = 'date'
    readonly_fields = ('ad', 'date', 'impressions', 'clicks')

    def has_add_permission(self, request):
        return False
