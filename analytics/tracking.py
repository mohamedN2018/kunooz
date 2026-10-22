"""
نقاط استقبال إشارات المتصفح: نبض كل 30 ثانية أثناء فتح الصفحة، وإشارة عند المغادرة (sendBeacon).
بها نعرف من "متصل الآن" بدقة ومتى "خرج" ومدة بقائه الفعلية في الصفحة.
"""
import uuid
from datetime import timedelta

from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .middleware import close_session
from .models import PageView, RealTimeVisitor, VisitorSession


def _session(request):
    sid = request.session.get('analytics_sid')
    if not sid:
        return None
    try:
        return VisitorSession.objects.filter(session_id=uuid.UUID(sid)).first()
    except ValueError:
        return None


# csrf_exempt: sendBeacon لا يرسل ترويسات CSRF؛ النقطة لا تغيّر إلا جلسة الزائر نفسه (من كوكي الجلسة)
@csrf_exempt
@require_POST
def ping(request):
    session = _session(request)
    if session:
        now = timezone.now()
        VisitorSession.objects.filter(pk=session.pk).update(last_seen=now, is_active=True, end_time=None)
        RealTimeVisitor.objects.filter(session=session).update(last_activity=now)
        request.session['analytics_last'] = now.timestamp()
    return HttpResponse(status=204)


@csrf_exempt
@require_POST
def leave(request):
    session = _session(request)
    if session:
        # مدة الصفحة الأخيرة الفعلية (قبلها كانت تُحسب فقط عند فتح صفحة تالية)
        last = PageView.objects.filter(session=session).order_by('-timestamp').first()
        if last and last.time_spent.total_seconds() == 0:
            spent = min(timezone.now() - last.timestamp, timedelta(hours=2))
            PageView.objects.filter(pk=last.pk).update(time_spent=spent, is_bounce=session.page_count <= 1)
        close_session(session.session_id)
    return HttpResponse(status=204)
