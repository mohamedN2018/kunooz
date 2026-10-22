from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from analytics.models import VisitorSession
from .models import Category, Comment, Post, sanitize_html


class BaseDataMixin:
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('admin_t', 'admin@example.test', 'Pass-12345!')
        cls.user = User.objects.create_user('user_t', 'user@example.test', 'Pass-12345!')
        cls.cats = {t: Category.objects.create(name=label, category_type=t) for t, label in Category.CATEGORY_TYPES}
        cls.published = Post.objects.create(
            title='منشور منشور', category=cls.cats['articles'], author=cls.admin,
            content='<p>نص</p>', status=Post.Status.PUBLISHED,
        )
        cls.draft = Post.objects.create(
            title='مسودة سرية', category=cls.cats['articles'], author=cls.admin,
            content='<p>سري</p>', status=Post.Status.DRAFT,
        )


@override_settings(ALLOWED_HOSTS=['testserver'], SECURE_SSL_REDIRECT=False)
class PublicPagesTests(BaseDataMixin, TestCase):
    def test_public_pages_ok(self):
        for url in ['/', '/courses/', '/articles/', '/grants/', '/books/', '/search/?q=منشور',
                    '/login/', '/sitemap.xml', '/robots.txt', self.published.get_absolute_url()]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_custom_404_page(self):
        resp = self.client.get('/no-such-page/')
        self.assertEqual(resp.status_code, 404)
        self.assertContains(resp, 'الصفحة غير موجودة', status_code=404)

    def test_post_without_image_renders(self):
        # كانت صفحة المنشور تُرجع 500 إذا لم تكن له صورة
        self.assertFalse(self.published.get_main_image)
        self.assertEqual(self.client.get(self.published.get_absolute_url()).status_code, 200)

    def test_section_pages_without_category_do_not_404(self):
        Category.objects.filter(category_type='grants').delete()
        self.assertEqual(self.client.get('/grants/').status_code, 200)

    def test_section_pages_with_duplicate_categories_do_not_500(self):
        Category.objects.create(name='مقالات 2', category_type='articles')
        self.assertEqual(self.client.get('/articles/').status_code, 200)

    def test_courses_invalid_category_filter(self):
        self.assertEqual(self.client.get('/courses/?category=abc').status_code, 200)

    def test_draft_not_public(self):
        self.assertEqual(self.client.get(self.draft.get_absolute_url()).status_code, 404)
        search = self.client.get('/search/', {'q': 'سرية'})
        self.assertNotContains(search, 'مسودة سرية')
        auto = self.client.get('/autocomplete_search/', {'term': 'سرية'})
        self.assertNotContains(auto, 'مسودة سرية')

    def test_sitemap_uses_real_domain_and_only_published(self):
        with self.settings(MAIN_DOMAIN='kunooz.deplois.net'):
            body = self.client.get('/sitemap.xml').content.decode()
        self.assertIn('https://kunooz.deplois.net/', body)
        self.assertNotIn('example.com', body)
        self.assertNotIn(self.draft.slug, body)

    def test_robots_blocks_private_areas(self):
        body = self.client.get('/robots.txt').content.decode()
        self.assertIn('Disallow: /admin/', body)
        self.assertIn('Sitemap:', body)

    def test_home_counts_are_real(self):
        for i in range(8):
            Post.objects.create(title=f'كورس {i}', category=self.cats['courses'], author=self.admin,
                                content='x', status=Post.Status.PUBLISHED)
        resp = self.client.get('/')
        self.assertEqual(resp.context['section_counts']['courses'], 8)
        self.assertEqual(len(resp.context['courses_posts']), 6)


