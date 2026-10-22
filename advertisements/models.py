from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.cache import cache
from django.utils import timezone
import uuid
from django.utils.html import escape

class AdPlacement(models.Model):
    PLACEMENT_CHOICES = [
        ('header', _('الترويسة')),
        ('sidebar', _('الشريط الجانبي')),
        ('footer', _('التذييل')),    
        ('between_posts', _('بين المنشورات')),
        ('popup', _('نافذة منبثقة')),
        ('in_content', _('داخل المحتوى')),
    ]
    
    name = models.CharField(_('اسم المكان'), max_length=100)
    code = models.SlugField(unique=True)
    placement_type = models.CharField(max_length=20, choices=PLACEMENT_CHOICES)
    description = models.TextField(blank=True)
    width = models.PositiveIntegerField(default=300)
    height = models.PositiveIntegerField(default=250)
    active = models.BooleanField(default=True)
    max_ads = models.PositiveIntegerField(default=5, help_text=_('أقصى عدد إعلانات يظهر في هذا المكان'))
    priority = models.IntegerField(default=1, help_text=_('الأماكن ذات الأولوية الأعلى تظهر أولاً'))
    
    # تواريخ الإنشاء والتحديث
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-priority', 'name']
        verbose_name = _('مكان الإعلان')
        verbose_name_plural = _('أماكن الإعلانات')
    
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
        cache.delete(f'ad_render_{self.code}')

