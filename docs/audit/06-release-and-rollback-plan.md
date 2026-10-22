# 06 — خطة النشر على Dokploy والتراجع

**لم يتم أي نشر.** هذه الخطوات لتنفذها أنت عندما تقرر.

## قبل النشر
1. **لا ترفع** `Dockerfile` و `docker-compose.yml` المعدّلين محلياً. استرجع نسخة git لهما:
   `git restore Dockerfile docker-compose.yml` (أو احتفظ بنسختك في فرع آخر إن كنت تحتاجها).
2. حدّث `Pipfile.lock` لأن `bleach[css]` أُضيفت للـ Pipfile: `pipenv lock` (الـ Dockerfile يبني منها).
   بدونها يعمل الموقع بتنظيف HTML أساسي فقط (لن يتعطل).
3. خذ نسخة احتياطية من قاعدة PostgreSQL في Dokploy (Backups → Run) ومن مجلد `media`.

## متغيرات البيئة في Dokploy
- لا شيء إلزامي جديد. `DEBUG` سيصبح `False` تلقائياً (هذا هو الإصلاح الأهم).
- اختياري: `EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD` موجودة أصلاً وستُستخدم الآن فعلاً لإرسال إعادة تعيين كلمة المرور.
- إذا كان Dokploy/Traefik يخدم `/media/` بنفسه: `SERVE_MEDIA=False`.

## ⚠️ نقطة يجب التحقق منها بعد النشر مباشرة
مع `DEBUG=False`:
- ملفات static تُخدم الآن عبر WhiteNoise (كانت تُخدم عبر DEBUG). تأكد أن `collectstatic` يعمل في البناء أو شغّله:
  `python manage.py collectstatic --noinput`.
- ملفات media (صور المنشورات) تُخدم عبر `SERVE_MEDIA=True`.
افتح الصفحة الرئيسية وصفحة منشور وتأكد أن الشعار والصور تظهر.

## لا توجد migrations
`makemigrations --check` → No changes. لا يلزم `migrate`.

## بعد النشر
- Google Search Console → Sitemaps → أعد إرسال `https://kunooz.deplois.net/sitemap.xml`.
- افتح رابطاً غير موجود وتأكد أن الصفحة أصبحت "الصفحة غير موجودة" العربية وليست صفحة Debug.

## التراجع
`git revert <commit>` ثم إعادة النشر من Dokploy. لا توجد تغييرات في قاعدة البيانات لذا التراجع آمن.


## تحديث: migrations جديدة (تحتاج تشغيل `migrate` عند النشر)
| Migration | ماذا تفعل | الخطورة |
|---|---|---|
| `core.0004_tags_revisions_review_deadline` | تنشئ جدولي `core_tag` و `core_postrevision` وجدول الربط، وتضيف عمود `deadline` (nullable) لـ `core_post` | منخفضة — إضافة فقط، لا حذف ولا تعديل بيانات |
| `advertisements.0002_arabic_labels` | تغيير verbose_name فقط | لا شيء — SQL فارغ (`BEGIN; COMMIT;`) مُتحقق بـ sqlmigrate |

**قبل `migrate` على الإنتاج: خذ نسخة احتياطية من PostgreSQL** (`pg_dump`).
الرجوع: `python manage.py migrate core 0003` يحذف الجداول الجديدة وعمود deadline (تُفقد الوسوم/النسخ/المواعيد المُدخلة بعد النشر فقط).

متغيرات بيئة جديدة اختيارية: `REQUIRE_EDITOR_REVIEW` (افتراضي False)، `SECURE_SSL_REDIRECT` (False)، `SECURE_HSTS_SECONDS` (0).
`Pipfile.lock` أُعيد توليده بإضافة bleach 6.4.0 و tinycss2 و webencodings فقط (باقي الإصدارات كما هي).


## تحديث 2: المحرر والتحسينات الشاملة
| Migration | ماذا تفعل | الخطورة |
|---|---|---|
| `core.0005_content_plain_textfield` | `content` من RichTextField (ckeditor) إلى TextField | على PostgreSQL لا تغيير فعلي (النوعان `text`). على SQLite يعيد إنشاء الجدول (اختُبر على نسخة: المحتوى سليم 100%) |