class SanitizeTests(BaseDataMixin, TestCase):
    def test_script_and_handlers_removed(self):
        dirty = '<p onclick="alert(1)">hi</p><script>alert(1)</script><a href="javascript:alert(1)">x</a>'
        clean = sanitize_html(dirty)
        self.assertNotIn('<script', clean)
        self.assertNotIn('onclick', clean)
        self.assertNotIn('javascript:', clean)
        self.assertIn('<p>hi</p>', clean)

    def test_formatting_and_trusted_embed_kept(self):
        html = ('<h2 dir="rtl">عنوان</h2><table><tr><td>1</td></tr></table>'
                '<iframe src="https://www.youtube.com/embed/abc"></iframe><iframe src="https://evil.test/x"></iframe>')
        clean = sanitize_html(html)
        self.assertIn('<h2 dir="rtl">', clean)
        self.assertIn('<td>1</td>', clean)
        self.assertIn('youtube.com/embed/abc', clean)
        self.assertNotIn('evil.test', clean)

    @override_settings(ALLOWED_HOSTS=['testserver'])
    def test_post_saved_and_rendered_clean(self):
        p = Post.objects.create(title='xss', category=self.cats['articles'], author=self.admin,
                                content='<img src=x onerror=alert(1)>', status=Post.Status.PUBLISHED)
        self.assertNotIn('onerror', p.content)
        # محتوى قديم أُدخل قبل التنظيف (update يتجاوز save)
        Post.objects.filter(pk=p.pk).update(content='<script>alert(1)</script><p>ok</p>')
        resp = self.client.get(p.get_absolute_url())
        self.assertNotContains(resp, '<script>alert(1)</script>')


@override_settings(ALLOWED_HOSTS=['testserver'])
class AuthAndPermissionTests(BaseDataMixin, TestCase):
    def test_login_rejects_external_next(self):
        resp = self.client.post('/login/?next=https://evil.example/', {'username': 'user_t', 'password': 'Pass-12345!'})
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn('evil.example', resp['Location'])

    def test_login_allows_local_next(self):
        resp = self.client.post('/login/?next=/profile/', {'username': 'user_t', 'password': 'Pass-12345!'})
        self.assertEqual(resp['Location'], '/profile/')

    def test_analytics_staff_only(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/analytics/dashboard/').status_code, 302)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get('/analytics/dashboard/').status_code, 200)

    def test_admin_pages_render(self):
        Comment.objects.create(post=self.published, name='زائر', email='v@example.test', content='تعليق')
        self.client.force_login(self.admin)
        for url in ['/dashboard/', '/profile/', '/my-posts/', '/my-posts/comments/', '/create-post/',
                    f'/edit-post/{self.published.id}/', '/content/dashboard/', '/staff/dashboard/', '/staff/posts/',
                    '/control/dashboard/', '/control/settings/', '/control/users/', '/control/logs/',
                    '/control/comments/', '/analytics/dashboard/', '/analytics/dashboard/simple/',
                    '/analytics/countries/', '/analytics/time/', '/analytics/pages/', '/analytics/devices/',
                    '/analytics/realtime/', '/analytics/export/csv/', '/admin/']:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_comment_moderation_flow(self):
        c = Comment.objects.create(post=self.published, name='زائر', email='v@example.test', content='تعليق')
        self.client.force_login(self.admin)
        resp = self.client.post(f'/control/comments/approve/{c.id}/')
        self.assertEqual(resp.status_code, 302)
        c.refresh_from_db()
        self.assertTrue(c.is_approved)

    def test_regular_user_cannot_create_post(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/create-post/').status_code, 302)


@override_settings(ALLOWED_HOSTS=['testserver'])
class PublishingWorkflowTests(BaseDataMixin, TestCase):
    def _scheduled(self):
        from datetime import timedelta
        from django.utils import timezone
        return Post.objects.create(title='منشور مجدول', category=self.cats['articles'], author=self.admin,
                                   content='x', status=Post.Status.PUBLISHED,
                                   publish_date=timezone.now() + timedelta(days=2))

    def test_scheduled_post_hidden_until_date(self):
        p = self._scheduled()
        self.assertTrue(p.is_scheduled)
        self.assertEqual(self.client.get(p.get_absolute_url()).status_code, 404)
        self.assertNotContains(self.client.get('/articles/'), 'منشور مجدول')
        self.assertNotIn(p.slug, self.client.get('/sitemap.xml').content.decode())
        # عند حلول التاريخ يظهر تلقائياً
        from django.utils import timezone
        Post.objects.filter(pk=p.pk).update(publish_date=timezone.now())
        self.assertEqual(self.client.get(p.get_absolute_url()).status_code, 200)

    def test_preview_access_control(self):
        url = f'/preview-post/{self.draft.id}/'
        self.assertEqual(self.client.get(url).status_code, 302)  # زائر → تسجيل الدخول
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(url).status_code, 403)  # مستخدم عادي
        self.client.force_login(self.admin)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['X-Robots-Tag'], 'noindex, nofollow')
        self.assertContains(resp, 'مسودة سرية')

    def test_editor_can_create_and_publish(self):
        self.user.profile.is_content_editor = True
        self.user.profile.save()
        self.client.force_login(self.user)
        resp = self.client.post('/create-post/', {
            'title': 'منشور جديد من محرر', 'category': self.cats['books'].id, 'content': '<p>محتوى</p><script>x</script>',
            'status': 'draft', 'link_delay': 30, 'publish_now': '1',
        })
        self.assertEqual(resp.status_code, 302)
        p = Post.objects.get(title='منشور جديد من محرر')
        self.assertEqual(p.status, Post.Status.PUBLISHED)
        self.assertEqual(p.author, self.user)
        self.assertNotIn('<script', p.content)
        self.assertEqual(self.client.get(p.get_absolute_url()).status_code, 200)


