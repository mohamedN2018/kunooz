from django.urls import path
from . import views

app_name = 'advertisements'

urlpatterns = [
    path("render/<str:code>/", views.render_ad_placement, name="render"),

    # تتبع الإعلانات
    path('impression/<int:ad_id>/', views.record_impression, name='record_impression'),
    path('click/<int:ad_id>/', views.record_click, name='record_click'),

    # لوحات إدارة الإعلانات القديمة كانت تعتمد على user.user_type غير الموجود وقوالب غير موجودة
    # (كانت تعطي 302 لكل المستخدمين أو 500). الإدارة الآن من لوحة Django للـ staff.
    path('dashboard/', views.admin_redirect('advertisement'), name='dashboard'),
    path('analytics/', views.admin_redirect('advertisement'), name='analytics'),
    path('create/', views.admin_redirect('advertisement', 'add'), name='create'),
    path('create-with-targeting/', views.admin_redirect('advertisement', 'add'), name='create_with_targeting'),
    path('edit/<int:pk>/', views.admin_redirect('advertisement', 'change'), name='edit'),
    path('preview/<int:pk>/', views.admin_redirect('advertisement', 'change'), name='preview'),
    path('placements/', views.admin_redirect('adplacement'), name='placements'),
    path('placement/edit/<int:pk>/', views.admin_redirect('adplacement', 'change'), name='edit_placement'),

    # إجراءات تعديل البيانات: POST فقط وللـ staff
    path('toggle/<int:pk>/', views.toggle_ad_status, name='toggle_status'),
    path('delete/<int:pk>/', views.delete_ad, name='delete'),
    path('placement/delete/<int:pk>/', views.delete_placement, name='delete_placement'),
    path('bulk-actions/', views.bulk_actions, name='bulk_actions'),

    path('report/', views.ads_report, name='ads_report'),
    path('report/<int:pk>.csv', views.ad_csv, name='ad_csv'),

    # API والتقارير
    path('export-analytics/', views.export_analytics, name='export_analytics'),
    path('api/feed/', views.ad_json_feed, name='json_feed'),
    path('api/feed/<str:placement_code>/', views.ad_json_feed, name='json_feed_filtered'),
]
