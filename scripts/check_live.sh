#!/usr/bin/env bash
# فحص الموقع المنشور (قراءة فقط):  ./scripts/check_live.sh [https://kunooz.deplois.net]
set -uo pipefail
SITE_URL="${1:-${SITE_URL:-https://kunooz.deplois.net}}"
fail=0
echo "health: $(curl -s --max-time 15 "$SITE_URL/health")"
for path in / /courses/ /articles/ /grants/ /books/ /search/?q=a /sitemap.xml /robots.txt /feed/ \
            /about/ /privacy/ /advertise/ /ads.txt /static/css/tailwind.css /static/vendor/jodit/jodit.min.js; do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$SITE_URL$path")
    printf '%-38s %s\n' "$path" "$code"
    [ "$code" = "200" ] || fail=1
done
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$SITE_URL/this-page-does-not-exist-404/")
printf '%-38s %s (المتوقع 404)\n' "/this-page-does-not-exist-404/" "$code"
[ "$code" = "404" ] || fail=1
if curl -s --max-time 20 "$SITE_URL/this-page-does-not-exist-404/" | grep -qi 'Traceback\|DEBUG = True\|Using the URLconf'; then
    echo "!! صفحة الخطأ تكشف معلومات DEBUG"; fail=1
fi
if curl -s --max-time 20 "$SITE_URL/sitemap.xml" | grep -q 'example.com'; then echo "!! sitemap يحتوي example.com"; fail=1; fi
exit $fail