@override_settings(ALLOWED_HOSTS=['testserver'])
class AnalyticsTrackingTests(BaseDataMixin, TestCase):
    def test_visit_is_recorded_and_ip_anonymized(self):
        self.client.get('/', HTTP_USER_AGENT='Mozilla/5.0 (Windows NT 10.0) Chrome/120', REMOTE_ADDR='203.0.113.57')
        self.client.get('/articles/', HTTP_USER_AGENT='Mozilla/5.0 (Windows NT 10.0) Chrome/120', REMOTE_ADDR='203.0.113.57')
        self.assertEqual(VisitorSession.objects.count(), 1)
        s = VisitorSession.objects.get()
        self.assertEqual(s.ip_address, '203.0.113.0')
        self.assertEqual(s.pageviews.count(), 2)
        self.assertEqual(s.page_count, 2)

    def test_bots_not_tracked(self):
        self.client.get('/', HTTP_USER_AGENT='Googlebot/2.1 (+http://www.google.com/bot.html)')
        self.assertEqual(VisitorSession.objects.count(), 0)

@override_settings(ALLOWED_HOSTS=['testserver'])
class NewPublishingFeaturesTests(BaseDataMixin, TestCase):
    def _editor(self):
        self.user.profile.is_content_editor = True
        self.user.profile.save()
        return self.user

    def _form(self, **extra):
        data = {'title': 'منشور بوسوم', 'category': self.cats['grants'].id, 'content': '<p>نص</p>',
                'status': 'draft', 'link_delay': 30}
        data.update(extra)
        return data

    def test_tags_saved_shown_and_listed(self):
        self.client.force_login(self.admin)
        self.client.post('/create-post/', self._form(tags_input='منح ممولة، بايثون, منح ممولة', publish_now='1'))
        p = Post.objects.get(title='منشور بوسوم')
        self.assertEqual(sorted(p.tags.values_list('name', flat=True)), ['بايثون', 'منح ممولة'])
        tag = p.tags.get(name='بايثون')
        self.assertContains(self.client.get(p.get_absolute_url()), tag.get_absolute_url())
        self.assertContains(self.client.get(tag.get_absolute_url()), 'منشور بوسوم')
        self.assertContains(self.client.get('/search/', {'q': 'بايثون'}), 'منشور بوسوم')

    def test_tag_page_hides_drafts(self):
        from .models import Tag
        tag = Tag.objects.create(name='سري')
        self.draft.tags.add(tag)
        self.assertNotContains(self.client.get(tag.get_absolute_url()), 'مسودة سرية')

    def test_revision_created_on_edit_and_restorable(self):
        self.client.force_login(self.admin)
        url = f'/edit-post/{self.published.id}/'
        self.client.post(url, self._form(title='عنوان جديد', category=self.cats['articles'].id, publish_now='1'))
        self.published.refresh_from_db()
        self.assertEqual(self.published.title, 'عنوان جديد')
        rev = self.published.revisions.get()
        self.assertEqual(rev.title, 'منشور منشور')
        self.assertContains(self.client.get(url), 'النسخ السابقة')
        # GET لا يسترجع
        self.assertEqual(self.client.get(f'{url}restore/{rev.id}/').status_code, 403)
        self.client.post(f'{url}restore/{rev.id}/')
        self.published.refresh_from_db()
        self.assertEqual(self.published.title, 'منشور منشور')
        self.assertEqual(self.published.revisions.count(), 2)  # الحالة قبل الاسترجاع محفوظة أيضاً

    def test_regular_user_cannot_restore(self):
        from .models import PostRevision
        rev = PostRevision.snapshot(self.published)
        self.client.force_login(self.user)
        self.client.post(f'/edit-post/{self.published.id}/restore/{rev.id}/')
        self.published.refresh_from_db()
        self.assertEqual(self.published.title, 'منشور منشور')

    def test_review_workflow(self):
        self._editor()
        self.client.force_login(self.user)
        self.client.post('/create-post/', self._form(submit_review='1'))
        p = Post.objects.get(title='منشور بوسوم')
        self.assertEqual(p.status, Post.Status.REVIEW)
        self.assertEqual(self.client.get(p.get_absolute_url()).status_code, 404)
        # المستخدم غير الـ staff لا يدخل قائمة المراجعة ولا يعتمد
        self.assertEqual(self.client.get('/staff/review/').status_code, 302)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get('/staff/review/'), 'منشور بوسوم')
        self.assertEqual(self.client.get(f'/staff/review/{p.id}/publish/').status_code, 403)
        self.client.post(f'/staff/review/{p.id}/publish/')
        p.refresh_from_db()
        self.assertEqual(p.status, Post.Status.PUBLISHED)
        self.assertEqual(self.client.get(p.get_absolute_url()).status_code, 200)

    def test_require_review_setting_blocks_direct_publish(self):
        self._editor()
        self.client.force_login(self.user)
        with self.settings(REQUIRE_EDITOR_REVIEW=True):
            self.client.post('/create-post/', self._form(publish_now='1'))
        self.assertEqual(Post.objects.get(title='منشور بوسوم').status, Post.Status.REVIEW)

    def test_grant_deadline_display_and_sort(self):
        from datetime import timedelta
        from django.utils import timezone
        today = timezone.localdate()

        def mk(title, deadline):
            return Post.objects.create(title=title, category=self.cats['grants'], author=self.admin,
                                       content='x', status=Post.Status.PUBLISHED, deadline=deadline)
        late = mk('منحة بعيدة', today + timedelta(days=60))
        soon = mk('منحة قريبة', today + timedelta(days=3))
        mk('منحة منتهية', today - timedelta(days=1))
        resp = self.client.get('/grants/?sort=deadline')
        titles = [p.title for p in resp.context['posts']]
        self.assertLess(titles.index('منحة قريبة'), titles.index('منحة بعيدة'))
        self.assertEqual(titles[-1], 'منحة منتهية')
        self.assertEqual(resp.context['upcoming_deadlines'], 1)
        self.assertContains(self.client.get(soon.get_absolute_url()), 'آخر موعد للتقديم')
        self.assertContains(self.client.get(late.get_absolute_url()), 'متبقٍ 60 يوم')

    def test_editor_image_upload(self):
        import io, shutil, tempfile
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        buf = io.BytesIO()
        Image.new('RGB', (50, 40), 'red').save(buf, 'PNG')
        png = lambda: SimpleUploadedFile('a.png', buf.getvalue(), content_type='image/png')
        with self.settings(MEDIA_ROOT=tmp):
            # مستخدم عادي ممنوع
            self.client.force_login(self.user)
            self.assertEqual(self.client.post('/editor/upload-image/', {'files[0]': png()}).status_code, 403)
            self.client.force_login(self.admin)
            self.assertEqual(self.client.get('/editor/upload-image/').status_code, 405)
            resp = self.client.post('/editor/upload-image/', {'files[0]': png()})
            data = resp.json()
            self.assertTrue(data['success'])
            self.assertTrue(data['data']['files'][0].startswith('/media/posts/content/'))
            self.assertTrue(data['data']['files'][0].endswith('.png'))
            # ملف ليس صورة بامتداد صورة
            fake = SimpleUploadedFile('x.jpg', b'<?php echo 1; ?>', content_type='image/jpeg')
            resp = self.client.post('/editor/upload-image/', {'files[0]': fake})
            self.assertEqual(resp.status_code, 400)
            self.assertFalse(resp.json()['success'])

    def test_create_page_uses_local_editor_not_ckeditor_cdn(self):
        self.client.force_login(self.admin)
        body = self.client.get('/create-post/').content.decode()
        self.assertIn('vendor/jodit/jodit.min.js', body)
        self.assertIn('data-rich-editor', body)
        self.assertNotIn('cdn.ckeditor.com', body)

    def test_health_feed_and_jsonld(self):
        import json, re
        self.assertEqual(self.client.get('/health').json()['status'], 'ok')
        feed = self.client.get('/feed/').content.decode()
        self.assertIn('منشور منشور', feed)
        self.assertNotIn('مسودة سرية', feed)
        self.assertNotIn('example.com', feed)
        self.assertEqual(self.client.get('/feed/grants/').status_code, 200)
        Post.objects.filter(pk=self.published.pk).update(title='عنوان "باقتباس" </script>')
        body = self.client.get(self.published.get_absolute_url()).content.decode()
        blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', body, re.S)
        types = [json.loads(b)['@type'] for b in blocks]  # كان JSON يتكسر مع علامات الاقتباس
        self.assertIn('Article', types)
        self.assertIn('BreadcrumbList', types)

    def test_maintenance_mode(self):
        from django.core.cache import cache
        from .models import SiteSettings
        SiteSettings.objects.create(maintenance_mode=True)
        self.assertEqual(self.client.get('/').status_code, 503)
        self.assertEqual(self.client.get('/login/').status_code, 200)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get('/').status_code, 200)
        site = SiteSettings.objects.get()
        site.maintenance_mode = False
        site.save()
        self.client.logout()
        self.assertEqual(self.client.get('/').status_code, 200)
        cache.clear()

    def test_comment_settings_honeypot_and_limit(self):
        from django.core.cache import cache
        from .models import SiteSettings
        cache.clear()
        url = self.published.get_absolute_url()
        data = {'comment_form': '1', 'name': 'زائر', 'email': 'v@example.test', 'content': 'تعليق'}
        self.client.post(url, dict(data, website='http://spam.test'))
        self.assertEqual(Comment.objects.count(), 0)  # بوت
        SiteSettings.objects.create(require_comment_approval=False)
        self.client.post(url, data)
        self.assertTrue(Comment.objects.get().is_approved)
        for _ in range(12):
            self.client.post(url, data)
        self.assertEqual(Comment.objects.count(), 10)  # حد 10 في الساعة
        SiteSettings.objects.update(allow_comments=False)
        self.client.post(url, dict(data, content='بعد الإغلاق'))
        self.assertFalse(Comment.objects.filter(content='بعد الإغلاق').exists())
        cache.clear()

    def test_login_rate_limited(self):
        from django.core.cache import cache
        cache.clear()
        for _ in range(10):
            self.client.post('/login/', {'username': 'user_t', 'password': 'wrong'})
        resp = self.client.post('/login/', {'username': 'user_t', 'password': 'Pass-12345!'})
        self.assertEqual(resp.status_code, 429)
        cache.clear()
        resp = self.client.post('/login/', {'username': 'user_t', 'password': 'Pass-12345!'})
        self.assertEqual(resp.status_code, 302)

    def test_arabic_language_and_number_format(self):
        self.assertContains(self.client.get('/admin/login/'), 'lang="ar"')
        from django.utils.formats import number_format
        self.assertEqual(number_format(12.5, 1), '12.5')
