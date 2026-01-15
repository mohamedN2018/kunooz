from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import login, authenticate, logout, update_session_auth_hash
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q, Count, Sum
from django.utils import timezone
from django.http import JsonResponse, HttpResponseForbidden, HttpResponse
from django.contrib import messages
from django.db import transaction
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.utils.html import strip_tags
from django.conf import settings

from .models import *
from .forms import *
import json
from datetime import datetime

# ======== دوال المساعدة ========
def is_content_editor(user):
    """التحقق من أن المستخدم محرر محتوى"""
    return user.is_authenticated and (
        user.is_staff or 
        (hasattr(user, 'profile') and user.profile.is_content_editor)
    )

def get_search_suggestions(query):
    """الحصول على اقتراحات البحث"""
    if len(query) < 2:
        return []
    
    suggestions = Post.objects.filter(
        Q(title__icontains=query[:3])
    ).values_list('title', flat=True).distinct()[:5]
    
    return list(suggestions)

# ======== الصفحات الرئيسية ========
def home(request):
    """الصفحة الرئيسية"""
    courses_posts = Post.objects.filter(
        category__category_type='courses', 
        status='published'
    ).order_by('-publish_date')[:6]
    
    articles_posts = Post.objects.filter(
        category__category_type='articles', 
        status='published'
    ).order_by('-publish_date')[:6]
    
    grants_posts = Post.objects.filter(
        category__category_type='grants', 
        status='published'
    ).order_by('-publish_date')[:6]
    
    books_posts = Post.objects.filter(
        category__category_type='books', 
        status='published'
    ).order_by('-publish_date')[:6]

    url_media = SiteSettings.objects.first()

    return render(request, 'home.html', {
        'courses_posts': courses_posts,
        'articles_posts': articles_posts,
        'grants_posts': grants_posts,
        'books_posts': books_posts,
        'url_media': url_media,
    })


# ======== تحديث دوال الصفحات الرئيسية ========

def articles(request):
    """صفحة المقالات مع إحصائيات متقدمة"""
    category = get_object_or_404(Category, category_type='articles')
    posts_list = Post.objects.filter(
        category__category_type='articles',
        status='published'
    ).order_by('-publish_date')
    
    # إحصائيات حقيقية
    total_posts = posts_list.count()
    total_authors = User.objects.filter(
        posts__category__category_type='articles',
        posts__status='published'
    ).distinct().count()
    total_views = posts_list.aggregate(total_views=Sum('views'))['total_views'] or 0
    total_comments = Comment.objects.filter(
        post__category__category_type='articles',
        post__status='published',
        is_approved=True
    ).count()
    
    # المقالات المميزة
    featured_posts = posts_list.filter(views__gte=100)[:2]
    
    # التصفية
    category_filter = request.GET.get('category', '')
    sort_by = request.GET.get('sort', 'newest')
    
    if category_filter:
        posts_list = posts_list.filter(category__name=category_filter)
    
    if sort_by == 'popular':
        posts_list = posts_list.order_by('-views')
    elif sort_by == 'commented':
        posts_list = posts_list.annotate(comment_count=Count('comments')).order_by('-comment_count')
    
    paginator = Paginator(posts_list, 12)
    page_number = request.GET.get('page')
    posts = paginator.get_page(page_number)
    
    # التصنيفات المتاحة
    available_categories = Category.objects.filter(
        category_type='articles'
    ).annotate(post_count=Count('posts')).order_by('-post_count')
    
    return render(request, 'articles.html', {
        'category': category,
        'posts': posts,
        'title': 'المقالات',
        'total_posts': total_posts,
        'total_authors': total_authors,
        'total_views': total_views,
        'total_comments': total_comments,
        'featured_posts': featured_posts,
        'available_categories': available_categories,
        'current_category_filter': category_filter,
        'current_sort': sort_by,
    })


def books(request):
    """صفحة الكتب والملخصات مع تصنيفات متقدمة"""
    category = get_object_or_404(Category, category_type='books')
    posts_list = Post.objects.filter(
        category__category_type='books',
        status='published'
    ).order_by('-publish_date')
    
    # إحصائيات حقيقية
    total_books = posts_list.filter(
        Q(seo_keywords__icontains='كتاب') | Q(title__icontains='كتاب')
    ).count()
    
    total_summaries = posts_list.filter(
        Q(seo_keywords__icontains='ملخص') | Q(title__icontains='ملخص')
    ).count()
    
    total_downloads = posts_list.aggregate(total_downloads=Sum('views'))['total_downloads'] or 0
    total_authors = User.objects.filter(
        posts__category__category_type='books',
        posts__status='published'
    ).distinct().count()
    
    # التصفية
    book_type = request.GET.get('type', '')
    book_category = request.GET.get('category', '')
    sort_by = request.GET.get('sort', 'newest')
    
    if book_type:
        if book_type == 'book':
            posts_list = posts_list.filter(
                Q(seo_keywords__icontains='كتاب') | Q(title__icontains='كتاب')
            )
        elif book_type == 'summary':
            posts_list = posts_list.filter(
                Q(seo_keywords__icontains='ملخص') | Q(title__icontains='ملخص')
            )
    
    if book_category:
        posts_list = posts_list.filter(category__name=book_category)
    
    if sort_by == 'downloads':
        posts_list = posts_list.order_by('-views')
    elif sort_by == 'popular':
        posts_list = posts_list.order_by('-views')
    
    paginator = Paginator(posts_list, 12)
    page_number = request.GET.get('page')
    posts = paginator.get_page(page_number)
    
    # الكتب الموصى بها (الأكثر مشاهدة)
    recommended_books = posts_list.order_by('-views')[:2]
    
    # التصنيفات المتاحة
    available_categories = Category.objects.filter(
        category_type='books'
    ).annotate(post_count=Count('posts')).order_by('-post_count')
    
    return render(request, 'books.html', {
        'category': category,
        'posts': posts,
        'title': 'الكتب والملخصات',
        'total_books': total_books,
        'total_summaries': total_summaries,
        'total_downloads': total_downloads,
        'total_authors': total_authors,
        'recommended_books': recommended_books,
        'available_categories': available_categories,
        'current_type': book_type,
        'current_category': book_category,
        'current_sort': sort_by,
    })


