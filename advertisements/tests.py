from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import Advertisement, AdPlacement
from .utils import clear_ad_cache


@override_settings(ALLOWED_HOSTS=['testserver'])
class AdsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('ads_admin', 'a@example.test', 'Pass-12345!')
        cls.user = User.objects.create_user('ads_user', 'u@example.test', 'Pass-12345!')
        cls.placement = AdPlacement.objects.create(name='جانبي', code='sidebar', placement_type='sidebar')
        now = timezone.now()
        cls.ad = Advertisement.objects.create(
            title='<script>x</script>', placement=cls.placement, ad_type='text', link='https://example.test/',
            start_date=now, end_date=now + timedelta(days=1),
        )
        # إعلان بدأ بالفعل (كان أي حفظ له يرمي ValidationError)
        Advertisement.objects.filter(pk=cls.ad.pk).update(start_date=now - timedelta(days=1))
        cls.ad.refresh_from_db()

    def test_management_pages_redirect_staff_to_admin(self):
        self.client.force_login(self.admin)
        for url, target in [('/ads/dashboard/', '/admin/advertisements/advertisement/'),
                            ('/ads/create/', '/admin/advertisements/advertisement/add/'),
                            (f'/ads/edit/{self.ad.id}/', f'/admin/advertisements/advertisement/{self.ad.id}/change/'),
                            ('/ads/placements/', '/admin/advertisements/adplacement/')]:
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 302)
                self.assertEqual(resp['Location'], target)
        self.assertEqual(self.client.get('/admin/advertisements/advertisement/').status_code, 200)

    def test_regular_user_blocked(self):
        self.client.force_login(self.user)
        resp = self.client.get('/ads/dashboard/')
        self.assertNotEqual(resp.get('Location', ''), '/admin/advertisements/advertisement/')
        self.client.post(f'/ads/toggle/{self.ad.id}/')
        self.ad.refresh_from_db()
        self.assertTrue(self.ad.active)

    def test_destructive_actions_require_post(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(f'/ads/delete/{self.ad.id}/').status_code, 405)
        self.assertEqual(self.client.get(f'/ads/toggle/{self.ad.id}/').status_code, 405)
        self.client.post(f'/ads/toggle/{self.ad.id}/')
        self.ad.refresh_from_db()
        self.assertFalse(self.ad.active)

    def test_render_escapes_title_and_cache_clears(self):
        from core.models import SiteSettings
        cache.clear()
        SiteSettings.objects.create(ads_enabled=True)
        body = self.client.get('/ads/render/sidebar/').content.decode()
        self.assertIn('data-ad-id', body)
        self.assertNotIn('<script>x</script>', body)
        self.assertIsNotNone(cache.get('kz_ad_slots'))
        clear_ad_cache()  # كانت ترمي AttributeError (cache.keys)
        self.assertIsNone(cache.get('kz_ad_slots'))

    def test_running_ad_records_impressions_and_clicks(self):
        self.client.get(f'/ads/impression/{self.ad.id}/')
        resp = self.client.get(f'/ads/click/{self.ad.id}/')
        self.assertTrue(resp['Location'].startswith('https://example.test/'))
        self.ad.refresh_from_db()
        self.assertEqual((self.ad.impressions, self.ad.clicks), (1, 1))

    def test_json_feed_bad_count(self):
        self.assertEqual(self.client.get('/ads/api/feed/?count=abc').status_code, 200)


