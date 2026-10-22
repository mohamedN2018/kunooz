"""
حد بسيط لعدد المحاولات (تسجيل الدخول/التعليقات/التسجيل) باستخدام cache Django — بدون مكتبات إضافية.

ملاحظة: الـ cache الافتراضي LocMemCache لكل عملية gunicorn؛ الحد إذن تقريبي (× عدد العمال)
لكنه يوقف التخمين الآلي. لحد دقيق عبر العمال اضبط CACHES على Redis (موجود في requirements).
"""
import hashlib

from django.core.cache import cache


def client_ip(request):
    # خلف reverse proxy (Traefik في Dokploy) العنوان الحقيقي أول قيمة في X-Forwarded-For
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def _key(scope, ident):
    return 'rl:%s:%s' % (scope, hashlib.sha256(str(ident).encode()).hexdigest()[:32])


def is_limited(scope, ident, limit):
    return (cache.get(_key(scope, ident)) or 0) >= limit


def hit(scope, ident, window):
    key = _key(scope, ident)
    if cache.add(key, 1, window):
        return 1
    try:
        return cache.incr(key)
    except ValueError:  # انتهت صلاحية المفتاح بين add و incr
        cache.set(key, 1, window)
        return 1


def reset(scope, ident):
    cache.delete(_key(scope, ident))