def courses(request):
    """صفحة الكورسات مع تصفية متقدمة"""
    category = get_object_or_404(Category, category_type='courses')
    posts_list = Post.objects.filter(
        category__category_type='courses',
        status='published'
    ).order_by('-publish_date')
    
    # التصفية
    course_category = request.GET.get('category', '')
    sort_by = request.GET.get('sort', 'newest')
    
    if course_category:
        posts_list = posts_list.filter(category__id=course_category)
    
    if sort_by == 'popular':
        posts_list = posts_list.order_by('-views')
    elif sort_by == 'commented':
        posts_list = posts_list.annotate(comment_count=Count('comments')).order_by('-comment_count')
    
    paginator = Paginator(posts_list, 12)
    page_number = request.GET.get('page')
    posts = paginator.get_page(page_number)
    
    # التصنيفات المتاحة
    categories = Category.objects.filter(
        category_type='courses'
    ).annotate(post_count=Count('posts')).order_by('-post_count')
    
    return render(request, 'courses.html', {
        'category': category,
        'posts': posts,
        'title': 'الكورسات',
        'categories': categories,
        'current_category': course_category,
        'current_sort': sort_by,
    })


def grants(request):
    """صفحة المنح والتدريبات مع تصفية متقدمة"""
    category = get_object_or_404(Category, category_type='grants')
    posts_list = Post.objects.filter(
        category__category_type='grants',
        status='published'
    ).order_by('-publish_date')
    
    # المنح المميزة (التي تحتوي على كلمات مفتاحية مميزة)
    featured_grants = posts_list.filter(
        Q(seo_keywords__icontains='مميز') | Q(seo_keywords__icontains='ممولة')
    )[:2]
    
    # التصفية
    grant_type = request.GET.get('type', '')
    sort_by = request.GET.get('sort', 'deadline')
    
    if grant_type == 'scholarship':
        posts_list = posts_list.filter(
            Q(title__icontains='منحة') | Q(seo_keywords__icontains='منحة')
        )
    elif grant_type == 'training':
        posts_list = posts_list.filter(
            Q(title__icontains='تدريب') | Q(seo_keywords__icontains='تدريب')
        )
    
    if sort_by == 'newest':
        posts_list = posts_list.order_by('-publish_date')
    elif sort_by == 'funding':
        posts_list = posts_list.filter(seo_keywords__icontains='ممولة').order_by('-publish_date')
    
    # إحصاءات سريعة
    upcoming_deadlines = posts_list.filter(
        publish_date__gte=timezone.now() - timezone.timedelta(days=30)
    ).count()
    
    free_opportunities = posts_list.filter(
        Q(title__icontains='مجاني') | Q(seo_keywords__icontains='مجاني')
    ).count()
    
    fully_funded = posts_list.filter(
        Q(title__icontains='ممولة') | Q(seo_keywords__icontains='ممولة')
    ).count()
    
    paginator = Paginator(posts_list, 12)
    page_number = request.GET.get('page')
    posts = paginator.get_page(page_number)
    
    return render(request, 'grants.html', {
        'category': category,
        'posts': posts,
        'title': 'المنح والتدريبات',
        'featured_grants': featured_grants,
        'upcoming_deadlines': upcoming_deadlines,
        'free_opportunities': free_opportunities,
        'fully_funded': fully_funded,
        'current_type': grant_type,
        'current_sort': sort_by,
    })



# ======== تفاصيل المنشور ========
def post_detail(request, slug):
    """عرض منشور معين"""
    post = get_object_or_404(Post, slug=slug, status='published')
    
    # زيادة عدد المشاهدات
    post.increment_views()
    
    # الحصول على التعليقات المعتمدة فقط
    comments = post.comments.filter(is_approved=True)
    
    # الحصول على البلوكات الخاصة بالمنشور
    post_blocks = post.blocks.all().order_by('order')
    
    # معالجة نموذج التعليق
    if request.method == 'POST' and 'comment_form' in request.POST:
        comment_form = CommentForm(request.POST)
        if comment_form.is_valid():
            comment = comment_form.save(commit=False)
            comment.post = post
            
            # إذا كان المستخدم مسجل دخول، استخدام معلوماته
            if request.user.is_authenticated:
                comment.name = f"{request.user.first_name} {request.user.last_name}".strip()
                if not comment.name:
                    comment.name = request.user.username
                comment.email = request.user.email
            
            comment.save()
            messages.success(request, 'تم إرسال تعليقك بنجاح، سيظهر بعد المراجعة.')
            return redirect('post_detail', slug=post.slug)
    else:
        comment_form = CommentForm()
    
    # الحصول على المنشورات المشابهة
    similar_posts = Post.objects.filter(
        category=post.category,
        status='published'
    ).exclude(id=post.id).order_by('-publish_date')[:4]
    
    return render(request, 'post_detail.html', {
        'post': post,
        'comments': comments,
        'comment_form': comment_form,
        'similar_posts': similar_posts,
        'post_blocks': post_blocks,
    })


