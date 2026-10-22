"""
نسخة احتياطية خام لكل جداول قاعدة البيانات (CSV داخل tar.gz) — لا تعتمد على الموديلات،
فتعمل قبل migrate حتى لو تغيّرت الأعمدة، وتعمل مع أي إصدار PostgreSQL (بدون pg_dump).

    python scripts/backup_db.py /s3files/backups [--keep 10]

الاسترجاع: كل ملف CSV فيه أسماء الأعمدة في أول سطر → \\copy <table> FROM 'file.csv' CSV HEADER
"""
import io
import os
import sys
import tarfile
import time

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kunooz.settings')
django.setup()

from django.db import connection  # noqa: E402

SKIP = {'django_session', 'analytics_realtimevisitor'}  # بيانات مؤقتة


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else 'backups'
    keep = int(sys.argv[sys.argv.index('--keep') + 1]) if '--keep' in sys.argv else 10
    os.makedirs(out_dir, exist_ok=True)
    stamp = time.strftime('%Y%m%d-%H%M%S')
    path = os.path.join(out_dir, f'db-{stamp}.tar.gz')
    tables = sorted(t for t in connection.introspection.table_names() if t not in SKIP)
    rows_total = 0
    with tarfile.open(path, 'w:gz') as tar, connection.cursor() as cur:
        for table in tables:
            buf = io.BytesIO()
            if connection.vendor == 'postgresql':
                raw = cur.cursor  # psycopg2
                raw.copy_expert(f'COPY "{table}" TO STDOUT WITH CSV HEADER', buf)
            else:
                import csv
                cur.execute(f'SELECT * FROM "{table}"')
                text = io.StringIO()
                w = csv.writer(text)
                w.writerow([c[0] for c in cur.description])
                w.writerows(cur.fetchall())
                buf.write(text.getvalue().encode('utf-8'))
            data = buf.getvalue()
            rows_total += max(data.count(b'\n') - 1, 0)
            info = tarfile.TarInfo(f'{table}.csv')
            info.size = len(data)
            info.mtime = int(time.time())
            tar.addfile(info, io.BytesIO(data))
    print(f'backup: {path} ({len(tables)} tables, ~{rows_total} rows, {os.path.getsize(path)} bytes)')

    old = sorted(f for f in os.listdir(out_dir) if f.startswith('db-') and f.endswith('.tar.gz'))
    for f in old[:-keep]:
        os.remove(os.path.join(out_dir, f))


if __name__ == '__main__':
    main()
