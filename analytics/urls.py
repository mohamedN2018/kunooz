# analytics/urls.py
from django.urls import path
from . import views, tracking

urlpatterns = [
    # لوحات التحليلات الرئيسية
    path('dashboard/', views.advanced_analytics_dashboard, name='analytics_dashboard'),
    path('dashboard/simple/', views.simple_analytics_dashboard, name='simple_analytics'),
    path('dashboard/advanced/', views.legacy_analytics_dashboard, name='legacy_analytics_dashboard'),
    
    # تحليلات الدول
    path('countries/', views.country_analytics, name='country_analytics'),
    path('countries/<str:country_code>/', views.country_analytics, name='country_detail'),
    
    # تحليلات الوقت
    path('time/', views.time_analytics, name='time_analytics'),
    
    # تحليلات الصفحات
    path('pages/', views.page_analytics, name='page_analytics'),
    
    # تحليلات الأجهزة
    path('devices/', views.device_analytics, name='device_analytics'),
    
    # الزوار الفوريين
    path('realtime/', views.realtime_analytics, name='realtime_analytics'),
    
    # تفاصيل الجلسات
    path('sessions/<uuid:session_id>/', views.session_details, name='session_details'),
    
    # تصدير البيانات
    path('export/<str:format>/', views.export_analytics, name='export_analytics'),
    
    # سجل الزيارات والبيانات الحية (إشارات المتصفح /t/ping/ و /t/leave/ في kunooz/urls.py)
    path('visitors/', views.visitors_log, name='visitors_log'),
    path('live.json', views.live_json, name='analytics_live_json'),

    # الإعدادات
    path('settings/', views.analytics_settings, name='analytics_settings'),
]