# ======== إنشاء وتعديل المنشورات ========
@login_required
@user_passes_test(is_content_editor)
def create_post(request):
    """إنشاء منشور جديد"""
    if request.method == 'POST':
        print("📋 POST DATA:")
        for key, value in request.POST.items():
            print(f"  {key}: {value}")
        print("\n📁 FILES:")
        for key, file in request.FILES.items():
            print(f"  {key}: {file.name} ({file.size} bytes)")
        
        form = PostForm(request.POST, request.FILES)
        
        if form.is_valid():
            print("✅ Form is valid")
            try:
                with transaction.atomic():
                    post = form.save(commit=False)
                    post.author = request.user
                    
                    # تحديد الحالة من الزر المضغوط
                    if 'save_draft' in request.POST:
                        post.status = Post.Status.DRAFT
                    elif 'publish_now' in request.POST:
                        post.status = Post.Status.PUBLISHED
                        if not post.publish_date:
                            post.publish_date = timezone.now()
                    
                    # حفظ المنشور
                    post.save()
                    
                    # معالجة البلوكات إذا كانت موجودة
                    blocks_data_str = request.POST.get('blocks_data', '[]')
                    try:
                        blocks_data = json.loads(blocks_data_str)
                        if blocks_data:
                            create_post_blocks(post, blocks_data, request.FILES)
                    except json.JSONDecodeError as e:
                        print(f"⚠️ Blocks data error: {e}")
                    
                    messages.success(request, f'تم {"نشر" if post.status == Post.Status.PUBLISHED else "حفظ"} المنشور "{post.title}" بنجاح!')
                    
                    # إعادة التوجيه
                    if post.status == Post.Status.PUBLISHED:
                        return redirect('post_detail', slug=post.slug)
                    else:
                        return redirect('edit_post', id=post.id)
                        
            except Exception as e:
                messages.error(request, f'حدث خطأ أثناء حفظ المنشور: {str(e)}')
                print(f"❌ Error saving post: {e}")
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء في النموذج')
            print("❌ Form is invalid")
            print("📝 Form errors:", form.errors)
            
            # طباعة تفصيلية لكل حقل
            print("\n🔍 Detailed field errors:")
            for field in form:
                if field.errors:
                    print(f"  Field '{field.name}': {field.errors}")
    else:
        # تهيئة القيم الافتراضية
        initial_data = {
            'link_delay': 30,
            'status': Post.Status.DRAFT,
        }
        
        form = PostForm(initial=initial_data)
    
    categories = Category.objects.all().order_by('name')
    
    return render(request, 'create_post.html', {
        'form': form,
        'categories': categories,
        'post_statuses': Post.Status.choices
    })


def create_post_blocks(post, blocks_data, files):
    """إنشاء وإدارة بلوكات المحتوى"""
    existing_blocks = {b.order: b for b in post.blocks.all()}

    for i, block_data in enumerate(blocks_data):
        block_type = block_data.get('type', 'text')
        text_content = block_data.get('text', '')

        # إذا كان البلوك موجوداً، قم بتحديثه
        if i in existing_blocks:
            post_block = existing_blocks[i]
            post_block.block_type = block_type
        else:
            # إنشاء بلوك جديد
            post_block = PostBlock(post=post, order=i, block_type=block_type)

        if block_type == 'text':
            post_block.text = text_content
        elif block_type == 'image':
            image_name = block_data.get('image_name', '')
            if image_name:
                for file_key in files:
                    file = files[file_key]
                    if hasattr(file, 'name') and file.name == image_name:
                        post_block.image = file
                        break

        post_block.save()

    return True

@login_required
@user_passes_test(is_content_editor)
def edit_post(request, id):
    """تعديل منشور موجود"""
    post = get_object_or_404(Post, id=id)
    post_blocks = post.blocks.all().order_by('order')
    categories = Category.objects.all()

    # التحقق من صلاحية المستخدم
    if not (request.user.is_staff or post.author == request.user or 
            (hasattr(request.user, 'profile') and request.user.profile.is_content_editor)):
        return HttpResponseForbidden("ليس لديك صلاحية لتعديل هذا المنشور")
    
    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES, instance=post)
        if form.is_valid():
            try:
                with transaction.atomic():
                    post = form.save(commit=False)
                    
                    # معالجة حالة النشر
                    if 'save_draft' in request.POST:
                        post.status = Post.Status.DRAFT
                    elif 'publish_now' in request.POST:
                        post.status = Post.Status.PUBLISHED
                        if not post.publish_date:
                            post.publish_date = timezone.now()
                    
                    # حفظ التغييرات
                    post.save()
                    
                    # معالجة البلوكات
                    blocks_data_str = request.POST.get('blocks_data', '[]')
                    try:
                        blocks_data = json.loads(blocks_data_str)
                        
                        # حذف البلوكات القديمة
                        post.blocks.all().delete()
                        
                        # إنشاء البلوكات الجديدة
                        for i, block_data in enumerate(blocks_data):
                            post_block = PostBlock(
                                post=post,
                                block_type=block_data.get('type', 'text'),
                                order=i
                            )
                            
                            if block_data['type'] == 'text':
                                post_block.text = block_data.get('text', '')
                            elif block_data['type'] == 'image':
                                # معالجة الصور من خلال حقل مخفي
                                image_name = block_data.get('image_name', '')
                                if image_name:
                                    # البحث عن الملف المرفق بالاسم
                                    for file_key in request.FILES:
                                        if request.FILES[file_key].name == image_name:
                                            post_block.image = request.FILES[file_key]
                                            break
                            
                            post_block.save()
                            
                    except (json.JSONDecodeError, KeyError) as e:
                        print(f"Error processing blocks: {e}")
                    
                    messages.success(request, f'تم تحديث المنشور "{post.title}" بنجاح!')
                    
                    # إعادة التوجيه حسب الحالة
                    if post.status == Post.Status.PUBLISHED:
                        return redirect('post_detail', slug=post.slug)
                    else:
                        return redirect('edit_post', id=post.id)
                        
            except Exception as e:
                messages.error(request, f'حدث خطأ أثناء تحديث المنشور: {str(e)}')
                print(f"Error: {e}")
    else:
        form = PostForm(instance=post)
    
    return render(request, 'edit_post.html', {
        'form': form,
        'post': post,
        'post_blocks': post_blocks,
        'post_statuses': Post.Status.choices,
        'categories': categories,
    })


@login_required
def delete_post(request, id):
    """حذف منشور"""
    post = get_object_or_404(Post, id=id, author=request.user)
    post.delete()
    messages.success(request, 'تم حذف المنشور بنجاح!')
    return redirect('dashboard')


