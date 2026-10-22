#!/bin/sh
# يعمل تلقائياً عند كل تشغيل للحاوية (بعد كل نشر من Dokploy):
#   1) انتظار قاعدة البيانات
#   2) نسخة احتياطية JSON (فقط إذا كان هناك migrations جديدة)
#   3) migrate
#   4) نسخ الصور الموجودة في git إلى الـ volume الدائم (بدون الكتابة فوق أي صورة موجودة)
#   5) تشغيل gunicorn
set -e

APP=/usr/src/app
cd "$APP"
log() { echo "[entrypoint] $(date '+%Y-%m-%d %H:%M:%S') $*"; }

if [ "${LOCAL:-True}" = "False" ] && [ -n "$DB_HOST" ]; then
    log "انتظار قاعدة البيانات ${DB_HOST}:${DB_PORT:-5432} ..."
    i=0
    until pg_isready -h "$DB_HOST" -p "${DB_PORT:-5432}" -U "${DB_USER:-postgres}" -q; do
        i=$((i + 1))
        if [ "$i" -ge 60 ]; then log "قاعدة البيانات لم تستجب خلال 120 ثانية"; exit 1; fi
        sleep 2
    done
    log "قاعدة البيانات جاهزة"
fi

if [ "${SKIP_MIGRATE:-False}" != "True" ]; then
    if ! python manage.py migrate --check >/dev/null 2>&1; then
        log "توجد migrations جديدة → نسخة احتياطية كاملة لقاعدة البيانات قبل التطبيق"
        if python scripts/backup_db.py /s3files/backups --keep 10; then
            log "تم حفظ النسخة الاحتياطية في /s3files/backups"
        else
            log "خطأ: فشلت النسخة الاحتياطية — لن تُطبَّق migrations (SKIP_BACKUP=True لتجاوز ذلك عمداً)"
            [ "${SKIP_BACKUP:-False}" = "True" ] || exit 1
        fi
        log "تطبيق migrations ..."
        python manage.py migrate --noinput
    else
        log "لا توجد migrations جديدة"
    fi
fi

# الصور المحفوظة في git (media-seed داخل الصورة) → volume الصور الدائم، دون استبدال أي ملف موجود
if [ -d "$APP/media-seed" ]; then
    mkdir -p "$APP/media"
    cp -rn "$APP/media-seed/." "$APP/media/" 2>/dev/null || true
    log "تمت مزامنة الصور الأساسية مع volume الصور"
fi

log "تشغيل: $*"
exec "$@"
