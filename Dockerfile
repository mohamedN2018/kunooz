# Kunooz — صورة الإنتاج (Dokploy / docker compose)
FROM python:3.11.3-alpine

WORKDIR /usr/src/app

ENV TZ=Africa/Cairo \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# مكتبات psycopg2 و Pillow، و pg_isready لانتظار قاعدة البيانات
RUN apk add --no-cache \
    build-base gcc python3-dev musl-dev libffi-dev openssl-dev \
    tzdata postgresql-dev postgresql-client \
    jpeg-dev zlib-dev libwebp-dev

RUN pip3 install --upgrade pip pipenv

# المتطلبات أولاً (طبقة مخزنة؛ لا يُعاد التثبيت إلا عند تغيّر Pipfile.lock)
COPY Pipfile Pipfile.lock ./
RUN pipenv requirements > /tmp/requirements.txt \
    && pip3 install -r /tmp/requirements.txt

COPY . .

# ملفات static تُجمع وقت البناء وتُخدم عبر WhiteNoise.
# الصور الموجودة في git تُحفظ في media-seed لأن media/ يُغطى بالـ volume الدائم وقت التشغيل.
RUN MY_SECRET_KEY=build-only-not-a-secret LOCAL=True DEBUG=False \
        python manage.py collectstatic --noinput --verbosity 0 \
    && cp -a media media-seed \
    && sed -i 's/\r$//' scripts/*.sh \
    && chmod +x scripts/*.sh \
    && mkdir -p /s3files

EXPOSE 80

ENTRYPOINT ["/usr/src/app/scripts/entrypoint.sh"]
CMD ["gunicorn", "--chdir", "/usr/src/app", "--access-logfile", "-", "--error-logfile", "-", "--bind", "0.0.0.0:80", "kunooz.wsgi:application"]