# ======== البحث ========
def search(request):
    """صفحة البحث"""
    query = request.GET.get('q', '').strip()
    category_filter = request.GET.get('category', '')
    sort_by = request.GET.get('sort', 'relevance')
    
    if query:
        # بناء استعلام البحث
        search_queries = Q(
            Q(title__icontains=query) | 
            Q(content__icontains=query) |
            Q(excerpt__icontains=query) |
            Q(seo_title__icontains=query) |
            Q(seo_description__icontains=query) |
            Q(category__name__icontains=query)
        ) & Q(status='published')
        
        # تطبيق فلتر الفئة إذا موجود
        if category_filter:
            search_queries &= Q(category__category_type=category_filter)
        
        # الحصول على النتائج
        results = Post.objects.filter(search_queries).distinct()
        
        # تطبيق الترتيب
        if sort_by == 'date':
            results = results.order_by('-publish_date')
        elif sort_by == 'title':
            results = results.order_by('title')
        elif sort_by == 'popularity':
            results = results.order_by('-views')
        else:  # relevance (default)
            results = results.order_by('-publish_date')
        
        # إحصائيات البحث
        search_stats = {
            'total': results.count(),
            'courses': results.filter(category__category_type='courses').count(),
            'articles': results.filter(category__category_type='articles').count(),
            'grants': results.filter(category__category_type='grants').count(),
            'books': results.filter(category__category_type='books').count(),
        }
        
    else:
        results = Post.objects.none()
        search_stats = {
            'total': 0,
            'courses': 0,
            'articles': 0,
            'grants': 0,
            'books': 0,
        }
    
    # الترقيم
    paginator = Paginator(results, 12)
    page = request.GET.get('page', 1)
    
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
    
    # الفئات المتاحة للفلترة
    available_categories = Category.objects.filter(
        category_type__in=['courses', 'articles', 'grants', 'books']
    ).order_by('category_type').distinct()
    
    return render(request, 'search/search_results.html', {
        'query': query,
        'results': page_obj,
        'search_stats': search_stats,
        'category_filter': category_filter,
        'sort_by': sort_by,
        'available_categories': available_categories,
        'suggestions': get_search_suggestions(query) if query else [],
        'paginator': paginator,
        'popular_terms': ['Python', 'تعلم الآلة', 'منح دراسية', 'برمجة', 'تعليم مجاني', 'كورسات أونلاين'],
    })


def autocomplete_search(request):
    """الإكمال التلقائي للبحث"""
    term = request.GET.get('term', '').strip()
    results = []

    if term:
        posts = Post.objects.filter(
            Q(title__icontains=term) | Q(content__icontains=term),
            status='published'
        )[:10]

        for post in posts:
            results.append({
                'title': post.title,
                'url': post.get_absolute_url(),
            })

        categories = Category.objects.filter(name__icontains=term)[:5]
        for cat in categories:
            results.append({
                'title': cat.name,
                'url': cat.get_absolute_url(),
            })

    return JsonResponse(results, safe=False)


# ======== API للبلوكات ========
@login_required
@user_passes_test(is_content_editor)
def api_upload_block_image(request):
    """رفع صورة للبلوك"""
    if request.method == 'POST' and request.FILES.get('image'):
        image_file = request.FILES['image']
        
        return JsonResponse({
            'success': True,
            'filename': image_file.name,
            'message': 'تم رفع الصورة بنجاح'
        })
    
    return JsonResponse({'success': False, 'error': 'لم يتم رفع صورة'})


# ======== المصادقة والمستخدمين ========
def login_view(request):
    """تسجيل الدخول"""
    if request.user.is_authenticated:
        messages.info(request, 'أنت مسجل الدخول بالفعل!')
        return redirect('home')
    
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            remember_me = form.cleaned_data.get('remember_me', False)
            
            user = authenticate(request, username=username, password=password)
            
            if user is not None:
                login(request, user)
                
                if not remember_me:
                    request.session.set_expiry(0)
                else:
                    request.session.set_expiry(1209600)
                
                messages.success(request, f'مرحباً بك {user.username}!')
                
                next_url = request.GET.get('next', 'home')
                return redirect(next_url)
            else:
                messages.error(request, 'اسم المستخدم أو كلمة المرور غير صحيحة!')
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء أدناه.')
    else:
        form = LoginForm()
    
    return render(request, 'auth/login.html', {'form': form})


def register(request):
    """التسجيل"""
    if request.user.is_authenticated:
        messages.info(request, 'أنت مسجل الدخول بالفعل!')
        return redirect('home')
    
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            
            profile, created = UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    "full_name": f"{form.cleaned_data.get('first_name','')} {form.cleaned_data.get('last_name','')}".strip()
                }
            )

            login(request, user)
            messages.success(request, f'مرحباً بك {user.username}!')
            return redirect('home')
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء أدناه.')
    else:
        form = RegisterForm()

    return render(request, 'auth/register.html', {'form': form})


@login_required
def logout_view(request):
    """تسجيل الخروج"""
    if request.method == 'POST':
        logout(request)
        messages.success(request, 'تم تسجيل خروجك بنجاح!')
        return redirect('home')
    
    return render(request, 'auth/logout.html')