class Advertisement(models.Model):
    AD_TYPE_CHOICES = [
        ('banner', _('صورة البانر')),
        ('text', _('إعلان نصي')),
        ('html', _('كود HTML')),
        ('video', _('إعلان فيديو')),
    ]
    
    # معلومات أساسية
    title = models.CharField(_('عنوان الإعلان'), max_length=200)
    placement = models.ForeignKey(AdPlacement, on_delete=models.CASCADE, verbose_name=_('مكان الإعلان'))
    ad_type = models.CharField(max_length=10, choices=AD_TYPE_CHOICES, default='banner')
    
    # المحتوى حسب النوع
    image = models.ImageField(upload_to='ads/banners/%Y/%m/', blank=True, null=True, 
                             verbose_name=_('صورة البانر'))
    text_content = models.TextField(blank=True, verbose_name=_('النص'))
    html_code = models.TextField(blank=True, verbose_name=_('كود HTML'))
    video_url = models.URLField(blank=True, verbose_name=_('رابط الفيديو'))
    
    # الرابط والتفاصيل
    link = models.URLField(verbose_name=_('رابط الوجهة'))
    target_blank = models.BooleanField(default=True, verbose_name=_('فتح في تبويب جديد'))
    nofollow = models.BooleanField(default=True, verbose_name=_('إضافة nofollow للرابط'))
    
    # الجدولة
    start_date = models.DateTimeField(verbose_name=_('تاريخ البدء'))
    end_date = models.DateTimeField(verbose_name=_('تاريخ الانتهاء'))
    
    # الإحصائيات
    impressions = models.PositiveIntegerField(default=0, verbose_name=_('مرات الظهور'))
    clicks = models.PositiveIntegerField(default=0, verbose_name=_('النقرات'))
    
    # الحالة والإعدادات
    active = models.BooleanField(default=True, verbose_name=_('نشط'))
    priority = models.IntegerField(default=1, verbose_name=_('الأولوية'), 
                                  help_text=_('الإعلانات ذات الأولوية الأعلى تظهر أولاً'))
    
    # معلومات إضافية
    advertiser_name = models.CharField(max_length=100, blank=True, verbose_name=_('اسم المعلن'))
    advertiser_email = models.EmailField(blank=True, verbose_name=_('بريد المعلن'))
    notes = models.TextField(blank=True, verbose_name=_('ملاحظات داخلية'))
    
    # التواريخ
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_impression = models.DateTimeField(null=True, blank=True)
    last_click = models.DateTimeField(null=True, blank=True)
    
    # معرف فريد
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    class Meta:
        ordering = ['-priority', '-start_date']
        verbose_name = _('إعلان')
        verbose_name_plural = _('الإعلانات')
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
        """تسجيل ظهور للإعلان (ذري: لا يضيع العد مع الطلبات المتزامنة) + إحصائية اليوم"""
        now = timezone.now()
        Advertisement.objects.filter(pk=self.pk).update(impressions=models.F('impressions') + 1, last_impression=now)
        AdDailyStat.bump(self, impressions=1)
        self.impressions += 1
        self.last_impression = now

    def record_click(self):
        """تسجيل نقرة على الإعلان"""
        now = timezone.now()
        Advertisement.objects.filter(pk=self.pk).update(clicks=models.F('clicks') + 1, last_click=now)
        AdDailyStat.bump(self, clicks=1)
        self.clicks += 1
        self.last_click = now
    
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
                    <img src="{self.image.url}" alt="{escape(self.title)}" 
                         style="width:100%; height:auto; max-width:{self.placement.width}px;">
                </a>
                <img src="{base_url}impression/{self.id}/" class="ad-impression" style="display:none;">
            </div>
            '''
        
        # أنواع أخرى من الإعلانات...
        return f'<div data-ad-id="{self.id}">{escape(self.title)}</div>'
    
    def clean(self):
        """تنظيف وفحص البيانات قبل الحفظ"""
        from django.core.exceptions import ValidationError
        
        if self.start_date >= self.end_date:
            raise ValidationError(_('يجب أن يكون تاريخ الانتهاء بعد تاريخ البدء'))
        
        # للإعلانات الجديدة فقط؛ كان يُطبق على كل حفظ فيفشل تسجيل الظهور/النقر وأي تعديل بمجرد بدء الإعلان
        if self._state.adding and self.start_date < timezone.now() - timezone.timedelta(minutes=5):
            raise ValidationError(_('لا يمكن أن يكون تاريخ البدء في الماضي'))

    def save(self, *args, **kwargs):
        # تنظيف البيانات قبل الحفظ (ليس عند تحديث العدادات فقط)
        if not kwargs.get('update_fields'):
            self.clean()

        # مسح الكاش عند الحفظ
        if self.pk and not self._state.adding:
            old_ad = Advertisement.objects.filter(pk=self.pk).select_related('placement').first()
            if old_ad and old_ad.placement_id != self.placement_id:
                cache.delete(f'ad_render_{old_ad.placement.code}')

        super().save(*args, **kwargs)

        # مسح كاش المكان الجديد
        cache.delete(f'ad_render_{self.placement.code}')


class AdDailyStat(models.Model):
    """ظهور ونقرات كل إعلان يوماً بيوم (للتقارير والفواتير للمعلنين)."""
    ad = models.ForeignKey(Advertisement, on_delete=models.CASCADE, related_name='daily_stats', verbose_name='الإعلان')
    date = models.DateField(verbose_name='اليوم')
    impressions = models.PositiveIntegerField(default=0, verbose_name='مرات الظهور')
    clicks = models.PositiveIntegerField(default=0, verbose_name='النقرات')

    class Meta:
        verbose_name = 'إحصائية يومية'
        verbose_name_plural = 'إحصائيات الإعلانات اليومية'
        ordering = ['-date']
        constraints = [models.UniqueConstraint(fields=['ad', 'date'], name='unique_ad_day')]

    def __str__(self):
        return f'{self.ad} — {self.date}'

    @classmethod
    def bump(cls, ad, impressions=0, clicks=0):
        today = timezone.localdate()
        updated = cls.objects.filter(ad=ad, date=today).update(
            impressions=models.F('impressions') + impressions, clicks=models.F('clicks') + clicks)
        if not updated:
            from django.db import IntegrityError, transaction
            try:
                with transaction.atomic():
                    cls.objects.create(ad=ad, date=today, impressions=impressions, clicks=clicks)
            except IntegrityError:  # طلب متزامن أنشأه للتو
                cls.objects.filter(ad=ad, date=today).update(
                    impressions=models.F('impressions') + impressions, clicks=models.F('clicks') + clicks)
