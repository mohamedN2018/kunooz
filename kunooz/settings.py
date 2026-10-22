import os
from pathlib import Path
from decouple import config
from django.utils.translation import gettext_lazy as _

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent



# =========================
# BASE & SECURITY
# =========================

SECRET_KEY = config('MY_SECRET_KEY')
# DEBUG يُقرأ من البيئة؛ الافتراضي False حتى لا تظهر صفحات الأخطاء التفصيلية في الإنتاج
DEBUG = config('DEBUG', default=False, cast=bool)


MAIN_DOMAIN = config("MAIN_DOMAIN", default="kunooz.deplois.net").replace("https://", "").replace("http://", "").strip("/")

ALLOWED_HOSTS = [
    MAIN_DOMAIN,
    f"www.{MAIN_DOMAIN}",

    # Local development
    "127.0.0.1",
    "localhost",
]

CSRF_TRUSTED_ORIGINS = [
    f"https://{MAIN_DOMAIN}",
    f"https://www.{MAIN_DOMAIN}",
]

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
# يمكن تعطيلها محلياً فقط (http://localhost) عبر متغير البيئة SECURE_COOKIES=False
CSRF_COOKIE_SECURE = config('SECURE_COOKIES', default=True, cast=bool)
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE
SESSION_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
X_FRAME_OPTIONS = 'SAMEORIGIN'  # وليس DENY: CKEditor وإطارات الإعلانات /ads/render/ تُعرض داخل iframe من نفس الموقع
# اختيارية ومعطلة افتراضياً: فعّلها من بيئة Dokploy بعد التأكد أن كل الموقع يعمل على HTTPS.
# HSTS يصعب التراجع عنه (المتصفحات تتذكره)، لذا ابدأ بقيمة صغيرة مثل 3600.
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=False, cast=bool)
SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=0, cast=int)

# خدمة ملفات media من Django (السلوك الحالي في الإنتاج). عطّلها إذا كان الـ reverse proxy يخدمها.
SERVE_MEDIA = config('SERVE_MEDIA', default=True, cast=bool)


# Application definition

INSTALLED_APPS = [
    'jazzmin',
    'django.contrib.sites',
    'django.contrib.sitemaps',

    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # التطبيقات المضافة
    'adminsortable2',
    'crispy_forms',
    # 'ckeditor' أُزيل: المحرر الآن Jodit (static/vendor/jodit). الحزمة باقية لأن migration 0001 تستوردها.
    'django_user_agents',  # تحليل user agents
    'django.contrib.humanize',  # إضافة هذا

    'core',
    'advertisements',
    'analytics',  # تطبيق التحليلات

]
SITE_ID = 1


# إعدادات User Agents
USER_AGENTS_CACHE = 'default'

# إعدادات التحليلات
ANALYTICS_SETTINGS = {
    'ENABLE_TRACKING': config('ANALYTICS_ENABLED', default=True, cast=bool),
    'STORE_USER_DATA': True,
    'ANONYMIZE_IP': True,
    'COOKIE_DURATION': 365,  # أيام
}


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # يخدم ملفات static عند DEBUG=False (مثبتة مسبقاً في requirements.txt)
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'core.middleware.MaintenanceModeMiddleware',  # وضع الصيانة من إعدادات الموقع
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_user_agents.middleware.UserAgentMiddleware',  # تحليل user agents
    'analytics.middleware.AdvancedAnalyticsMiddleware',  # التحليلات المبسطة
]


ROOT_URLCONF = 'kunooz.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.site_settings',
                'core.context_processors.heroSections',
            ],
        },
    },
]

WSGI_APPLICATION = 'kunooz.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

if LOCAL := config('LOCAL', default=True, cast=bool):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': config('DB_ENGINE'),
            'NAME': config('DB_NAME'),
            'USER': config('DB_USER'),
            'PASSWORD': config('DB_PASSWORD'),
            'HOST': config('DB_HOST'),
            'PORT': config('DB_PORT', cast=int),
        }
    }

# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

# الموقع عربي بالكامل: رسائل Django ولوحة الإدارة والتواريخ بالعربية
LANGUAGE_CODE = 'ar'
TIME_ZONE = 'Africa/Cairo'
USE_I18N = True
USE_TZ = True


# =========================
# STATIC & MEDIA
# =========================
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / "static"]
if os.path.isdir("/usr/src/app/static/") and Path("/usr/src/app/static/").resolve() != (BASE_DIR / "static").resolve():
    STATICFILES_DIRS.append("/usr/src/app/static/")
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# إعدادات crispy forms
CRISPY_TEMPLATE_PACK = 'bootstrap4'

# إعدادات التحميلات
FILE_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB

LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/'
LOGIN_URL = '/login/'

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'



# سير عمل المراجعة: عند True لا ينشر محرر المحتوى (غير الـ staff) مباشرة بل يرسل للمراجعة
REQUIRE_EDITOR_REVIEW = config('REQUIRE_EDITOR_REVIEW', default=False, cast=bool)

# الأرقام بالأرقام الإنجليزية ونقطة عشرية (تنسيق ar الافتراضي يستخدم الفاصلة فيكسر قيم CSS مثل width: 12,5%)
FORMAT_MODULE_PATH = ['kunooz.formats']






# إعدادات البريد الإلكتروني
# القيم السرية تُقرأ من البيئة فقط (docker-compose يمرر EMAIL_HOST_USER / EMAIL_HOST_PASSWORD)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_BACKEND = config(
    'EMAIL_BACKEND',
    default='django.core.mail.backends.smtp.EmailBackend' if EMAIL_HOST_USER
    else 'django.core.mail.backends.console.EmailBackend',
)
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = True
EMAIL_TIMEOUT = 15
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default=f'كنوز <{EMAIL_HOST_USER or "noreply@" + MAIN_DOMAIN}>')

# إعدادات الجلسة
SESSION_COOKIE_AGE = 1209600  # أسبوعين بالثواني
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_SAVE_EVERY_REQUEST = True






# =========================
# Jazzmin
# =========================
JAZZMIN_SETTINGS = {
    "site_title": "إدارة كنوز",
    "site_header": "كنوز",
    "site_brand": "كنوز",
    "welcome_sign": "مرحباً بك في لوحة تحكم كنوز",
    "copyright": "كنوز © 2026",
    "search_model": ["core.Post", "core.Category"],
    "user_avatar": None,
    # "language_chooser": True,
    "topmenu_links": [
        {"name": "الرئيسية", "url": "admin:index", "permissions": ["auth.view_user"]},
        {"name": "عرض الموقع", "url": "/", "new_window": True},
    ],
    "icons": {
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user",
        "auth.Group": "fas fa-users",
        "core.Category": "fas fa-folder",
        "core.Tag": "fas fa-tags",
        "core.PostRevision": "fas fa-history",
        "core.Post": "fas fa-newspaper",
        "core.Comment": "fas fa-comments",
        "pages.Page": "fas fa-file",
    },
    "custom_css": "css/admin_rtl.css",
    "default_icon_parents": "fas fa-chevron-circle-left",
    "default_icon_children": "fas fa-circle",
}

JAZZMIN_UI_TWEAKS = {
    "navbar_small_text": False,
    "footer_small_text": False,
    "body_small_text": False,
    "brand_small_text": False,
    "brand_colour": False,
    "accent": "accent-primary",
    "navbar": "navbar-dark",
    "no_navbar_border": False,
    "navbar_fixed": False,
    "layout_boxed": False,
    "footer_fixed": False,
    "sidebar_fixed": False,
    "sidebar": "sidebar-dark-primary",
    "sidebar_nav_small_text": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": False,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": False,
    "theme": "default",
    "dark_mode_theme": None,
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success"
    }
}
