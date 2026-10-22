#!/usr/bin/env bash
# =====================================================================
#  نشر كنوز بأمر واحد:   ./scripts/deploy.sh "رسالة التعديل"
#
#  1) فحوص: لا أسرار في الملفات، الاختبارات تنجح، لا migrations ناقصة
#  2) بناء Tailwind إذا تغيّرت القوالب
#  3) commit + push إلى GitHub (main)
#  4) تشغيل النشر على Dokploy عبر الـ webhook
#  5) انتظار الموقع والتحقق من /health والصفحات الأساسية
#
#  رابط الـ webhook سرّي: ضعه في ملف .deploy.env (مُستثنى من git):
#     DOKPLOY_WEBHOOK_URL=https://dash.deplois.net/api/deploy/compose/XXXX
#  أو كمتغير بيئة بنفس الاسم.
# =====================================================================
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT=$(pwd)
SITE_URL="${SITE_URL:-https://kunooz.deplois.net}"
BRANCH="${BRANCH:-main}"
MSG="${1:-}"

c_green='\033[0;32m'; c_red='\033[0;31m'; c_yellow='\033[0;33m'; c_off='\033[0m'
step() { echo -e "\n${c_green}==> $*${c_off}"; }
warn() { echo -e "${c_yellow}!! $*${c_off}"; }
die()  { echo -e "${c_red}xx $*${c_off}" >&2; exit 1; }

[ -f .deploy.env ] && set -a && . ./.deploy.env && set +a

# بايثون المشروع (venv محلي إن وُجد)
if   [ -x .venv/Scripts/python.exe ]; then PY=.venv/Scripts/python.exe
elif [ -x .venv/bin/python ];         then PY=.venv/bin/python
else PY=python3; fi

# ---------- 1) فحوص ----------
step "فحص الأسرار في الملفات المتغيرة"
CHANGED=$(git status --porcelain | awk '{print $NF}')
if [ -n "$CHANGED" ]; then
    if echo "$CHANGED" | grep -E '(^|/)\.env$|\.deploy\.env|db\.sqlite3|\.pem$|id_rsa' ; then
        die "ملف حساس ضمن التغييرات — أضفه إلى .gitignore"
    fi
    # shellcheck disable=SC2086
    if git diff --no-color HEAD -- $(echo "$CHANGED" | grep -E '\.(py|html|js|yml|yaml|sh|txt|md|json)$' || true) 2>/dev/null \
        | grep -E '^\+' | grep -Ei 'api/deploy/compose/[A-Za-z0-9_-]{10,}|ghp_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|EMAIL_HOST_PASSWORD *= *["'"'"'][^"'"'"']+'; then
        die "يبدو أن هناك سراً داخل الكود — راجع السطور أعلاه"
    fi
fi

export MY_SECRET_KEY="${MY_SECRET_KEY:-deploy-check-$(date +%s)-not-a-real-secret-key-0123456789}"
export LOCAL=True DEBUG=False PYTHONIOENCODING=utf-8

step "فحص إعدادات Django"
"$PY" manage.py check --fail-level ERROR

step "التأكد من عدم وجود migrations ناقصة"
"$PY" manage.py makemigrations --check --dry-run >/dev/null || die "هناك تغييرات في الموديلات بدون migration: شغّل makemigrations"

step "تشغيل الاختبارات"
"$PY" manage.py test core advertisements analytics --noinput -v 1

# ---------- 2) Tailwind ----------
if command -v npm >/dev/null 2>&1 && [ -f frontend/package.json ]; then
    step "بناء Tailwind CSS"
    ( cd frontend && { [ -d node_modules ] || npm ci --no-audit --no-fund; } && npm run build --silent )
else
    warn "npm غير موجود — تخطي بناء Tailwind (تأكد أن static/css/tailwind.css محدث)"
fi

# ---------- 3) commit + push ----------
step "رفع التعديلات إلى GitHub ($BRANCH)"
git fetch origin "$BRANCH" --quiet
if ! git merge-base --is-ancestor "origin/$BRANCH" HEAD; then
    die "GitHub فيه تعديلات غير موجودة عندك: نفّذ  git pull --rebase origin $BRANCH  ثم أعد المحاولة"
fi
git add -A
if git diff --cached --quiet; then
    warn "لا توجد تعديلات جديدة للـ commit"
else
    [ -n "$MSG" ] || MSG="تحديث الموقع $(date '+%Y-%m-%d %H:%M')"
    git commit -m "$MSG"
fi
git push origin "HEAD:$BRANCH"
SHA=$(git rev-parse HEAD)
echo "commit: $SHA"

# ---------- 4) Dokploy ----------
if [ -z "${DOKPLOY_WEBHOOK_URL:-}" ]; then
    warn "DOKPLOY_WEBHOOK_URL غير معرف (.deploy.env) — تم الرفع فقط. إن كان Auto Deploy مفعلاً في Dokploy سيبدأ النشر وحده."
    exit 0
fi

step "تشغيل النشر على Dokploy"
# الـ webhook يتوقع حدث push بصيغة GitHub (يقرأ الفرع من ref)
PAYLOAD=$(printf '{"ref":"refs/heads/%s","after":"%s","head_commit":{"id":"%s","message":"%s"},"commits":[]}' \
    "$BRANCH" "$SHA" "$SHA" "$(git log -1 --format=%s | sed 's/"/\\"/g' | head -c 200)")
HTTP=$(curl -sS -o /tmp/kz_deploy_resp.txt -w '%{http_code}' -X POST "$DOKPLOY_WEBHOOK_URL" \
    -H 'Content-Type: application/json' -H 'X-GitHub-Event: push' --data "$PAYLOAD" || echo 000)
echo "Dokploy: HTTP $HTTP — $(cat /tmp/kz_deploy_resp.txt 2>/dev/null)"
[ "$HTTP" = "200" ] || die "Dokploy لم يقبل طلب النشر (تأكد أن Auto Deploy مفعل والفرع $BRANCH)"

# ---------- 5) التحقق ----------
step "انتظار الموقع ($SITE_URL/health) ..."
sleep 20
ok=0
for i in $(seq 1 60); do
    body=$(curl -s --max-time 10 "$SITE_URL/health" || true)
    if echo "$body" | grep -q '"status": *"ok"'; then ok=1; break; fi
    sleep 10
done
[ "$ok" = 1 ] || die "الموقع لم يرد بـ /health خلال 10 دقائق — راجع سجل النشر في Dokploy"

step "فحص الصفحات الأساسية"
fail=0
for path in / /courses/ /articles/ /grants/ /books/ /sitemap.xml /robots.txt /feed/ /about/ /privacy/ /advertise/ /static/css/tailwind.css; do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$SITE_URL$path")
    printf '  %-28s %s\n' "$path" "$code"
    [ "$code" = "200" ] || fail=1
done
if curl -s --max-time 20 "$SITE_URL/sitemap.xml" | grep -q 'example.com'; then warn "sitemap ما زال يحتوي example.com"; fail=1; fi
[ "$fail" = 0 ] || die "بعض الصفحات لا تعمل بعد النشر"

echo -e "\n${c_green}✓ تم النشر بنجاح: $SITE_URL  (commit ${SHA:0:7})${c_off}"
