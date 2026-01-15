from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import Advertisement, AdPlacement

@admin.register(AdPlacement)
class AdPlacementAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'placement_type', 'width', 'height', 'active', 'ad_count')
    list_filter = ('placement_type', 'active')
    search_fields = ('name', 'code', 'description')
    list_editable = ('active',)
    
    def ad_count(self, obj):
        return obj.advertisement_set.count()
    ad_count.short_description = _('Number of Ads')

@admin.register(Advertisement)
class AdvertisementAdmin(admin.ModelAdmin):
    list_display = ('title', 'ad_type', 'placement', 'start_date', 
                   'end_date', 'impressions', 'clicks', 'ctr', 'status')
    list_filter = ('ad_type', 'placement', 'active', 'start_date')
    search_fields = ('title', 'text_content', 'html_code')
    date_hierarchy = 'start_date'
    readonly_fields = ('impressions', 'clicks', 'created_at', 'updated_at')
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('title', 'placement', 'ad_type', 'link', 'active')
        }),
        (_('Content'), {
            'fields': ('image', 'text_content', 'html_code', 'video_url'),
            'description': _('Fill only the fields relevant to the selected ad type')
        }),
        (_('Schedule'), {
            'fields': ('start_date', 'end_date')
        }),
        (_('Statistics'), {
            'fields': ('impressions', 'clicks'),
            'classes': ('collapse',)
        }),
    )
    
    def ctr(self, obj):
        if obj.impressions > 0:
            return f"{(obj.clicks / obj.impressions * 100):.2f}%"
        return "0%"
    ctr.short_description = _('CTR')
    
    def status(self, obj):
        return obj.is_active()
    status.boolean = True
    status.short_description = _('Active')
    
    def save_model(self, request, obj, form, change):
        if not change:
            # يمكنك إضافة منطق هنا عند إنشاء إعلان جديد
            pass
        super().save_model(request, obj, form, change)
