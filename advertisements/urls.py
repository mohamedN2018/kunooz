from django.urls import path
from . import views

app_name = 'advertisements'

urlpatterns = [
    path("render/<str:code>/", views.render_ad_placement, name="render"),

    # تتبع الإعلانات
    path('impression/<int:ad_id>/', views.record_impression, name='record_impression'),
    path('click/<int:ad_id>/', views.record_click, name='record_click'),

    path('placement/edit/<int:pk>/', views.edit_placement, name='edit_placement'),
    path('placement/delete/<int:pk>/', views.delete_placement, name='delete_placement'),

    # لوحة التحكم والإدارة
    path('dashboard/', views.ad_dashboard, name='dashboard'),
    path('analytics/', views.analytics_dashboard, name='analytics'),
    path('create/', views.create_ad, name='create'),
    path('edit/<int:pk>/', views.edit_ad, name='edit'),
    path('preview/<int:pk>/', views.preview_ad, name='preview'),
    path('placements/', views.manage_placements, name='placements'),
    path('toggle/<int:pk>/', views.toggle_ad_status, name='toggle_status'),
    path('delete/<int:pk>/', views.delete_ad, name='delete'),
    path('bulk-actions/', views.bulk_actions, name='bulk_actions'),

    path('create-with-targeting/', views.create_ad_with_targeting, name='create_with_targeting'),


    
    # API والتقارير
    path('export-analytics/', views.export_analytics, name='export_analytics'),
    path('api/feed/', views.ad_json_feed, name='json_feed'),
    path('api/feed/<str:placement_code>/', views.ad_json_feed, name='json_feed_filtered'),
]