@login_required
def profile(request):
    """الملف الشخصي"""
    try:
        user_profile = UserProfile.objects.get(user=request.user)
    except UserProfile.DoesNotExist:
        user_profile = UserProfile.objects.create(user=request.user)
    
    # جلب مقالات المستخدم مع الترقيم
    user_posts = Post.objects.filter(author=request.user).order_by('-created_at')
    
    # الترقيم
    paginator = Paginator(user_posts, 9)  # 9 مقالات لكل صفحة
    page_number = request.GET.get('page')
    posts_page = paginator.get_page(page_number)
    
    # إحصائيات المستخدم
    published_posts_count = request.user.posts.filter(status='published').count()
    draft_posts_count = request.user.posts.filter(status='draft').count()
    total_posts = user_posts.count()
    total_views = user_posts.aggregate(total_views=Sum('views'))['total_views'] or 0
    comments_count = Comment.objects.filter(post__author=request.user).count()
    
    # حساب الأيام النشطة
    days_active = (timezone.now() - request.user.date_joined).days
    days_active = max(days_active, 1)  # على الأقل يوم واحد
    
    # حساب متوسط المشاهدات لكل مقال
    avg_views_per_post = total_views / total_posts if total_posts > 0 else 0
    
    # حساب نسبة التعليقات للإنجازات
    comments_width = min((comments_count / 10) * 100, 100) if comments_count > 0 else 0
    
    # النشاط الأخير
    recent_activities = []
    
    # إضافة المنشورات الجديدة كنشاط
    recent_posts = user_posts[:5]
    for post in recent_posts:
        recent_activities.append({
            'message': f'أنشأت مقال جديد: "{post.title[:30]}..."',
            'details': f'في {post.category.name}',
            'time': post.created_at,
            'icon': 'newspaper'
        })
    
    # إضافة التعليقات كنشاط
    recent_comments = Comment.objects.filter(post__author=request.user).order_by('-created_at')[:3]
    for comment in recent_comments:
        recent_activities.append({
            'message': f'تلقيت تعليق جديد على "{comment.post.title[:20]}..."',
            'details': f'بواسطة {comment.name}',
            'time': comment.created_at,
            'icon': 'comment'
        })
    
    # إضافة المشاهدات كنشاط
    popular_posts = user_posts.order_by('-views')[:2]
    for post in popular_posts:
        if post.views > 0:
            recent_activities.append({
                'message': f'مقالك "{post.title[:20]}..." حصل على {post.views} مشاهدة',
                'details': f'آخر تحديث: {post.updated_at.strftime("%Y-%m-%d")}',
                'time': post.updated_at,
                'icon': 'eye'
            })
    
    # ترتيب النشاط حسب الوقت
    recent_activities.sort(key=lambda x: x['time'], reverse=True)
    
    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES, instance=user_profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'تم تحديث الملف الشخصي بنجاح!')
            return redirect('profile')
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء أدناه.')
    else:
        form = UserProfileForm(instance=user_profile)
    
    return render(request, 'auth/profile.html', {
        'title': 'ملفي الشخصي',
        'user': request.user,
        'profile': user_profile,
        'form': form,
        'posts': posts_page,  # المنشورات مع الترقيم
        'total_posts': total_posts,
        'published_posts_count': published_posts_count,
        'draft_posts_count': draft_posts_count,
        'total_views': total_views,
        'comments_count': comments_count,
        'days_active': days_active,
        'avg_views_per_post': round(avg_views_per_post, 1),
        'comments_width': comments_width,
        'recent_activities': recent_activities[:5],  # آخر 5 نشاطات
        'recent_comments_count': recent_comments.count(),
    })

@login_required
def change_password(request):
    """تغيير كلمة المرور"""
    if request.method == 'POST':
        form = ChangePasswordForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'تم تغيير كلمة المرور بنجاح!')
            return redirect('profile')
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء أدناه.')
    else:
        form = ChangePasswordForm(request.user)
    
    return render(request, 'auth/change_password.html', {'form': form})

def password_reset_confirm(request, uidb64, token):
    if request.user.is_authenticated:
        messages.info(request, 'أنت مسجل الدخول بالفعل!')
        return redirect('home')

    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        if request.method == 'POST':
            form = SetPasswordForm(user, request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, 'تم تعيين كلمة المرور الجديدة بنجاح!')
                return redirect('password_reset_complete')
            else:
                messages.error(request, 'يرجى تصحيح الأخطاء أدناه.')
        else:
            form = SetPasswordForm(user)

        return render(request, 'auth/password_reset_confirm.html', {
            'form': form,
            'validlink': True
        })
    else:
        messages.error(request, 'رابط إعادة التعيين غير صالح أو منتهي الصلاحية!')
        return render(request, 'auth/password_reset_confirm.html', {'validlink': False})


# ======== استعادة كلمة المرور ========
def password_reset_request(request):
    """طلب إعادة تعيين كلمة المرور"""
    if request.user.is_authenticated:
        messages.info(request, 'أنت مسجل الدخول بالفعل!')
        return redirect('home')
    
    if request.method == 'POST':
        form = CustomPasswordResetForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            
            associated_users = User.objects.filter(Q(email__iexact=email))
            
            if associated_users.exists():
                for user in associated_users:
                    if user.is_active:
                        subject = "إعادة تعيين كلمة المرور - موقع التعليم"
                        token = default_token_generator.make_token(user)
                        uid = urlsafe_base64_encode(force_bytes(user.pk))
                        
                        reset_url = request.build_absolute_uri(
                            f'/reset/{uid}/{token}/'
                        )
                        
                        context = {
                            'email': user.email,
                            'username': user.username,
                            'reset_url': reset_url,
                            'site_name': 'موقع التعليم',
                            'user': user,
                        }
                        
                        html_message = render_to_string('emails/password_reset_email.html', context)
                        plain_message = strip_tags(html_message)
                        
                        try:
                            send_mail(
                                subject=subject,
                                message=plain_message,
                                from_email=settings.DEFAULT_FROM_EMAIL,
                                recipient_list=[user.email],
                                html_message=html_message,
                                fail_silently=False,
                            )
                            
                            messages.success(request, f'تم إرسال رابط إعادة التعيين إلى {email}.')
                            return render(request, 'auth/password_reset_done.html', {'email': email})
                            
                        except Exception as e:
                            messages.error(request, f'حدث خطأ أثناء إرسال البريد: {str(e)}')
                    else:
                        messages.error(request, 'هذا الحساب غير مفعل.')
            else:
                messages.error(request, 'لا يوجد حساب مرتبط بهذا البريد الإلكتروني.')
        else:
            messages.error(request, 'يرجى إدخال بريد إلكتروني صحيح.')
    else:
        form = CustomPasswordResetForm()
    
    return render(request, 'auth/password_reset.html', {'form': form})


def password_reset_complete(request):
    """اكتمال إعادة تعيين كلمة المرور"""
    return render(request, 'auth/password_reset_complete.html')


