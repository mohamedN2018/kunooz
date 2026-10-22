from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import RealTimeVisitor, VisitorSession

UA = 'Mozilla/5.0 (Windows NT 10.0) Chrome/120'


@override_settings(ALLOWED_HOSTS=['testserver'])
class VisitorFlowTests(TestCase):
    """الدخول، الخروج، المتصلون الآن، الزوار الفريدون والعائدون، ولوحة حركة الزوار."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('an_admin', 'an@example.test', 'Pass-12345!')

    def visit(self, path='/', **extra):
        return self.client.get(path, HTTP_USER_AGENT=UA, **extra)

    def test_entry_sets_visitor_cookie_source_and_last_seen(self):
        resp = self.visit('/', HTTP_REFERER='https://www.google.com/search?q=kunooz')
        self.assertIn('kz_vid', resp.cookies)
        s = VisitorSession.objects.get()
        self.assertEqual(s.entry_source, 'search')
        self.assertIsNotNone(s.visitor_id)
        self.assertIsNotNone(s.last_seen)
        self.assertFalse(s.is_returning)
        self.visit('/articles/', HTTP_REFERER='http://testserver/')  # تنقل داخلي ليس مصدراً
        s.refresh_from_db()
        self.assertEqual(s.page_count, 2)
        self.assertTrue(s.exit_page.endswith('/articles/'))

    def test_leave_beacon_closes_session_and_return_visit_is_returning(self):
        self.visit('/')
        self.client.post('/t/leave/', HTTP_USER_AGENT=UA)
        s = VisitorSession.objects.get()
        self.assertFalse(s.is_active)
        self.assertIsNotNone(s.end_time)
        self.assertFalse(RealTimeVisitor.objects.exists())
        # بعد 30 دقيقة خمول: زيارة جديدة لنفس المتصفح = زائر عائد
        session = self.client.session
        session['analytics_last'] = (timezone.now() - timedelta(minutes=31)).timestamp()
        session.save()
        self.visit('/')
        self.assertEqual(VisitorSession.objects.count(), 2)
        latest = VisitorSession.objects.order_by('-start_time').first()
        self.assertTrue(latest.is_returning)
        self.assertEqual(VisitorSession.objects.values('visitor_id').distinct().count(), 1)

    def test_refresh_after_leave_resumes_same_session(self):
        self.visit('/')
        self.client.post('/t/leave/', HTTP_USER_AGENT=UA)
        self.visit('/')  # تحديث الصفحة
        self.assertEqual(VisitorSession.objects.count(), 1)
        self.assertTrue(VisitorSession.objects.get().is_active)

    def test_ping_keeps_online_and_stale_sessions_close(self):
        from .reports import close_stale_sessions, online_now
        self.visit('/')
        s = VisitorSession.objects.get()
        self.assertEqual(online_now().count(), 1)
        old = timezone.now() - timedelta(minutes=40)
        VisitorSession.objects.filter(pk=s.pk).update(last_seen=old)
        self.assertEqual(online_now().count(), 0)
        close_stale_sessions()
        s.refresh_from_db()
        self.assertFalse(s.is_active)
        self.assertEqual(s.end_time, old)  # وقت الخروج = آخر نشاط
        self.assertEqual(self.client.post('/t/ping/').status_code, 204)

    def test_dashboard_numbers(self):
        self.visit('/')
        self.visit('/articles/')
        self.client.post('/t/leave/', HTTP_USER_AGENT=UA)
        other = self.client_class()
        other.get('/', HTTP_USER_AGENT=UA)
        self.client.force_login(self.admin)
        resp = self.client.get('/analytics/dashboard/?range=today')
        self.assertEqual(resp.status_code, 200)
        k = resp.context['kpis']
        self.assertEqual(k['sessions'], 2)
        self.assertEqual(k['unique'], 2)
        self.assertEqual(k['exits'], 1)
        self.assertEqual(k['online'], 1)
        self.assertEqual(k['pageviews'], 3)
        self.assertEqual(sum(resp.context['chart']['entries']), 2)
        self.assertEqual(sum(resp.context['chart']['exits']), 1)
        for url in ['/analytics/visitors/', '/analytics/visitors/?status=online', '/analytics/live.json',
                    '/analytics/dashboard/advanced/', '/analytics/dashboard/?range=90d']:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get('/analytics/live.json').json()['online_count'], 1)

    def test_dashboard_staff_only(self):
        self.assertEqual(self.client.get('/analytics/dashboard/').status_code, 302)
        self.assertEqual(self.client.get('/analytics/live.json').status_code, 302)

    def test_bots_tools_staff_and_404s_not_counted(self):
        for ua in ['curl/8.4.0', 'python-requests/2.31', 'Mozilla/5.0 HeadlessChrome/120', '']:
            self.client.get('/', HTTP_USER_AGENT=ua)
        self.visit('/v1/models/')      # فحص آلي لمسار غير موجود
        self.client.force_login(self.admin)
        self.visit('/')                # المشرف
        self.assertEqual(VisitorSession.objects.count(), 0)

    def test_cloudflare_country_header(self):
        self.visit('/', HTTP_CF_IPCOUNTRY='EG')
        self.assertEqual(VisitorSession.objects.get().country.name, 'مصر')
