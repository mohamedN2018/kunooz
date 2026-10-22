from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.conf import settings
from PIL import Image
import os
from django.db.models.signals import post_save
from django.dispatch import receiver
import datetime
import re
import logging
from django.core.exceptions import ValidationError

try:
    import bleach
    from bleach.css_sanitizer import CSSSanitizer
except ImportError:  # يجب تثبيت bleach[css] (موجودة في requirements.txt و Pipfile)
    bleach = None
    logging.getLogger(__name__).warning("bleach غير مثبتة؛ يتم استخدام تنظيف HTML أساسي فقط")


# وسوم HTML المسموحة في محتوى المنشورات (يُعرض بـ |safe لذا يجب تنظيفه من السكربتات)
ALLOWED_CONTENT_TAGS = {
    'p', 'br', 'hr', 'div', 'span', 'blockquote', 'pre', 'code',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'strong', 'b', 'em', 'i', 'u', 's', 'sub', 'sup', 'small', 'mark',
    'ul', 'ol', 'li', 'dl', 'dt', 'dd',
    'a', 'img', 'figure', 'figcaption',
    'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'caption', 'colgroup', 'col',
    'iframe',
}
ALLOWED_CONTENT_ATTRS = {
    '*': ['class', 'style', 'dir', 'lang', 'title'],
    'a': ['href', 'target', 'rel', 'name'],
    'img': ['src', 'alt', 'width', 'height', 'loading'],
    'td': ['colspan', 'rowspan', 'align'],
    'th': ['colspan', 'rowspan', 'align', 'scope'],
    'table': ['border', 'cellpadding', 'cellspacing'],
    'iframe': ['src', 'width', 'height', 'allow', 'allowfullscreen', 'frameborder'],
}
TRUSTED_IFRAME_PREFIXES = (
    'https://www.youtube.com/embed/', 'https://www.youtube-nocookie.com/embed/',
    'https://player.vimeo.com/video/',
)


def _filter_attr(tag, name, value):
    if tag == 'iframe' and name == 'src':
        return value.startswith(TRUSTED_IFRAME_PREFIXES)
    return name in ALLOWED_CONTENT_ATTRS.get(tag, []) or name in ALLOWED_CONTENT_ATTRS['*']


def sanitize_html(html):
    """يزيل السكربتات وخصائص on* وروابط javascript: مع الحفاظ على التنسيق."""
    if not html:
        return html
    if bleach is None:
        html = re.sub(r'(?is)<(script|style|object|embed)\b.*?</\1\s*>', '', html)
        html = re.sub(r'(?i)\s+on[a-z]+\s*=\s*(".*?"|\'.*?\'|[^\s>]+)', '', html)
        return re.sub(r'(?i)(href|src)\s*=\s*(["\']?)\s*javascript:', r'\1=\2#', html)
    return bleach.clean(
        html,
        tags=ALLOWED_CONTENT_TAGS,
        attributes=_filter_attr,
        protocols={'http', 'https', 'mailto', 'tel'},
        css_sanitizer=CSSSanitizer(),
        strip=True,
        strip_comments=True,
    )


class Category(models.Model):
    CATEGORY_TYPES = [
        ('courses', 'الكورسات'),
        ('articles', 'المقالات'),
        ('grants', 'المنح والتدريبات'),
        ('books', 'الكتب والملخصات'),
    ]
    
    name = models.CharField(max_length=100, verbose_name="الاسم")
    category_type = models.CharField(max_length=20, choices=CATEGORY_TYPES, verbose_name="نوع الفئة")
    description = models.TextField(blank=True, verbose_name="الوصف")
    icon = models.CharField(max_length=50, blank=True, verbose_name="الأيقونة")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    
    class Meta:
        verbose_name = 'القسم'
        verbose_name_plural = 'الأقسام'
        ordering = ['name']
    
    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return f"{reverse('search')}?category={self.category_type}"


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name="الوسم")
    slug = models.SlugField(max_length=60, unique=True, allow_unicode=True, verbose_name="الرابط")

    class Meta:
        verbose_name = 'وسم'
        verbose_name_plural = 'الوسوم'
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name, allow_unicode=True)[:50] or "tag"
            slug, i = base, 1
            while Tag.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{i}"
                i += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("tag_posts", kwargs={"slug": self.slug})


