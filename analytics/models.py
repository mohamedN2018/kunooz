from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta, datetime
import uuid
import json

class Country(models.Model):
    """تخزين بيانات الدول"""
    name = models.CharField(max_length=100, verbose_name="اسم الدولة")
    code = models.CharField(max_length=10, unique=True, verbose_name="كود الدولة")
    flag_emoji = models.CharField(max_length=10, blank=True, null=True, verbose_name="إيموجي العلم")
    visits = models.PositiveIntegerField(default=0, verbose_name="عدد الزيارات")
    total_time_spent = models.DurationField(default=timedelta(0), verbose_name="إجمالي الوقت المنقضي")
    last_visit = models.DateTimeField(null=True, blank=True, verbose_name="آخر زيارة")
    
    class Meta:
        verbose_name = "دولة"
        verbose_name_plural = "الدول"
        ordering = ['-visits']
    
    def __str__(self):
        return f"{self.flag_emoji or '🌐'} {self.name}"
    
    def avg_time_spent(self):
        """متوسط الوقت المنقضي في الدولة"""
        if self.visits > 0:
            avg_seconds = self.total_time_spent.total_seconds() / self.visits
            return timedelta(seconds=int(avg_seconds))
        return timedelta(0)

class VisitorSession(models.Model):
    """تتبع جلسات الزوار بشكل مفصل"""
    session_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name="معرف الجلسة")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="المستخدم")
    ip_address = models.GenericIPAddressField(verbose_name="عنوان IP")
    user_agent = models.TextField(verbose_name="معلومات المتصفح")
    device_type = models.CharField(max_length=50, verbose_name="نوع الجهاز")
    browser = models.CharField(max_length=100, verbose_name="المتصفح")
    browser_version = models.CharField(max_length=50, blank=True, null=True, verbose_name="إصدار المتصفح")
    os = models.CharField(max_length=100, verbose_name="نظام التشغيل")
    os_version = models.CharField(max_length=50, blank=True, null=True, verbose_name="إصدار نظام التشغيل")
    
    # معلومات جغرافية مفصلة
    country = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="الدولة")
    region = models.CharField(max_length=100, blank=True, null=True, verbose_name="المنطقة")
    city = models.CharField(max_length=100, blank=True, null=True, verbose_name="المدينة")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True, verbose_name="خط العرض")
    longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True, verbose_name="خط الطول")
    
    # بيانات الجلسة
    referrer = models.URLField(blank=True, null=True, verbose_name="المصدر")
    landing_page = models.URLField(verbose_name="صفحة الهبوط")
    start_time = models.DateTimeField(auto_now_add=True, verbose_name="وقت البدء")
    end_time = models.DateTimeField(null=True, blank=True, verbose_name="وقت الانتهاء")
    is_active = models.BooleanField(default=True, verbose_name="نشطة")
    
    # إحصائيات الجلسة
    page_count = models.PositiveIntegerField(default=1, verbose_name="عدد الصفحات")
    total_time_spent = models.DurationField(default=timedelta(0), verbose_name="إجمالي الوقت المنقضي")
    
    # بيانات إضافية
    metadata = models.JSONField(default=dict, blank=True, verbose_name="بيانات إضافية")

    # تتبع الدخول والخروج
    visitor_id = models.UUIDField(null=True, blank=True, db_index=True, verbose_name="معرف الزائر",
                                  help_text="ثابت لنفس المتصفح (كوكي سنة) لحساب الزوار الفريدين والعائدين")
    is_returning = models.BooleanField(default=False, verbose_name="زائر عائد")
    last_seen = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="آخر نشاط")
    entry_source = models.CharField(max_length=20, blank=True, default='', verbose_name="مصدر الدخول",
                                    help_text="direct / search / social / referral")
    exit_page = models.URLField(blank=True, null=True, verbose_name="صفحة الخروج")
    
    class Meta:
        verbose_name = "جلسة زائر"
        verbose_name_plural = "جلسات الزوار"
        ordering = ['-start_time']
        indexes = [
            models.Index(fields=['session_id']),
            models.Index(fields=['start_time']),
            models.Index(fields=['country']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"جلسة {self.session_id}"
    
    @property
    def duration(self):
        """مدة الجلسة"""
        if self.end_time:
            return self.end_time - self.start_time
        return timezone.now() - self.start_time
    
    def end_session(self):
        """إنهاء الجلسة"""
        self.end_time = timezone.now()
        self.is_active = False
        self.total_time_spent = self.duration
        self.save()

class SiteAnalytics(models.Model):
    date = models.DateField(unique=True, verbose_name="التاريخ")
    page_views = models.PositiveIntegerField(default=0, verbose_name="مشاهدات الصفحات")
    unique_visitors = models.PositiveIntegerField(default=0, verbose_name="زوار فريدون")
    sessions = models.PositiveIntegerField(default=0, verbose_name="جلسات")
    bounce_rate = models.FloatField(default=0.0, verbose_name="معدل الارتداد")
    avg_session_duration = models.DurationField(default=timedelta(0), verbose_name="متوسط مدة الجلسة")
    
    # إحصائيات المحتوى
    courses_views = models.PositiveIntegerField(default=0, verbose_name="مشاهدات الكورسات")
    articles_views = models.PositiveIntegerField(default=0, verbose_name="مشاهدات المقالات")
    grants_views = models.PositiveIntegerField(default=0, verbose_name="مشاهدات المنح")
    books_views = models.PositiveIntegerField(default=0, verbose_name="مشاهدات الكتب")
    
    # المستخدمين
    new_users = models.PositiveIntegerField(default=0, verbose_name="مستخدمين جدد")
    active_users = models.PositiveIntegerField(default=0, verbose_name="مستخدمين نشطين")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "إحصائيات الموقع"
        verbose_name_plural = "إحصائيات الموقع"
        ordering = ['-date']
    
    def __str__(self):
        return f"إحصائيات {self.date}"

class PageView(models.Model):
    """تتبع مشاهدات الصفحات مع الوقت المنقضي"""
    session = models.ForeignKey(VisitorSession, on_delete=models.CASCADE, related_name='pageviews', verbose_name="الجلسة")
    url = models.URLField(verbose_name="رابط الصفحة")
    title = models.CharField(max_length=500, verbose_name="عنوان الصفحة")
    time_spent = models.DurationField(verbose_name="الوقت المنقضي")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="الوقت")
    scroll_depth = models.PositiveIntegerField(default=0, verbose_name="عمق التمرير (%)")
    is_bounce = models.BooleanField(default=False, verbose_name="ارتداد")
    
    class Meta:
        verbose_name = "مشاهدة صفحة"
        verbose_name_plural = "مشاهدات الصفحات"
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.title} - {self.time_spent}"

