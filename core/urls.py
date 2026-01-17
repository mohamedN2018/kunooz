from django.urls import path, include
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # الصفحات الرئيسية والتصفح
    path('', views.home, name='home'),
    path('courses/', views.courses, name='courses'),
    path('articles/', views.articles, name='articles'),
    path('grants/', views.grants, name='grants'),
    path('books/', views.books, name='books'),
    path('post/<str:slug>/', views.post_detail, name='post_detail'),
    
    # البحث
    path('search/', views.search, name='search'),
    path('autocomplete_search/', views.autocomplete_search, name='autocomplete_search'),
    
    # المصادقة
    path('login/', views.login_view, name='login'),
    path('register/', views.register, name='register'),
    path('logout/', views.logout_view, name='logout'),
    
    # الملف الشخصي والإعدادات
    path('profile/', views.profile, name='profile'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('change-password/', views.change_password, name='change_password'),
    path('delete-account/', views.delete_account, name='delete_account'),
    
    # استعادة كلمة المرور
    path('password-reset/', views.password_reset_request, name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='auth/password_reset_done.html'), name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='auth/password_reset_confirm.html'), name='password_reset_confirm'),
    path('reset/<uidb64>/<token>/', views.password_reset_confirm, name='password_reset_confirm'),
    
    # AJAX/API endpoints
    path('check-username/', views.check_username, name='check_username'),
    path('check-email/', views.check_email, name='check_email'),
    
    # إدارة المحتوى (للمستخدمين العاديين/المؤلفين)
    path('create-post/', views.create_post, name='create_post'),
    path('edit-post/<int:id>/', views.edit_post, name='edit_post'),
    path('delete-post/<int:id>/', views.delete_post, name='delete_post'),
    path('my-posts/comments/', views.view_comments_on_my_posts, name='my_comments'),
    path('my-posts/', views.my_posts, name='my_posts'),
    

    # لوحة تحكم المحتوى
    path('content/dashboard/', views.content_dashboard, name='content_dashboard'),
    
    # لوحة تحكم Staff
    path('staff/dashboard/', views.staff_dashboard, name='staff_dashboard'),
    path('staff/posts/', views.staff_manage_posts, name='staff_manage_posts'),
    
    # لوحة تحكم الإدارة الخاصة (بديل admin/)
    path('control/dashboard/', views.admin_dashboard, name='control_dashboard'),
    path('control/settings/', views.admin_settings, name='control_settings'),
    path('control/users/', views.manage_users, name='control_users'),
    path('control/logs/', views.system_logs, name='control_logs'),

    # إدارة التعليقات الخاصة بلوحة التحكم
    path('control/comments/', views.manage_comments, name='control_comments'),
    path('control/comments/approve/<int:comment_id>/', views.approve_comment, name='control_comment_approve'),
    path('control/comments/reject/<int:comment_id>/', views.reject_comment, name='control_comment_reject'),
    path('control/comments/bulk-approve/', views.bulk_approve_comments, name='control_comments_bulk_approve'),
    path('control/comments/bulk-delete/', views.bulk_delete_comments, name='control_comments_bulk_delete'),
]

# معالجات الأخطاء
handler404 = views.handler404
handler500 = views.handler500
handler403 = views.handler403
handler400 = views.handler400