- **المحرر**: CKEditor 4 (منتهي الدعم، ثغرات معروفة، كان يُحمَّل من cdn.ckeditor.com 4.16.2) استُبدل بـ **Jodit 4.15.13 (MIT)** محفوظ محلياً في `static/vendor/jodit/`. يعمل في صفحات الإنشاء/التعديل وفي Django Admin. رفع الصور عبر `/editor/upload-image/` (محررون فقط، صور حقيقية فقط بفحص Pillow، 5MB، إعادة ترميز تزيل EXIF، تُحفظ في `media/posts/content/`).
  - حزمة `django-ckeditor` باقية في المتطلبات لأن migration 0001 تستورد `ckeditor.fields` — لا تحذفها.
- **Tailwind**: كان يُحمَّل من `cdn.tailwindcss.com` (يولّد CSS في متصفح كل زائر، غير مخصص للإنتاج). الآن `static/css/tailwind.css` مبني مسبقاً (101KB). **بعد تعديل أي قالب يضيف كلاسات جديدة:** `cd frontend && npm ci && npm run build` ثم commit الملف الناتج.
- **/health**: Dokploy كان يطلبه كل 30 ثانية ويحصل على 404 — يرجع الآن `{"status":"ok","db":true}` (أو 503 إن تعطلت قاعدة البيانات).
- `/login/` و `/logout/` المكررتان في `kunooz/urls.py` أُزيلتا (كانتا تطغيان على views الموقع).

### متغيرات بيئة اختيارية جديدة
لا شيء إلزامي. (`REQUIRE_EDITOR_REVIEW`, `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS` من التحديث السابق.)

### خطوات النشر (ملخص)
1. `pg_dump` نسخة احتياطية.
2. commit + push (بدون `Dockerfile` و `docker-compose.yml` المعدّلين محلياً).
3. Deploy من Dokploy ثم داخل الحاوية: `python manage.py migrate` و `python manage.py collectstatic --noinput`.
4. تحقق: `/health`، صفحة منشور، `/create-post/` (المحرر يظهر)، `/admin/`، `/sitemap.xml`، `/feed/`.


## تحديث 3: التحليلات الشاملة ونظام الإعلانات
| Migration | ماذا تفعل | الخطورة |
|---|---|---|
| `analytics.0002_visit_entry_exit` | 5 أعمدة جديدة nullable/بقيم افتراضية في `analytics_visitorsession` | منخفضة — إضافة فقط |
| `advertisements.0003_daily_stats` | جدول جديد `advertisements_addailystat` | منخفضة — إضافة فقط |
| `advertisements.0004_default_placements` | **بيانات**: ينشئ 7 أماكن إعلانية بأكوادها (`get_or_create` — لا يلمس الموجود). التراجع يحذف فقط الأماكن الفارغة التي أنشأها | منخفضة |
| `core.0006_ads_and_legal_settings` | 5 أعمدة جديدة في `core_sitesettings` (الإعلانات مغلقة افتراضياً) | منخفضة — إضافة فقط |

**لا يظهر أي إعلان للزوار بعد النشر** حتى تفعّل "تفعيل الإعلانات" من إعدادات الموقع.

### ما تغيّر في التحليلات
- الزيارة تنتهي بعد 30 دقيقة خمول أو عند إغلاق الصفحة (إشارة `/t/leave/`) — قبلها لم يكن يُسجَّل "خروج" أبداً.
- نبض كل 30 ثانية (`/t/ping/`) لحساب "متصل الآن" بدقة.
- كوكي `kz_vid` (سنة) لعدّ الزوار الفريدين والعائدين.
- لا يُحسب: البوتات وأدوات مثل curl/HeadlessChrome، موظفو الموقع (staff)، والمسارات غير الموجودة (فحوص آلية مثل `/v1/models/`) — كانت تضخّم الأرقام.
- الدولة: من ترويسة Cloudflare `CF-IPCountry` إن وُجدت، أو قاعدة GeoIP2 عبر `GEOIP_PATH` (اختياري). بدونهما تظهر "غير معروف".
- `/analytics/dashboard/` = لوحة "حركة الزوار" الجديدة؛ اللوحة القديمة على `/analytics/dashboard/advanced/`.

### ما تغيّر في الإعلانات
- 7 أماكن مدمجة في القوالب عبر `{% ad_slot 'code' %}` (بدل iframes المعطلة).
- الظهور يُحسب عند رؤية الإعلان فعلاً (50% لثانية) — لا عند تحميل الصفحة — ويُحفظ يومياً (`AdDailyStat`).
- `/ads/report/`: فحص جاهزية + أداء الأماكن والإعلانات + CSV لكل إعلان.
- صفحات عامة جديدة: `/about/`، `/privacy/`، `/advertise/`، و `/ads.txt`.