# ======== لوحات التحكم ========
@login_required
def dashboard(request):
    """لوحة تحكم المستخدم"""
    user = request.user
    posts = Post.objects.filter(author=user).order_by('-created_at')[:10]
    
    total_posts = Post.objects.filter(author=user).count()
    published_posts = Post.objects.filter(author=user, status='published').count()
    draft_posts = Post.objects.filter(author=user, status='draft').count()
    total_views = Post.objects.filter(author=user).aggregate(total_views=Sum('views'))['total_views'] or 0
    
    return render(request, 'dashboard.html', {
        'user': user,
        'posts': posts,
        'total_posts': total_posts,
        'published_posts': published_posts,
        'draft_posts': draft_posts,
        'total_views': total_views,
    })


@login_required
def my_posts(request):
    """صفحة منشورات المستخدم الشخصية"""
    posts = Post.objects.filter(author=request.user).order_by('-created_at')
    
    # الترقيم
    paginator = Paginator(posts, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'my_posts.html', {
        'posts': page_obj,
        'title': 'منشوراتي',
        'total_posts': posts.count(),
        'published_posts': posts.filter(status='published').count(),
        'draft_posts': posts.filter(status='draft').count(),
        'archived_posts': posts.filter(status='archived').count(),
    })

@login_required
def content_dashboard(request):
    """لوحة تحكم المحتوى"""
    user = request.user
    is_staff_or_editor = user.is_staff or (hasattr(user, 'profile') and user.profile.is_content_editor)
    
    if not is_staff_or_editor:
        return redirect('dashboard')
    
    if user.is_superuser or user.is_staff:
        total_posts = Post.objects.count()
        published_posts = Post.objects.filter(status='published').count()
        draft_posts = Post.objects.filter(status='draft').count()
        recent_posts = Post.objects.all().order_by('-created_at')[:5]
        new_comments = Comment.objects.filter(is_approved=False).count()
    else:
        total_posts = Post.objects.filter(author=user).count()
        published_posts = Post.objects.filter(author=user, status='published').count()
        draft_posts = Post.objects.filter(author=user, status='draft').count()
        recent_posts = Post.objects.filter(author=user).order_by('-created_at')[:5]
        new_comments = Comment.objects.filter(
            post__author=user,
            is_approved=False
        ).count()
    
    if user.is_superuser or user.is_staff:
        total_views = Post.objects.aggregate(total_views=Sum('views'))['total_views'] or 0
        posts_by_type = {
            'courses': Post.objects.filter(category__category_type='courses').count(),
            'articles': Post.objects.filter(category__category_type='articles').count(),
            'grants': Post.objects.filter(category__category_type='grants').count(),
            'books': Post.objects.filter(category__category_type='books').count(),
        }
    else:
        total_views = Post.objects.filter(author=user).aggregate(total_views=Sum('views'))['total_views'] or 0
        posts_by_type = {
            'courses': Post.objects.filter(author=user, category__category_type='courses').count(),
            'articles': Post.objects.filter(author=user, category__category_type='articles').count(),
            'grants': Post.objects.filter(author=user, category__category_type='grants').count(),
            'books': Post.objects.filter(author=user, category__category_type='books').count(),
        }
    
    return render(request, 'content_dashboard.html', {
        'title': 'لوحة تحكم المحتوى',
        'total_posts': total_posts,
        'published_posts': published_posts,
        'draft_posts': draft_posts,
        'recent_posts': recent_posts,
        'new_comments': new_comments,
        'total_views': total_views,
        'posts_by_type': posts_by_type,
        'is_staff': user.is_staff,
        'is_superuser': user.is_superuser,
    })


@login_required
def admin_dashboard(request):
    """لوحة تحكم الإدارة"""
    user = request.user
    
    if not user.is_staff and not (hasattr(user, 'profile') and user.profile.is_content_editor):
        return redirect('dashboard')
    
    if user.is_superuser:
        template_name = 'admin_dashboard.html'
        is_superuser = True
    elif user.is_staff:
        template_name = 'staff_dashboard.html'
        is_superuser = False
    else:
        template_name = 'content_dashboard.html'
        is_superuser = False
    
    if user.is_superuser:
        total_posts = Post.objects.count()
        total_comments = Comment.objects.count()
        total_users = User.objects.count()
        total_views = Post.objects.aggregate(total_views=Sum('views'))['total_views'] or 0
        
        recent_posts = Post.objects.all().select_related('category', 'author').order_by('-created_at')[:10]
        new_comments = Comment.objects.filter(is_approved=False).select_related('post').order_by('-created_at')[:10]
        
    elif user.is_staff:
        total_posts = Post.objects.count()
        total_comments = Comment.objects.count()
        total_users = User.objects.count()
        total_views = Post.objects.aggregate(total_views=Sum('views'))['total_views'] or 0
        
        recent_posts = Post.objects.all().select_related('category', 'author').order_by('-created_at')[:10]
        new_comments = Comment.objects.filter(is_approved=False).select_related('post').order_by('-created_at')[:10]
        
    else:
        total_posts = Post.objects.filter(author=user).count()
        total_comments = Comment.objects.filter(post__author=user).count()
        total_users = 0
        total_views = Post.objects.filter(author=user).aggregate(total_views=Sum('views'))['total_views'] or 0
        
        recent_posts = Post.objects.filter(author=user).select_related('category', 'author').order_by('-created_at')[:10]
        new_comments = Comment.objects.filter(
            post__author=user,
            is_approved=False
        ).select_related('post').order_by('-created_at')[:10]
    
    published_posts = Post.objects.filter(status='published').count()
    published_percentage = (published_posts / total_posts * 100) if total_posts > 0 else 0
    
    approved_comments = Comment.objects.filter(is_approved=True).count()
    approved_comments_percentage = (approved_comments / total_comments * 100) if total_comments > 0 else 0
    
    if user.is_superuser:
        active_editors = UserProfile.objects.filter(is_content_editor=True).count()
        non_editor_users = total_users - active_editors
        active_editors_percentage = (active_editors / total_users * 100) if total_users > 0 else 0
        
        today = timezone.now().date()
        views_today = Post.objects.filter(publish_date__date=today).aggregate(Sum('views'))['views__sum'] or 0
        
        posts_by_type = {
            'courses': Post.objects.filter(category__category_type='courses').count(),
            'articles': Post.objects.filter(category__category_type='articles').count(),
            'grants': Post.objects.filter(category__category_type='grants').count(),
            'books': Post.objects.filter(category__category_type='books').count(),
        }
        
        days_since_start = max((timezone.now() - timezone.make_aware(datetime(2024, 1, 1))).days, 1)
        average_views_per_day = total_views / days_since_start
        
        admin_context = {
            'active_editors': active_editors,
            'non_editor_users': non_editor_users,
            'active_editors_percentage': round(active_editors_percentage, 1),
            'views_today': views_today,
            'posts_by_type': posts_by_type,
            'average_views_per_day': round(average_views_per_day, 1),
            'posts_today': Post.objects.filter(created_at__date=today).count(),
            'comments_today': Comment.objects.filter(created_at__date=today).count(),
            'users_today': User.objects.filter(date_joined__date=today).count(),
            'average_views_per_post': round(total_views / total_posts, 0) if total_posts > 0 else 0,
        }
    else:
        admin_context = {}
    
    return render(request, template_name, {
        'total_posts': total_posts,
        'total_comments': total_comments,
        'total_users': total_users,
        'total_views': total_views,
        'recent_posts': recent_posts,
        'new_comments': new_comments,
        'published_posts': published_posts,
        'published_percentage': round(published_percentage, 1),
        'approved_comments': approved_comments,
        'approved_comments_percentage': round(approved_comments_percentage, 1),
        'user': user,
        'is_superuser': is_superuser,
        **admin_context,
    })