class PostQuerySet(models.QuerySet):
    def live(self):
        """
        المنشورات الظاهرة للزوار: حالتها "منشور" وتاريخ نشرها حلّ.
        منشور بتاريخ مستقبلي = نشر مجدول، يظهر تلقائياً عند حلول التاريخ (بدون cron).
        """
        return self.filter(status=Post.Status.PUBLISHED).filter(
            models.Q(publish_date__isnull=True) | models.Q(publish_date__lte=timezone.now())
        )


class Post(models.Model):
    objects = PostQuerySet.as_manager()

    class Status(models.TextChoices):
        DRAFT = 'draft', 'مسودة'
        REVIEW = 'review', 'قيد المراجعة'
        PUBLISHED = 'published', 'منشور'
        PRIVATE = 'private', 'خاص'
        ARCHIVED = 'archived', 'مؤرشف'

    # المعلومات الأساسية
    title = models.CharField(max_length=200, verbose_name="العنوان")
    slug = models.SlugField(max_length=250, unique=True, verbose_name="الرابط")
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='posts', verbose_name="الفئة")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='posts', verbose_name="المؤلف")

    # المحتوى
    # كان RichTextField من django-ckeditor (CKEditor 4 منتهي الدعم وبه ثغرات)؛ المحرر الآن Jodit في الواجهة
    content = models.TextField(verbose_name="المحتوى")
    
    # الصور (القديم والجديد معاً)
    image = models.ImageField(upload_to='posts/featured/%Y/%m/%d/', blank=True, verbose_name="الصورة القديمة")
    featured_image = models.ImageField(upload_to='posts/featured/%Y/%m/', blank=True, verbose_name="الصورة الرئيسية")
    thumbnail = models.ImageField(upload_to='posts/thumbnails/%Y/%m/', blank=True, verbose_name="الصورة المصغرة")

    excerpt = models.TextField(max_length=300, blank=True, verbose_name="الملخص")
    tags = models.ManyToManyField(Tag, blank=True, related_name='posts', verbose_name="الوسوم")
    deadline = models.DateField(blank=True, null=True, verbose_name="آخر موعد للتقديم",
                                help_text="للمنح والتدريبات: يظهر للزائر ويُستخدم في الترتيب")

    # الروابط
    link = models.URLField(blank=True, null=True, verbose_name="رابط خارجي")
    link_delay = models.IntegerField(default=30, blank=True, null=True, verbose_name="تأخير الرابط")

    # الإحصائيات
    views = models.PositiveIntegerField(default=0, verbose_name="المشاهدات")

    # حالة النشر
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, verbose_name="الحالة")
    publish_date = models.DateTimeField(blank=True, null=True, verbose_name="تاريخ النشر")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")

    # SEO
    seo_title = models.CharField(max_length=200, blank=True, verbose_name="عنوان SEO")
    seo_description = models.TextField(max_length=300, blank=True, verbose_name="وصف SEO")
    seo_keywords = models.CharField(max_length=200, blank=True, verbose_name="كلمات مفتاحية SEO")

    class Meta:
        verbose_name = 'منشور'
        verbose_name_plural = 'المنشورات'
        ordering = ['-publish_date', '-created_at']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # إنشاء slug تلقائياً إذا لم يكن موجوداً
        if not self.slug:
            base = slugify(self.title, allow_unicode=True) or "post"
            slug = base
            i = 1
            while Post.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{i}"
                i += 1
            self.slug = slug
        
        # تنظيف المحتوى من HTML خطير (XSS) لأنه يُعرض بدون escaping
        self.content = sanitize_html(self.content)

        # نشر تلقائي
        if self.status == self.Status.PUBLISHED and not self.publish_date:
            self.publish_date = timezone.now()
        
        super().save(*args, **kwargs)
        
        # إنشاء thumbnail تلقائياً إذا كانت featured_image موجودة
        if self.featured_image and not self.thumbnail:
            self.create_thumbnail()

    def create_thumbnail(self):
        """إنشاء صورة مصغرة من الصورة الرئيسية"""
        if not self.featured_image:
            return
        
        try:
            image = Image.open(self.featured_image.path)
            image.thumbnail((400, 300), Image.Resampling.LANCZOS)
            
            thumb_path = self.featured_image.path.replace("featured", "thumbnails")
            os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
            image.save(thumb_path)
            
            # os.path.relpath يعمل على Windows و Linux (split("media/") كان يفشل مع \ في Windows)
            self.thumbnail.name = os.path.relpath(thumb_path, settings.MEDIA_ROOT).replace(os.sep, "/")
            Post.objects.filter(pk=self.pk).update(thumbnail=self.thumbnail.name)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("خطأ في إنشاء الصورة المصغرة للمنشور %s: %s", self.pk, e)

    def get_absolute_url(self):
        return reverse("post_detail", kwargs={"slug": self.slug})

    @property
    def deadline_passed(self):
        return bool(self.deadline) and self.deadline < timezone.localdate()

    @property
    def days_to_deadline(self):
        if not self.deadline:
            return None
        return (self.deadline - timezone.localdate()).days

    @property
    def is_scheduled(self):
        return self.status == self.Status.PUBLISHED and bool(self.publish_date) and self.publish_date > timezone.now()

    def increment_views(self):
        Post.objects.filter(pk=self.pk).update(views=models.F("views") + 1)

    @property
    def display_title(self):
        return self.seo_title or self.title

    @property
    def display_description(self):
        from django.utils.html import strip_tags
        return self.seo_description or self.excerpt or strip_tags(self.content)[:160]
    
    @property
    def card_image(self):
        """
        صورة البطاقات: المصغرة إن كان مسارها سليماً، وإلا الصورة الرئيسية.
        (منشورات قديمة حُفظت مصغرتها بمسار Windows مطلق مثل C:\\Users\\... فتظهر مكسورة)
        """
        name = self.thumbnail.name if self.thumbnail else ''
        if name and ':' not in name and not name.startswith(('/', '\\')):
            return self.thumbnail
        return self.get_main_image

    @property
    def get_main_image(self):
        """الحصول على الصورة الرئيسية (الأفضلية للصورة الجديدة ثم القديمة)"""
        return self.featured_image or self.image


