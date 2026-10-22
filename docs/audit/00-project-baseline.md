# 00 — خط الأساس للمشروع (Project Baseline)

التاريخ: 2026-10-22 — فحص محلي فقط. لم يتم أي تعديل على الإنتاج (Dokploy).

## المسار و Git
- المسار: `F:\4_docker-composer\Django Project\1-Online\konoz`
- الفرع: `main` — آخر commit: `00b72e2 add meta`
- تعديلات سابقة غير محفوظة (من صاحب المشروع، لم تُلمس):
  - `Dockerfile` و `docker-compose.yml` معدّلان محلياً (نسخة مختلفة تماماً عن المرفوعة — راجع التحذير بالأسفل).
  - حذف صور: `static/images/{articles-bg.jpg,grants-bg.jpg,back-hero2.png}` ونسخها في `staticfiles/` و `media/`.

## التقنيات الفعلية
| البند | القيمة |
|---|---|
| Framework | Django 5.2.9 |
| Python في الإنتاج | 3.11 (Dockerfile المرفوع: `python:3.11.3-alpine`) |
| قاعدة البيانات | PostgreSQL 17 في الإنتاج (`LOCAL=False`)، SQLite محلياً (`LOCAL=True`، الافتراضي) |
| الخادم | gunicorn (25 worker) خلف Dokploy |
| الواجهة | Django templates + Tailwind عبر CDN + GSAP + AOS + Font Awesome |
| المحرر | CKEditor 4 (من CDN في صفحات الإنشاء/التعديل، و django-ckeditor في الأدمن) |
| لوحة الأدمن | Django Admin + Jazzmin، إضافة للوحات مخصصة `/control/` و `/staff/` و `/content/` |
| الحزم | Pipfile / Pipfile.lock (الـ Dockerfile المرفوع يولّد requirements منها) |

## التطبيقات
- `core`: المنشورات، الأقسام، التعليقات، إعدادات الموقع، قسم الـ Hero، ملفات المستخدمين، سجلات النظام، كل الصفحات العامة ولوحات التحكم.
- `analytics`: تتبع الزوار (Middleware) ولوحات التحليلات.
- `advertisements`: نظام إعلانات (مُعطّل في القوالب حالياً).

## قاعدة البيانات المحلية
`db.sqlite3` (بيانات تجريبية: 4 منشورات، قسم واحد، مستخدم واحد). تم أخذ نسخة احتياطية في `backups/`.
كل الاختبارات اليدوية تمت على نُسخ في `.scratch/` — **لم يتم تعديل db.sqlite3 الأصلي**.
الـ migrations متطابقة مع الموديلات (`makemigrations --check` → No changes). **لم تُنشأ أي migration جديدة.**

## متغيرات البيئة (الأسماء فقط)
`MY_SECRET_KEY`, `LOCAL`, `DB_ENGINE`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `MAIN_DOMAIN`,
`EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`
جديدة (اختيارية، لها قيم افتراضية آمنة): `DEBUG` (افتراضي False), `SECURE_COOKIES` (True), `SERVE_MEDIA` (True),
`ANALYTICS_ENABLED` (True), `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `DEFAULT_FROM_EMAIL`.

## ⚠️ تحذير مهم قبل أي نشر
ملفا `Dockerfile` و `docker-compose.yml` المعدّلان محلياً (غير محفوظين في git) **لا يصلحان للإنتاج**:
يستخدمان `runserver` بدل gunicorn، ومسار `/app` بدل `/usr/src/app`، وقاعدة `postgres:15` بحجم بيانات جديد `db_data`
بدلاً من `postgresql_data` — أي أن رفعهما كما هما على Dokploy سيُشغّل قاعدة بيانات **فارغة**.
النسخ المرفوعة في git (HEAD) هي الصحيحة للإنتاج.

## تشغيل المشروع محلياً
راجع `docs/audit/04-testing-and-verification.md`.
