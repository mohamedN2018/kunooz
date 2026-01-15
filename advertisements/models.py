from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.cache import cache
from django.utils import timezone
import uuid

class AdPlacement(models.Model):
    PLACEMENT_CHOICES = [
        ('header', _('Header')),
        ('sidebar', _('Sidebar')),
        ('footer', _('Footer')),    
        ('between_posts', _('Between Posts')),
        ('popup', _('Popup')),
        ('in_content', _('In Content')),
    ]
    
    name = models.CharField(_('Placement Name'), max_length=100)
    code = models.SlugField(unique=True)
    placement_type = models.CharField(max_length=20, choices=PLACEMENT_CHOICES)
    description = models.TextField(blank=True)
    width = models.PositiveIntegerField(default=300)
    height = models.PositiveIntegerField(default=250)
    active = models.BooleanField(default=True)
    max_ads = models.PositiveIntegerField(default=5, help_text=_('Maximum number of ads to show in this placement'))
    priority = models.IntegerField(default=1, help_text=_('Higher priority placements are shown first'))
    
    # تواريخ الإنشاء والتحديث
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-priority', 'name']
        verbose_name = _('Ad Placement')
        verbose_name_plural = _('Ad Placements')
    
    def __str__(self):
        return self.name
    
    def active_ad_count(self):
        """عدد الإعلانات النشطة في هذا المكان"""
        return self.advertisement_set.filter(
            active=True,
            start_date__lte=timezone.now(),
            end_date__gte=timezone.now()
        ).count()
    
    def save(self, *args, **kwargs):
        # مسح الكاش عند حفظ التغييرات
        super().save(*args, **kwargs)
        cache.delete(f'ad_{self.code}_*')

class Advertisement(models.Model):
    AD_TYPE_CHOICES = [
        ('banner', _('Banner Image')),
        ('text', _('Text Ad')),
        ('html', _('HTML Code')),
        ('video', _('Video Ad')),
    ]
    
    # معلومات أساسية
    title = models.CharField(_('Ad Title'), max_length=200)
    placement = models.ForeignKey(AdPlacement, on_delete=models.CASCADE, verbose_name=_('Ad Placement'))
    ad_type = models.CharField(max_length=10, choices=AD_TYPE_CHOICES, default='banner')
    
    # المحتوى حسب النوع
    image = models.ImageField(upload_to='ads/banners/%Y/%m/', blank=True, null=True, 
                             verbose_name=_('Banner Image'))
    text_content = models.TextField(blank=True, verbose_name=_('Text Content'))
    html_code = models.TextField(blank=True, verbose_name=_('HTML Code'))
    video_url = models.URLField(blank=True, verbose_name=_('Video URL'))
    
    # الرابط والتفاصيل
    link = models.URLField(verbose_name=_('Destination URL'))
    target_blank = models.BooleanField(default=True, verbose_name=_('Open in new tab'))
    nofollow = models.BooleanField(default=True, verbose_name=_('Add nofollow attribute'))
    
    # الجدولة
    start_date = models.DateTimeField(verbose_name=_('Start Date'))
    end_date = models.DateTimeField(verbose_name=_('End Date'))
    
    # الإحصائيات
    impressions = models.PositiveIntegerField(default=0, verbose_name=_('Impressions'))
    clicks = models.PositiveIntegerField(default=0, verbose_name=_('Clicks'))
    
    # الحالة والإعدادات
    active = models.BooleanField(default=True, verbose_name=_('Active'))
    priority = models.IntegerField(default=1, verbose_name=_('Priority'), 
                                  help_text=_('Higher priority ads are shown first'))
    
    # معلومات إضافية
    advertiser_name = models.CharField(max_length=100, blank=True, verbose_name=_('Advertiser Name'))
    advertiser_email = models.EmailField(blank=True, verbose_name=_('Advertiser Email'))
    notes = models.TextField(blank=True, verbose_name=_('Internal Notes'))
    
    # التواريخ
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_impression = models.DateTimeField(null=True, blank=True)
    last_click = models.DateTimeField(null=True, blank=True)
    
    # معرف فريد
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    class Meta:
        ordering = ['-priority', '-start_date']
        verbose_name = _('Advertisement')
        verbose_name_plural = _('Advertisements')
        indexes = [
            models.Index(fields=['active', 'start_date', 'end_date']),
            models.Index(fields=['placement', 'active']),
            models.Index(fields=['ad_type']),
        ]
    
    def __str__(self):
        return self.title
    
    def is_active(self):
        """التحقق إذا كان الإعلان نشط حالياً"""
        now = timezone.now()
        return self.active and self.start_date <= now <= self.end_date
    
    def record_impression(self):
        """تسجيل ظهور للإعلان"""
        self.impressions += 1
        self.last_impression = timezone.now()
        self.save(update_fields=['impressions', 'last_impression'])
    
    def record_click(self):
        """تسجيل نقرة على الإعلان"""
        self.clicks += 1
        self.last_click = timezone.now()
        self.save(update_fields=['clicks', 'last_click'])
    
    def get_ctr(self):
        """حساب نسبة النقر للظهور"""
        if self.impressions > 0:
            return (self.clicks / self.impressions) * 100
        return 0
    
    def days_remaining(self):
        """عدد الأيام المتبقية حتى انتهاء الإعلان"""
        if self.end_date:
            remaining = (self.end_date.date() - timezone.now().date()).days
            return max(0, remaining)
        return 0
    
    def get_display_html(self):
        """الحصول على كود HTML لعرض الإعلان"""
        base_url = '/ads/'
        
        if self.ad_type == 'banner' and self.image:
            target = ' target="_blank"' if self.target_blank else ''
            rel = ' rel="nofollow"' if self.nofollow else ''
            
            return f'''
            <div class="advertisement" data-ad-id="{self.id}" data-ad-uuid="{self.uuid}">
                <a href="{base_url}click/{self.id}/"{target}{rel}
                   onclick="this.parentNode.querySelector('.ad-impression').src='{base_url}impression/{self.id}/';">
                    <img src="{self.image.url}" alt="{self.title}" 
                         style="width:100%; height:auto; max-width:{self.placement.width}px;">
                </a>
                <img src="{base_url}impression/{self.id}/" class="ad-impression" style="display:none;">
            </div>
            '''
        
        # أنواع أخرى من الإعلانات...
        return f'<div data-ad-id="{self.id}">{self.title}</div>'
    
    def clean(self):
        """تنظيف وفحص البيانات قبل الحفظ"""
        from django.core.exceptions import ValidationError
        
        if self.start_date >= self.end_date:
            raise ValidationError(_('End date must be after start date'))
        
        if self.start_date < timezone.now():
            raise ValidationError(_('Start date cannot be in the past'))
    
    def save(self, *args, **kwargs):
        # تنظيف البيانات قبل الحفظ
        self.clean()
        
        # مسح الكاش عند الحفظ
        if self.pk:
            old_ad = Advertisement.objects.get(pk=self.pk)
            if old_ad.placement != self.placement:
                cache.delete(f'ad_{old_ad.placement.code}_*')
        
        super().save(*args, **kwargs)
        
        # مسح كاش المكان الجديد
        cache.delete(f'ad_{self.placement.code}_*')