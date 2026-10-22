# 04 — الاختبارات والتحقق

## تشغيل الموقع محلياً (Python 3.11 مثل الإنتاج)
```powershell
uv venv --python 3.11 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
$env:MY_SECRET_KEY = "<أي قيمة طويلة للتطوير>"; $env:LOCAL = "True"; $env:DEBUG = "True"
.venv\Scripts\python.exe manage.py runserver
```
ملاحظة: Python 3.14.0a1 المثبت على الجهاز إصدار تجريبي قديم وبه خلل في `urljoin` يكسر كل روابط static/media — لا تستخدمه للمشروع.

## الاختبارات الآلية
`python manage.py test core` → **24 اختبار، كلها ناجحة** (قاعدة بيانات اختبار معزولة).
قبل التعديلات: لم يكن يوجد أي اختبار.

| المجموعة | ما تغطيه |
|---|---|
| PublicPagesTests | كل الصفحات العامة 200، صفحة 404 مخصصة، المسودات لا تظهر في العرض/البحث/الاقتراحات، sitemap بالدومين الصحيح، robots، أرقام الرئيسية الحقيقية، منشور بدون صورة |
| SanitizeTests | إزالة script و on* و javascript:، الحفاظ على التنسيق و YouTube فقط |
| AuthAndPermissionTests | منع open redirect، التحليلات للـ staff فقط، كل لوحات التحكم 200، مراجعة التعليقات، منع المستخدم العادي من الإنشاء |
| PublishingWorkflowTests | النشر المجدول، صلاحيات المعاينة، إنشاء ونشر من محرر |
| AnalyticsTrackingTests | تسجيل الزيارة فعلاً، إخفاء IP، تجاهل البوتات |

## فحوصات أخرى
- `manage.py check` → تحذير واحد فقط: CKEditor 4 منتهي الدعم.
- `makemigrations --check` → No changes (لا توجد migrations جديدة).
- متصفح (Playwright/Chromium) على 6 صفحات × (1366px و 390px): كلها RTL، لا يوجد تمرير أفقي، **0 أخطاء JavaScript**،
  ولا صور مكسورة. قبل التعديلات: أخطاء JS في كل صفحة + صور مكسورة في صفحة المنشور.

## غير مُختبَر
- إرسال بريد إعادة تعيين كلمة المرور فعلياً (لم يُرسل أي بريد).
- رفع الصور عبر المتصفح.
- السلوك على PostgreSQL (الاختبارات على SQLite).