class PostRevision(models.Model):
    """نسخة سابقة من المنشور تُحفظ تلقائياً قبل كل تعديل، ويمكن استرجاعها."""
    KEEP_LAST = 20

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='revisions', verbose_name="المنشور")
    title = models.CharField(max_length=200, verbose_name="العنوان")
    excerpt = models.TextField(blank=True, verbose_name="الملخص")
    content = models.TextField(verbose_name="المحتوى")
    status = models.CharField(max_length=10, verbose_name="الحالة")
    edited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                  verbose_name="بواسطة")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ النسخة")

    class Meta:
        verbose_name = 'نسخة سابقة'
        verbose_name_plural = 'النسخ السابقة'
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'{self.title} — {self.created_at:%Y-%m-%d %H:%M}'

    def get_status_display(self):
        return dict(Post.Status.choices).get(self.status, self.status)

    @classmethod
    def snapshot(cls, post, user=None):
        """يحفظ نسخة من حالة المنشور الحالية في قاعدة البيانات ويحذف ما زاد عن KEEP_LAST."""
        rev = cls.objects.create(
            post=post, title=post.title, excerpt=post.excerpt or '', content=post.content or '',
            status=post.status, edited_by=user if getattr(user, 'is_authenticated', False) else None,
        )
        old_ids = cls.objects.filter(post=post).values_list('id', flat=True)[cls.KEEP_LAST:]
        cls.objects.filter(id__in=list(old_ids)).delete()
        return rev


class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments', verbose_name="المنشور")
    name = models.CharField(max_length=100, verbose_name="الاسم")
    email = models.EmailField(verbose_name="البريد الإلكتروني")
    content = models.TextField(verbose_name="المحتوى")
    is_approved = models.BooleanField(default=False, verbose_name="معتمد")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    
    class Meta:
        verbose_name = 'تعليق'
        verbose_name_plural = 'التعليقات'
        ordering = ['-created_at']
    
    def __str__(self):
        return f'تعليق بواسطة {self.name} على {self.post.title}'