# ======== إدارة التعليقات ========
@staff_member_required
def manage_comments(request):
    """إدارة جميع التعليقات"""
    comments = Comment.objects.all().select_related('post', 'user').order_by('-created_at')
    
    paginator = Paginator(comments, 20)
    page = request.GET.get('page', 1)
    
    try:
        comments_page = paginator.page(page)
    except PageNotAnInteger:
        comments_page = paginator.page(1)
    except EmptyPage:
        comments_page = paginator.page(paginator.num_pages)
    
    return render(request, 'admin/manage_comments.html', {
        'comments': comments_page,
        'title': 'إدارة التعليقات',
        'total_comments': comments.count(),
        'approved_comments': Comment.objects.filter(is_approved=True).count(),
        'pending_comments': Comment.objects.filter(is_approved=False).count(),
    })


@staff_member_required
def approve_comment(request, comment_id):
    """قبول تعليق معين"""
    if request.method == 'POST':
        comment = get_object_or_404(Comment, id=comment_id)
        comment.is_approved = True
        comment.save()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'تم قبول التعليق بنجاح'})
        
        messages.success(request, 'تم قبول التعليق بنجاح')
        return redirect('manage_comments')
    
    return JsonResponse({'success': False, 'message': 'طريقة الطلب غير صحيحة'})


@staff_member_required
def reject_comment(request, comment_id):
    """رفض وحذف تعليق"""
    if request.method == 'POST':
        comment = get_object_or_404(Comment, id=comment_id)
        comment.delete()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'تم رفض التعليق بنجاح'})
        
        messages.success(request, 'تم رفض التعليق بنجاح')
        return redirect('manage_comments')
    
    return JsonResponse({'success': False, 'message': 'طريقة الطلب غير صحيحة'})


@staff_member_required
def bulk_approve_comments(request):
    """قبول مجموعة من التعليقات دفعة واحدة"""
    if request.method == 'POST':
        comment_ids = request.POST.getlist('comment_ids')
        
        if comment_ids:
            Comment.objects.filter(id__in=comment_ids).update(is_approved=True)
            messages.success(request, f'تم قبول {len(comment_ids)} تعليق')
        else:
            messages.warning(request, 'لم يتم تحديد أي تعليق')
        
        return redirect('manage_comments')
    
    return redirect('manage_comments')


@staff_member_required
def bulk_delete_comments(request):
    """حذف مجموعة من التعليقات دفعة واحدة"""
    if request.method == 'POST':
        comment_ids = request.POST.getlist('comment_ids')
        
        if comment_ids:
            deleted_count, _ = Comment.objects.filter(id__in=comment_ids).delete()
            messages.success(request, f'تم حذف {deleted_count} تعليق')
        else:
            messages.warning(request, 'لم يتم تحديد أي تعليق')
        
        return redirect('manage_comments')
    
    return redirect('manage_comments')


@login_required
def view_comments_on_my_posts(request):
    """عرض التعليقات على منشورات المستخدم"""
    user = request.user
    
    if user.is_staff or (hasattr(user, 'profile') and user.profile.is_content_editor):
        if user.is_superuser:
            comments = Comment.objects.all().select_related('post')
        elif user.is_staff:
            comments = Comment.objects.filter(
                Q(post__author=user) | Q(is_approved=False)
            ).select_related('post')
        else:
            comments = Comment.objects.filter(post__author=user).select_related('post')
    else:
        messages.error(request, 'ليس لديك صلاحية لعرض التعليقات')
        return redirect('dashboard')
    
    paginator = Paginator(comments.order_by('-created_at'), 20)
    page = request.GET.get('page', 1)
    
    try:
        comments_page = paginator.page(page)
    except PageNotAnInteger:
        comments_page = paginator.page(1)
    except EmptyPage:
        comments_page = paginator.page(paginator.num_pages)
    
    return render(request, 'my_comments.html', {
        'comments': comments_page,
        'title': 'التعليقات على منشوراتي',
        'total_comments': comments.count(),
        'approved_comments': comments.filter(is_approved=True).count(),
        'pending_comments': comments.filter(is_approved=False).count(),
    })