class RealTimeVisitor(models.Model):
    """الزوار المتصلين حالياً"""
    session = models.OneToOneField(VisitorSession, on_delete=models.CASCADE, related_name='realtime', verbose_name="الجلسة")
    current_page = models.URLField(verbose_name="الصفحة الحالية")
    time_on_page = models.DurationField(default=timedelta(0), verbose_name="الوقت في الصفحة")
    last_activity = models.DateTimeField(auto_now=True, verbose_name="آخر نشاط")
    
    class Meta:
        verbose_name = "زائر فوري"
        verbose_name_plural = "الزوار الفوريين"
        ordering = ['-last_activity']
    
    def __str__(self):
        return f"زائر فوري: {self.session.session_id}"
    
    @property
    def is_online(self):
        """التحقق إذا كان الزائر لا يزال متصلاً"""
        return (timezone.now() - self.last_activity).seconds < 300  # 5 دقائق

class UserActivity(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="المستخدم")
    activity_type = models.CharField(max_length=100, verbose_name="نوع النشاط")
    description = models.TextField(verbose_name="الوصف")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="بيانات إضافية")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="الوقت")
    
    class Meta:
        verbose_name = "نشاط المستخدم"
        verbose_name_plural = "أنشطة المستخدمين"
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.user.username} - {self.activity_type}"

class RealTimeStat(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="اسم الإحصائية")
    value = models.JSONField(default=dict, verbose_name="القيمة")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخر تحديث")
    
    class Meta:
        verbose_name = "إحصائية فورية"
        verbose_name_plural = "إحصائيات فورية"
    
    def __str__(self):
        return self.name

# إعدادات العرض
class AnalyticsSettings(models.Model):
    enable_tracking = models.BooleanField(default=True, verbose_name="تفعيل التتبع")
    anonymize_ip = models.BooleanField(default=True, verbose_name="إخفاء عناوين IP")
    store_user_data = models.BooleanField(default=True, verbose_name="تخزين بيانات المستخدم")
    dashboard_refresh_interval = models.PositiveIntegerField(default=30, verbose_name="فترة تحديث الداشبورد (ثانية)")
    
    class Meta:
        verbose_name = "إعدادات التحليلات"
        verbose_name_plural = "إعدادات التحليلات"
    
    def __str__(self):
        return "إعدادات التحليلات"
    
class AnalyticsDashboard(models.Model):
    """إعدادات وتكوينات لوحة التحليلات"""
    name = models.CharField(max_length=100, verbose_name="اسم اللوحة")
    widgets = models.JSONField(default=list, verbose_name="عناصر الواجهة")
    refresh_interval = models.PositiveIntegerField(default=30, verbose_name="فترة التحديث (ثانية)")
    is_default = models.BooleanField(default=False, verbose_name="افتراضي")
    
    class Meta:
        verbose_name = "لوحة تحليلات"
        verbose_name_plural = "لوحات التحليلات"
    
    def __str__(self):
        return self.name

class AlertRule(models.Model):
    """قواعد التنبيهات التلقائية"""
    ALERT_TYPES = [
        ('high_traffic', 'حركة مرور عالية'),
        ('low_traffic', 'حركة مرور منخفضة'),
        ('new_country', 'دولة جديدة'),
        ('high_bounce', 'ارتداد مرتفع'),
        ('long_session', 'جلسة طويلة'),
    ]
    
    name = models.CharField(max_length=100, verbose_name="اسم التنبيه")
    alert_type = models.CharField(max_length=50, choices=ALERT_TYPES, verbose_name="نوع التنبيه")
    threshold = models.IntegerField(verbose_name="الحد الأدنى")
    enabled = models.BooleanField(default=True, verbose_name="مفعل")
    recipients = models.JSONField(default=list, verbose_name="المستلمون")
    last_triggered = models.DateTimeField(null=True, blank=True, verbose_name="آخر تشغيل")
    
    class Meta:
        verbose_name = "قاعدة تنبيه"
        verbose_name_plural = "قواعد التنبيهات"
    
    def __str__(self):
        return self.name
