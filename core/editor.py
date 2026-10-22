"""
محرر المحتوى: Jodit (رخصة MIT، يُخدم محلياً من static/vendor/jodit) بدل CKEditor 4 المنتهي الدعم.

- PostEditorWidget: textarea عادي يحوّله Jodit إلى محرر عربي RTL.
- upload_editor_image: رفع الصور من داخل المحرر (للمحررين فقط، صور فقط، حجم محدود، يُعاد ترميزها بـ Pillow).
المحتوى الناتج يمر دائماً بـ sanitize_html عند الحفظ والعرض، فالمحرر ليس خط الدفاع الوحيد.
"""
import os
import uuid

from django import forms
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
from PIL import Image, UnidentifiedImageError

MAX_EDITOR_IMAGE_BYTES = 5 * 1024 * 1024
MAX_EDITOR_IMAGE_SIDE = 2000
ALLOWED_IMAGE_FORMATS = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp', 'GIF': 'gif'}


class PostEditorWidget(forms.Textarea):
    """يُعرض كـ textarea عليه data-rich-editor؛ static/js/post-editor.js يفعّل Jodit عليه."""
    template_name = 'django/forms/widgets/textarea.html'

    def __init__(self, attrs=None):
        base = {'data-rich-editor': '1', 'rows': 18, 'dir': 'rtl'}
        base.update(attrs or {})
        super().__init__(base)

    class Media:
        css = {'all': ('vendor/jodit/jodit.min.css', 'css/post-editor.css')}
        js = ('vendor/jodit/jodit.min.js', 'js/post-editor.js')


def _can_upload(user):
    return user.is_staff or (hasattr(user, 'profile') and user.profile.is_content_editor)


def _error(message, status=400):
    return JsonResponse({'success': False, 'data': {'messages': [message]}}, status=status)


@login_required
@require_POST
def upload_editor_image(request):
    """
    استجابة بصيغة Jodit uploader:
    {"success": true, "data": {"baseurl": "", "files": [url], "isImages": [true]}}
    """
    if not _can_upload(request.user):
        return _error('ليس لديك صلاحية رفع الصور', 403)

    files = [f for key, f in request.FILES.items() if key.startswith('files')]
    if not files:
        return _error('لم يتم اختيار صورة')

    urls = []
    for upload in files[:10]:
        if upload.size > MAX_EDITOR_IMAGE_BYTES:
            return _error(f'حجم الصورة "{upload.name}" أكبر من 5 ميجابايت')
        try:
            image = Image.open(upload)
            image.verify()  # يرفض الملفات غير الصور حتى لو امتدادها .jpg
            upload.seek(0)
            image = Image.open(upload)
            fmt = image.format
        except (UnidentifiedImageError, OSError, SyntaxError):
            return _error(f'الملف "{upload.name}" ليس صورة صالحة')
        if fmt not in ALLOWED_IMAGE_FORMATS:
            return _error('الصيغ المسموحة: JPG, PNG, WEBP, GIF')

        ext = ALLOWED_IMAGE_FORMATS[fmt]
        if fmt == 'GIF':
            # لا نعيد ترميز GIF حتى لا تضيع الحركة؛ verify() تحقق أنه صورة حقيقية
            upload.seek(0)
            data = upload.read()
        else:
            # إعادة الترميز تزيل أي بيانات ملحقة بالملف وبيانات EXIF (مثل موقع التصوير)
            if image.mode not in ('RGB', 'RGBA', 'L'):
                image = image.convert('RGBA' if 'A' in image.getbands() else 'RGB')
            if fmt == 'JPEG' and image.mode == 'RGBA':
                image = image.convert('RGB')
            image.thumbnail((MAX_EDITOR_IMAGE_SIDE, MAX_EDITOR_IMAGE_SIDE))
            from io import BytesIO
            buf = BytesIO()
            save_kwargs = {'quality': 85, 'optimize': True} if fmt in ('JPEG', 'WEBP') else {'optimize': True}
            image.save(buf, format=fmt, **save_kwargs)
            data = buf.getvalue()

        path = os.path.join('posts', 'content', timezone.now().strftime('%Y/%m'), f'{uuid.uuid4().hex}.{ext}')
        saved = default_storage.save(path.replace(os.sep, '/'), ContentFile(data))
        urls.append(default_storage.url(saved))

    return JsonResponse({'success': True, 'data': {
        'baseurl': '', 'files': urls, 'isImages': [True] * len(urls), 'messages': [],
    }})