# ======== إدارة المستخدمين والإعدادات ========
@user_passes_test(lambda u: u.is_superuser)
def admin_settings(request):
    """إعدادات الأدمن المتقدمة"""
    try:
        site_settings = SiteSettings.objects.first()
    except SiteSettings.DoesNotExist:
        site_settings = SiteSettings.objects.create()
    
    if request.method == 'POST':
        form = SiteSettingsForm(request.POST, instance=site_settings)
        if form.is_valid():
            form.save()
            messages.success(request, 'تم حفظ الإعدادات بنجاح')
            return redirect('admin_settings')
    else:
        form = SiteSettingsForm(instance=site_settings)
    
    return render(request, 'admin/admin_settings.html', {
        'form': form,
        'title': 'إعدادات الموقع المتقدمة',
        'site_settings': site_settings,
    })


@user_passes_test(lambda u: u.is_superuser)
def manage_users(request):
    """إدارة المستخدمين"""
    users = User.objects.all().select_related('profile').order_by('-date_joined')
    
    paginator = Paginator(users, 20)
    page = request.GET.get('page', 1)
    
    try:
        users_page = paginator.page(page)
    except PageNotAnInteger:
        users_page = paginator.page(1)
    except EmptyPage:
        users_page = paginator.page(paginator.num_pages)
    
    return render(request, 'admin/manage_users.html', {
        'users': users_page,
        'title': 'إدارة المستخدمين',
        'total_users': users.count(),
        'staff_users': users.filter(is_staff=True).count(),
        'superusers': users.filter(is_superuser=True).count(),
        'content_editors': UserProfile.objects.filter(is_content_editor=True).count(),
    })


@user_passes_test(lambda u: u.is_superuser)
def edit_user_role(request, user_id):
    """تعديل دور المستخدم"""
    user = get_object_or_404(User, id=user_id)
    profile, created = UserProfile.objects.get_or_create(user=user)
    
    if request.method == 'POST':
        form = UserRoleForm(request.POST, instance=profile)
        if form.is_valid():
            profile = form.save()
            
            user.is_staff = profile.is_content_editor
            user.save()
            
            messages.success(request, f'تم تحديث صلاحيات المستخدم {user.username}')
            return redirect('manage_users')
    else:
        form = UserRoleForm(instance=profile)
    
    return render(request, 'admin/edit_user_role.html', {
        'form': form,
        'user': user,
        'title': f'تعديل صلاحيات المستخدم: {user.username}'
    })


@user_passes_test(lambda u: u.is_superuser)
def system_logs(request):
    """عرض سجلات النظام"""
    logs = SystemLog.objects.all().order_by('-created_at')[:100]
    
    return render(request, 'admin/system_logs.html', {
        'logs': logs,
        'title': 'سجلات النظام',
        'log_count': logs.count(),
        'error_count': logs.filter(log_type='error').count(),
        'warning_count': logs.filter(log_type='warning').count(),
        'info_count': logs.filter(log_type='info').count(),
    })


# ======== Staff فقط ========
@user_passes_test(lambda u: u.is_staff)
def staff_dashboard(request):
    """لوحة تحكم الـ Staff"""
    user = request.user
    
    total_posts = Post.objects.count()
    published_posts = Post.objects.filter(status='published').count()
    draft_posts = Post.objects.filter(status='draft').count()
    recent_posts = Post.objects.all().order_by('-created_at')[:5]
    new_comments = Comment.objects.filter(is_approved=False).count()
    total_views = Post.objects.aggregate(total_views=Sum('views'))['total_views'] or 0
    
    return render(request, 'staff/dashboard.html', {
        'title': 'لوحة تحكم Staff',
        'total_posts': total_posts,
        'published_posts': published_posts,
        'draft_posts': draft_posts,
        'recent_posts': recent_posts,
        'new_comments': new_comments,
        'total_views': total_views,
        'user': user,
    })


@user_passes_test(lambda u: u.is_staff)
def staff_manage_posts(request):
    """إدارة المنشورات للـ Staff"""
    posts = Post.objects.all().select_related('author', 'category').order_by('-created_at')
    
    paginator = Paginator(posts, 20)
    page = request.GET.get('page', 1)
    
    try:
        posts_page = paginator.page(page)
    except PageNotAnInteger:
        posts_page = paginator.page(1)
    except EmptyPage:
        posts_page = paginator.page(paginator.num_pages)
    
    return render(request, 'staff/manage_posts.html', {
        'posts': posts_page,
        'title': 'إدارة المنشورات',
        'total_posts': posts.count(),
        'published_posts': posts.filter(status='published').count(),
        'draft_posts': posts.filter(status='draft').count(),
    })


# ======== وظائف إضافية ========
@login_required
def delete_account(request):
    """حذف حساب المستخدم"""
    if request.method == 'POST':
        password = request.POST.get('password', '')
        
        user = authenticate(username=request.user.username, password=password)
        
        if user is not None:
            user.delete()
            logout(request)
            messages.success(request, 'تم حذف حسابك بنجاح. نأسف لرحيلك!')
            return redirect('home')
        else:
            messages.error(request, 'كلمة المرور غير صحيحة!')
    
    return render(request, 'auth/delete_account.html')


def check_username(request):
    """التحقق من توفر اسم المستخدم (AJAX)"""
    if request.method == 'GET' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        username = request.GET.get('username', '')
        
        if username:
            exists = User.objects.filter(username__iexact=username).exists()
            return HttpResponse(json.dumps({'exists': exists}), content_type='application/json')
    
    return HttpResponse(json.dumps({'error': 'Invalid request'}), content_type='application/json')


def check_email(request):
    """التحقق من توفر البريد الإلكتروني (AJAX)"""
    if request.method == 'GET' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        email = request.GET.get('email', '')
        
        if email:
            exists = User.objects.filter(email__iexact=email).exists()
            return HttpResponse(json.dumps({'exists': exists}), content_type='application/json')
    
    return HttpResponse(json.dumps({'error': 'Invalid request'}), content_type='application/json')


# ======== معالجات الأخطاء ========
def handler404(request, exception):
    return render(request, 'errors/404.html', status=404)


def handler500(request):
    return render(request, 'errors/500.html', status=500)


def handler403(request, exception):
    return render(request, 'errors/403.html', status=403)


def handler400(request, exception):
    return render(request, 'errors/400.html', status=400)