class SiteSettings(models.Model):
    site_name = models.CharField(max_length=200, default='موقع التعليم', verbose_name="اسم الموقع")
    site_description = models.TextField(blank=True, null=True, verbose_name="وصف الموقع")
    site_logo = models.ImageField(upload_to='site/', blank=True, null=True, verbose_name="شعار الموقع")
    
    # إعدادات المحتوى
    default_link_delay = models.IntegerField(default=30, help_text='التأخير الافتراضي بالثواني', verbose_name="تأخير الرابط الافتراضي")
    allow_comments = models.BooleanField(default=True, verbose_name="السماح بالتعليقات")
    require_comment_approval = models.BooleanField(default=True, verbose_name="يتطلب موافقة على التعليقات")
    
    # إعدادات النظام
    maintenance_mode = models.BooleanField(default=False, verbose_name="وضع الصيانة")
    contact_email = models.EmailField(default='contact@example.com', verbose_name="البريد الإلكتروني للتواصل")
    
    # وسائل التواصل الاجتماعي
    facebook_url = models.URLField(blank=True, null=True, verbose_name="رابط الفيسبوك")
    instagram_url = models.URLField(blank=True, null=True, verbose_name="رابط إنستغرام")
    youtube_url = models.URLField(blank=True, null=True, verbose_name="رابط يوتيوب")
    
    # الإعلانات
    ads_enabled = models.BooleanField(default=False, verbose_name="تفعيل الإعلانات في الموقع",
                                      help_text="مغلق افتراضياً. للمعاينة بدون تفعيل: افتح أي صفحة بـ ?ads_preview=1 وأنت مسجل كمشرف")
    adsense_client = models.CharField(max_length=40, blank=True, verbose_name="معرف Google AdSense",
                                      help_text="مثل ca-pub-1234567890123456 — يُحمَّل سكربت AdSense فقط عند تعبئته وتفعيل الإعلانات")
    ads_txt = models.TextField(blank=True, verbose_name="محتوى ads.txt",
                               help_text="يُعرض على /ads.txt — شبكة الإعلانات (مثل AdSense) تعطيك السطر المطلوب")

    # صفحات قانونية (فارغة = نص افتراضي يصف ما يجمعه الموقع فعلاً)
    about_content = models.TextField(blank=True, verbose_name="نص صفحة من نحن")
    privacy_content = models.TextField(blank=True, verbose_name="نص سياسة الخصوصية")

    # التواريخ
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")
    
    def __str__(self):
        return self.site_name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from django.core.cache import cache
        cache.delete('site_maintenance_mode')  # يطبق وضع الصيانة فوراً
        cache.delete('kz_ad_slots')
    
    class Meta:
        verbose_name = 'إعدادات الموقع'
        verbose_name_plural = 'إعدادات الموقع'

class heroSection(models.Model):
    title = models.CharField(max_length=200, verbose_name="العنوان")
    subtitle = models.CharField(max_length=300, blank=True, verbose_name="العنوان الفرعي")
    background_image = models.ImageField(upload_to='site/hero/', blank=True, null=True, verbose_name="صورة الخلفية")
    
    def __str__(self):
        return self.title
    
    class Meta:
        verbose_name = 'hero قسم'
        verbose_name_plural = 'hero قسم'


class SystemLog(models.Model):
    """سجلات النظام"""
    LOG_TYPES = (
        ('info', 'معلومات'),
        ('warning', 'تحذير'),
        ('error', 'خطأ'),
        ('security', 'أمني'),
    )
    
    log_type = models.CharField(max_length=20, choices=LOG_TYPES, default='info', verbose_name="نوع السجل")
    message = models.TextField(verbose_name="الرسالة")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="المستخدم")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="عنوان IP")
    user_agent = models.TextField(blank=True, null=True, verbose_name="معلومات المتصفح")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    
    def __str__(self):
        return f"{self.get_log_type_display()} - {self.message[:50]}"
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'سجل النظام'
        verbose_name_plural = 'سجلات النظام'


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile', verbose_name="المستخدم")
    full_name = models.CharField(max_length=255, blank=True, verbose_name="الاسم الكامل")
    bio = models.TextField(blank=True, null=True, verbose_name="السيرة الذاتية")
    profile_image = models.ImageField(upload_to='profile_images/', blank=True, null=True, verbose_name="صورة الملف الشخصي")
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="الهاتف")
    birth_date = models.DateField(blank=True, null=True, verbose_name="تاريخ الميلاد")
    
    # الصلاحيات
    is_content_editor = models.BooleanField(default=False, verbose_name='محرر محتوى')
    can_manage_comments = models.BooleanField(default=False, verbose_name='يمكنه إدارة التعليقات')
    can_manage_categories = models.BooleanField(default=False, verbose_name='يمكنه إدارة الأقسام')

    # الإحصائيات
    posts_count = models.IntegerField(default=0, verbose_name="عدد المنشورات")
    comments_count = models.IntegerField(default=0, verbose_name="عدد التعليقات")
    last_active = models.DateTimeField(auto_now=True, verbose_name="آخر نشاط")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")
    
    def __str__(self):
        return f'{self.user.username} Profile'
    
    class Meta:
        verbose_name = 'ملف المستخدم'
        verbose_name_plural = 'ملفات المستخدمين'

    def update_stats(self):
        """تحديث إحصائيات المستخدم"""
        self.posts_count = self.user.posts.count()
        self.comments_count = Comment.objects.filter(post__author=self.user).count()
        self.save(update_fields=['posts_count', 'comments_count'])




@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()