@override_settings(ALLOWED_HOSTS=['testserver'])
class AdSlotsAndReadinessTests(TestCase):
    """الأماكن داخل الصفحات، التفعيل/المعاينة، حساب الظهور اليومي، وتقرير الجاهزية."""

    @classmethod
    def setUpTestData(cls):
        from core.models import Category, Post, SiteSettings
        cls.admin = User.objects.create_superuser('ads_admin2', 'a2@example.test', 'Pass-12345!')
        cls.site = SiteSettings.objects.create(contact_email='team@kunooz.test')
        cat = Category.objects.create(name='مقالات', category_type='articles')
        cls.post = Post.objects.create(title='منشور', category=cat, author=cls.admin, content='<p>نص</p>',
                                       status=Post.Status.PUBLISHED)
        cls.placement = AdPlacement.objects.get(code='post_bottom')  # من migration الأماكن الافتراضية
        now = timezone.now()
        cls.ad = Advertisement.objects.create(
            title='كورس مدفوع', placement=cls.placement, ad_type='text', text_content='سجل الآن',
            link='https://advertiser.test/', start_date=now, end_date=now + timedelta(days=10))

    def setUp(self):
        cache.clear()

    def test_default_placements_created(self):
        codes = set(AdPlacement.objects.values_list('code', flat=True))
        self.assertTrue({'header_banner', 'post_top', 'post_bottom', 'list_between', 'footer_banner'} <= codes)

    def test_ads_hidden_until_enabled(self):
        body = self.client.get(self.post.get_absolute_url()).content.decode()
        self.assertNotIn('كورس مدفوع', body)
        self.site.ads_enabled = True
        self.site.save()
        body = self.client.get(self.post.get_absolute_url()).content.decode()
        self.assertIn('كورس مدفوع', body)
        self.assertIn('rel="sponsored noopener nofollow"', body)
        self.assertIn('>إعلان<', body)

    def test_staff_preview_shows_slots_without_enabling(self):
        self.client.force_login(self.admin)
        body = self.client.get('/?ads_preview=1').content.decode()
        self.assertIn('kz-ad-preview', body)
        self.assertIn('header_banner', body)
        self.assertNotIn('kz-ad-preview', self.client.get('/').content.decode())

    def test_impressions_counted_daily_bots_and_staff_ignored(self):
        from .models import AdDailyStat
        self.client.post(f'/ads/impression/{self.ad.id}/', HTTP_USER_AGENT='Mozilla/5.0 Chrome/120')
        self.client.post(f'/ads/impression/{self.ad.id}/', HTTP_USER_AGENT='Googlebot/2.1')
        self.client.get(f'/ads/click/{self.ad.id}/', HTTP_USER_AGENT='Mozilla/5.0 Chrome/120')
        self.client.force_login(self.admin)
        self.client.post(f'/ads/impression/{self.ad.id}/', HTTP_USER_AGENT='Mozilla/5.0 Chrome/120')
        stat = AdDailyStat.objects.get(ad=self.ad)
        self.assertEqual((stat.impressions, stat.clicks), (1, 1))
        self.ad.refresh_from_db()
        self.assertEqual((self.ad.impressions, self.ad.clicks), (1, 1))

    def test_report_readiness_and_csv(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/ads/report/')
        self.assertEqual(resp.status_code, 200)
        verdict = resp.context['readiness']['verdict'][0]
        self.assertEqual(verdict, 'fail')  # منشور واحد فقط → محتوى غير كافٍ
        self.assertContains(resp, 'كمية المحتوى المنشور')
        csv_resp = self.client.get(f'/ads/report/{self.ad.id}.csv')
        self.assertEqual(csv_resp.status_code, 200)
        self.assertIn('مرات الظهور', csv_resp.content.decode('utf-8-sig'))
        self.client.logout()
        self.assertEqual(self.client.get('/ads/report/').status_code, 302)

    def test_public_pages_and_ads_txt(self):
        for url in ['/about/', '/privacy/', '/advertise/']:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        self.assertContains(self.client.get('/advertise/'), 'نهاية المنشور')
        self.site.ads_txt = 'google.com, pub-0000000000000000, DIRECT, f08c47fec0942fa0'
        self.site.save()
        resp = self.client.get('/ads.txt')
        self.assertEqual(resp['Content-Type'], 'text/plain; charset=utf-8')
        self.assertContains(resp, 'pub-0000000000000000')

    def test_adsense_script_only_when_enabled(self):
        self.site.adsense_client = 'ca-pub-0000000000000000'
        self.site.save()
        self.assertNotContains(self.client.get('/'), 'adsbygoogle.js')
        self.site.ads_enabled = True
        self.site.save()
        self.assertContains(self.client.get('/'), 'adsbygoogle.js?client=ca-pub-0000000000000000')
