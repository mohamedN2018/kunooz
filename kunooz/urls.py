# education/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.views.generic import TemplateView

from django.contrib.sitemaps.views import sitemap
from django.urls import re_path
from django.views.static import serve
from core.sitemaps import PostSitemap, StaticViewSitemap, TagSitemap
from core.views import robots_txt, health
from core.feeds import LatestPostsFeed
from analytics import tracking as analytics_tracking
from core import pages

sitemaps = {
    "static": StaticViewSitemap,
    "posts": PostSitemap,
    "tags": TagSitemap,
}

urlpatterns = [
    path('admin/', admin.site.urls),
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}),
    path("robots.txt", robots_txt, name="robots_txt"),
    path("feed/", LatestPostsFeed(), name="feed"),
    path("feed/<str:section>/", LatestPostsFeed(), name="feed_section"),
    path("ads.txt", pages.ads_txt, name="ads_txt"),
    path("about/", pages.about, name="about"),
    path("privacy/", pages.privacy, name="privacy"),
    path("advertise/", pages.advertise, name="advertise"),
    path("health", health, name="health"),
    path("health/", health),
    path("google6dc94822b91e8a80.html", TemplateView.as_view(template_name="google6dc94822b91e8a80.html", content_type="text/html")),

    # /login/ و /logout/ في core/urls.py (كانت معرّفة هنا أيضاً فتطغى على views.login_view
    # فلا يعمل حد المحاولات ولا "تذكرني" ولا رسائل الخطأ العربية)
    
    # تطبيق core
    path('', include('core.urls')),
    path('analytics/', include('analytics.urls')),
    path('t/ping/', analytics_tracking.ping, name='analytics_ping'),
    path('t/leave/', analytics_tracking.leave, name='analytics_leave'),
    path('ads/', include('advertisements.urls')),

]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# معالجات الأخطاء يجب أن تكون في الـ ROOT_URLCONF (تعريفها في core/urls.py كان يُتجاهل)
handler404 = 'core.views.handler404'
handler500 = 'core.views.handler500'
handler403 = 'core.views.handler403'
handler400 = 'core.views.handler400'

# الصور المرفوعة كانت تُخدم من Django عبر DEBUG=True؛ نحافظ على ذلك بعد إيقاف DEBUG
if settings.DEBUG or settings.SERVE_MEDIA:
    urlpatterns += [
        re_path(r'^%s(?P<path>.*)$' % settings.MEDIA_URL.lstrip('/'), serve, {'document_root': settings.MEDIA_ROOT}),
    ]