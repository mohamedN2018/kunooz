# analytics/middleware.py
import geoip2.database
import geoip2.errors
from django.utils import timezone
from django.db import models
import user_agents
from datetime import timedelta
import os
from django.conf import settings
import json
import uuid
import logging
import ipaddress
import re
from datetime import datetime, timezone as dt_timezone
from urllib.parse import urlparse
from .models import VisitorSession, PageView, Country, RealTimeVisitor

logger = logging.getLogger(__name__)

SESSION_TIMEOUT_SECONDS = 30 * 60
# أدوات وفحوص آلية لا تُعرّفها مكتبة user_agents كبوتات (ظهرت فعلاً في البيانات: curl و HeadlessChrome)
NON_HUMAN_UA = re.compile(
    r'curl|wget|python-requests|python-urllib|httpx|aiohttp|go-http-client|java/|okhttp|node-fetch|axios|'
    r'headless|phantomjs|puppeteer|playwright|selenium|lighthouse|pagespeed|uptime|monitor|healthcheck|'
    r'pingdom|statuscake|zabbix|nagios|prometheus|dokploy|traefik|docker|kube-probe|scanner|nikto|nmap|masscan|zgrab',
    re.I)
COUNTRY_NAMES_AR = {
    'EG': 'مصر', 'SA': 'السعودية', 'AE': 'الإمارات', 'QA': 'قطر', 'KW': 'الكويت', 'OM': 'عُمان', 'BH': 'البحرين',
    'JO': 'الأردن', 'LB': 'لبنان', 'SY': 'سوريا', 'IQ': 'العراق', 'YE': 'اليمن', 'SD': 'السودان', 'DZ': 'الجزائر',
    'MA': 'المغرب', 'TN': 'تونس', 'LY': 'ليبيا', 'PS': 'فلسطين', 'MR': 'موريتانيا', 'SO': 'الصومال',
    'US': 'الولايات المتحدة', 'GB': 'المملكة المتحدة', 'FR': 'فرنسا', 'DE': 'ألمانيا', 'TR': 'تركيا',
    'IN': 'الهند', 'CN': 'الصين', 'RU': 'روسيا', 'BR': 'البرازيل', 'CA': 'كندا', 'NL': 'هولندا', 'IT': 'إيطاليا',
    'ES': 'إسبانيا', 'MY': 'ماليزيا', 'PK': 'باكستان', 'ID': 'إندونيسيا',
}
VISITOR_COOKIE = 'kz_vid'
SEARCH_ENGINES = ('google.', 'bing.', 'yahoo.', 'duckduckgo.', 'yandex.', 'baidu.', 'ecosia.')
SOCIAL_SITES = ('facebook.', 'fb.', 'instagram.', 't.co', 'twitter.', 'x.com', 'linkedin.', 'youtube.',
                'tiktok.', 'whatsapp.', 'telegram.', 't.me', 'reddit.', 'pinterest.', 'snapchat.')


def external_referrer(request):
    """المصدر الخارجي فقط (التنقل داخل الموقع ليس مصدراً)."""
    ref = (request.META.get('HTTP_REFERER') or '')[:200]
    if not ref:
        return None
    host = urlparse(ref).netloc.lower()
    if not host or host == request.get_host().lower():
        return None
    return ref


def classify_source(referrer):
    if not referrer:
        return 'direct'
    host = urlparse(referrer).netloc.lower()
    if any(s in host for s in SEARCH_ENGINES):
        return 'search'
    if any(s in host for s in SOCIAL_SITES):
        return 'social'
    return 'referral'


def close_session(session_key, ended_at=None):
    """إغلاق جلسة (خروج الزائر): يُسجَّل وقت الخروج ويُحذف من المتصلين الآن."""
    try:
        sid = uuid.UUID(str(session_key))
    except ValueError:
        return
    ended_at = ended_at or timezone.now()
    session = VisitorSession.objects.filter(session_id=sid, is_active=True).first()
    if not session:
        return
    VisitorSession.objects.filter(pk=session.pk).update(
        is_active=False, end_time=ended_at,
        total_time_spent=max(ended_at - session.start_time, timedelta(0)),
    )
    RealTimeVisitor.objects.filter(session=session).delete()

class AdvancedAnalyticsMiddleware:
    """Middleware متقدم لتتبع الزوار بدقة"""
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.geoip_reader = None
        
        # تحميل قاعدة بيانات GeoIP2 إذا كانت موجودة
        geoip_path = getattr(settings, 'GEOIP_PATH', None)
        if geoip_path and os.path.exists(geoip_path):
            try:
                self.geoip_reader = geoip2.database.Reader(geoip_path)
            except:
                self.geoip_reader = None
    
    def __call__(self, request):
        # تجنب تتبع طلبات AJAX أو static أو admin
        if self.should_skip_tracking(request):
            return self.get_response(request)

        user_agent_string = request.META.get('HTTP_USER_AGENT', '')
        user_agent = user_agents.parse(user_agent_string)
        if user_agent.is_bot or NON_HUMAN_UA.search(user_agent_string) or not user_agent_string:
            return self.get_response(request)
        # موظفو الموقع لا يُحسبون زواراً (كانت زياراتهم للوحات التحكم تضخم الأرقام)
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated and user.is_staff:
            return self.get_response(request)
        # الصفحات غير الموجودة (فحوص آلية مثل /v1/models/ و /wp-login.php) ليست زيارات
        if not self._is_real_page(request.path):
            return self.get_response(request)

        # session_id في VisitorSession هو UUID؛ مفتاح جلسة Django ليس UUID
        # (كان ذلك يُفشل كل عمليات الإنشاء بصمت فتظل التحليلات فارغة)
        # جلسة الزيارة تنتهي بعد 30 دقيقة خمول (نفس معيار Google Analytics) فتبدأ زيارة جديدة
        now = timezone.now()
        session_key = request.session.get('analytics_sid')
        last_ts = request.session.get('analytics_last')
        if session_key and last_ts and now.timestamp() - last_ts > SESSION_TIMEOUT_SECONDS:
            close_session(session_key, ended_at=datetime.fromtimestamp(last_ts, tz=dt_timezone.utc))
            session_key = None
        if not session_key:
            session_key = str(uuid.uuid4())
            request.session['analytics_sid'] = session_key
        request.session['analytics_last'] = now.timestamp()

        # معرف ثابت للمتصفح (كوكي سنة) = عدد الزوار الفريدين والعائدين
        visitor_id = request.COOKIES.get(VISITOR_COOKIE)
        try:
            visitor_id = str(uuid.UUID(visitor_id)) if visitor_id else None
        except ValueError:
            visitor_id = None
        new_visitor_cookie = None
        if not visitor_id:
            visitor_id = new_visitor_cookie = str(uuid.uuid4())
        request.analytics_visitor_id = visitor_id
        ip_address = self.get_client_ip(request)
        
        # معلومات الجهاز والمتصفح
        device_info = self.get_device_info(user_agent)
        
        # معلومات جغرافية: GeoIP2 إن وُجدت قاعدته (GEOIP_PATH)، وإلا ترويسة الدولة من CDN (Cloudflare)
        geo_info = self.get_geo_info(self.get_raw_ip(request)) or self.get_header_country(request)
        
        # التتبع يجب ألا يُسقط الصفحة أبداً
        visitor_session = None
        try:
            visitor_session = self.create_or_update_session(
                request, session_key, ip_address, user_agent_string, device_info, geo_info
            )
            if request.method == 'GET':
                self.track_page_view(request, visitor_session)
            self.update_realtime_visitor(visitor_session, request)
        except Exception:
            logger.exception("فشل تتبع الزيارة")

        # إضافة الجلسة إلى request للوصول إليها في views
        request.visitor_session = visitor_session

        response = self.get_response(request)
        if new_visitor_cookie:
            response.set_cookie(VISITOR_COOKIE, new_visitor_cookie, max_age=365 * 24 * 3600,
                                samesite='Lax', secure=request.is_secure(), httponly=True)
        return response
    
    @staticmethod
    def _is_real_page(path):
        from django.urls import Resolver404, resolve
        try:
            resolve(path)
            return True
        except Resolver404:
            return False

    def should_skip_tracking(self, request):
        """التحقق إذا كان يجب تخطي التتبع"""
        if not settings.ANALYTICS_SETTINGS.get('ENABLE_TRACKING', True):
            return True

        skip_paths = [
            '/admin/', '/static/', '/media/',
            '/api/analytics/', '/analytics/', '/ads/', '/favicon.ico',
            '/health', '/robots.txt', '/sitemap.xml', '/autocomplete_search/',
            '/check-username/', '/check-email/', '/t/', '/feed/', '/editor/',
        ]

        if any(request.path.startswith(path) for path in skip_paths):
            return True
        # طلبات AJAX/fetch لا تُحسب زيارات
        return request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    def get_client_ip(self, request):
        """استخراج عنوان IP الحقيقي (مع إخفاء آخر جزء إذا كان ANONYMIZE_IP مفعلاً)"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        try:
            addr = ipaddress.ip_address(ip)
        except (ValueError, TypeError):
            return '0.0.0.0'
        if settings.ANALYTICS_SETTINGS.get('ANONYMIZE_IP', True):
            prefix = 24 if addr.version == 4 else 48
            addr = ipaddress.ip_network(f"{addr}/{prefix}", strict=False).network_address
        return str(addr)
    
    def get_raw_ip(self, request):
        # GeoIP يحتاج العنوان الكامل؛ لا يُخزَّن، المخزَّن هو المُخفى
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        return forwarded.split(',')[0].strip() if forwarded else request.META.get('REMOTE_ADDR')

    def get_header_country(self, request):
        code = (request.META.get('HTTP_CF_IPCOUNTRY') or request.META.get('HTTP_X_COUNTRY_CODE') or '').upper()
        if len(code) != 2 or not code.isalpha() or code in ('XX', 'T1'):
            return None
        return {'country_code': code, 'country_name': code, 'country_name_ar': COUNTRY_NAMES_AR.get(code, code),
                'flag_emoji': self.get_flag_emoji(code), 'region': None, 'city': None,
                'latitude': None, 'longitude': None, 'timezone': None}

    def get_device_info(self, user_agent):
        """استخراج معلومات الجهاز من User Agent"""
        return {
            'device_type': 'mobile' if user_agent.is_mobile else 
                          'tablet' if user_agent.is_tablet else 
                          'desktop',
            'browser': user_agent.browser.family,
            'browser_version': user_agent.browser.version_string,
            'os': user_agent.os.family,
            'os_version': user_agent.os.version_string,
            'is_bot': user_agent.is_bot,
        }
    
    def get_geo_info(self, ip_address):
        """الحصول على المعلومات الجغرافية"""
        if not self.geoip_reader:
            return None
        
        try:
            response = self.geoip_reader.city(ip_address)
            
            # الحصول على كود الدولة وإيموجي العلم
            country_code = response.country.iso_code
            flag_emoji = self.get_flag_emoji(country_code)
            
            return {
                'country_code': country_code,
                'country_name': response.country.name,
                'country_name_ar': self.translate_country_name(response.country.name),
                'flag_emoji': flag_emoji,
                'region': response.subdivisions.most_specific.name if response.subdivisions else None,
                'city': response.city.name if response.city else None,
                'latitude': response.location.latitude,
                'longitude': response.location.longitude,
                'timezone': response.location.time_zone,
            }
        except:
            return None
    
    def get_flag_emoji(self, country_code):
        """تحويل كود الدولة إلى إيموجي علم"""
        if not country_code or len(country_code) != 2:
            return "🌐"
        
        # تحويل ASCII إلى إيموجي علم
        try:
            base = ord('🇦') - ord('A')
            emoji = ''.join(chr(ord(c.upper()) + base) for c in country_code)
            return emoji
        except:
            return "🌐"
    
    def translate_country_name(self, country_name):
        """ترجمة أسماء الدول إلى العربية"""
        translations = {
            'Egypt': 'مصر',
            'Saudi Arabia': 'السعودية',
            'United Arab Emirates': 'الإمارات',
            'Qatar': 'قطر',
            'Kuwait': 'الكويت',
            'Oman': 'عُمان',
            'Bahrain': 'البحرين',
            'Jordan': 'الأردن',
            'Lebanon': 'لبنان',
            'Syria': 'سوريا',
            'Iraq': 'العراق',
            'Yemen': 'اليمن',
            'Sudan': 'السودان',
            'Algeria': 'الجزائر',
            'Morocco': 'المغرب',
            'Tunisia': 'تونس',
            'Libya': 'ليبيا',
            'Palestine': 'فلسطين',
            'United States': 'الولايات المتحدة',
            'United Kingdom': 'المملكة المتحدة',
            'France': 'فرنسا',
            'Germany': 'ألمانيا',
            'Turkey': 'تركيا',
            'India': 'الهند',
            'China': 'الصين',
            'Russia': 'روسيا',
            'Brazil': 'البرازيل',
        }
        
        return translations.get(country_name, country_name)
    
    def create_or_update_session(self, request, session_key, ip_address, user_agent_string, device_info, geo_info):
        """إنشاء أو تحديث جلسة الزائر"""
        try:
            # الجلسة نفسها (حتى لو أُغلقت بإشارة مغادرة ثم عاد خلال 30 دقيقة، مثل تحديث الصفحة → تُستأنف)
            session = VisitorSession.objects.filter(session_id=session_key).first()
            if session and not session.is_active:
                VisitorSession.objects.filter(pk=session.pk).update(is_active=True, end_time=None)
                session.is_active, session.end_time = True, None
            
            if not session:
                # إنشاء دولة جديدة إذا لم تكن موجودة
                country = None
                if geo_info:
                    country, _ = Country.objects.get_or_create(
                        code=geo_info['country_code'],
                        defaults={
                            'name': geo_info['country_name_ar'],
                            'flag_emoji': geo_info['flag_emoji']
                        }
                    )
                
                # إنشاء جلسة جديدة
                session = VisitorSession.objects.create(
                    session_id=session_key,
                    user=request.user if request.user.is_authenticated else None,
                    ip_address=ip_address,
                    user_agent=user_agent_string,
                    device_type=device_info['device_type'],
                    browser=device_info['browser'],
                    browser_version=device_info['browser_version'],
                    os=device_info['os'],
                    os_version=device_info['os_version'],
                    country=country,
                    region=geo_info['region'] if geo_info else None,
                    city=geo_info['city'] if geo_info else None,
                    latitude=geo_info['latitude'] if geo_info else None,
                    longitude=geo_info['longitude'] if geo_info else None,
                    referrer=external_referrer(request),
                    landing_page=request.build_absolute_uri()[:200],
                    visitor_id=request.analytics_visitor_id,
                    is_returning=VisitorSession.objects.filter(visitor_id=request.analytics_visitor_id).exists(),
                    entry_source=classify_source(external_referrer(request)),
                    last_seen=timezone.now(),
                    metadata={
                        'is_bot': device_info['is_bot'],
                        'timezone': geo_info.get('timezone') if geo_info else None,
                    }
                )
            
            return session

        except Exception:
            logger.exception("فشل إنشاء جلسة زائر")
            return None
    
    def track_page_view(self, request, visitor_session):
        """تتبع مشاهدة الصفحة الحالية"""
        if not visitor_session:
            return
        
        # حساب الوقت المنقضي في الصفحة السابقة
        self.update_previous_page_time(visitor_session)
        
        # تسجيل مشاهدة الصفحة الجديدة
        PageView.objects.create(
            session=visitor_session,
            url=request.build_absolute_uri()[:200],
            title=(self.get_page_title(request) or request.path)[:500],
            time_spent=timedelta(0),  # سيتم تحديثه لاحقاً
            scroll_depth=0,
            is_bounce=False
        )
        
        # زيادة عدد صفحات الجلسة (الجلسة الجديدة تبدأ بـ page_count=1 فلا نزيد أول صفحة)
        if visitor_session.pageviews.count() > 1:
            VisitorSession.objects.filter(pk=visitor_session.pk).update(page_count=models.F('page_count') + 1)
            visitor_session.page_count += 1
        now = timezone.now()
        VisitorSession.objects.filter(pk=visitor_session.pk).update(
            total_time_spent=now - visitor_session.start_time,
            last_seen=now,
            exit_page=request.build_absolute_uri()[:200],
            is_active=True,
        )
    
    def update_previous_page_time(self, visitor_session):
        """تحديث الوقت المنقضي في الصفحة السابقة"""
        if not visitor_session:
            return
        
        # البحث عن آخر مشاهدة صفحة لم يتم تحديث وقتها
        last_pageview = PageView.objects.filter(
            session=visitor_session
        ).order_by('-timestamp').first()
        
        if last_pageview and last_pageview.time_spent.total_seconds() == 0:
            # حساب الوقت المنقضي
            time_spent = timezone.now() - last_pageview.timestamp
            
            # تحديث وقت الصفحة
            last_pageview.time_spent = time_spent
            
            # تحديد إذا كانت الصفحة ارتداد (مشاهدة صفحة واحدة فقط)
            if visitor_session.page_count == 1:
                last_pageview.is_bounce = True
            
            last_pageview.save()
    
    def update_realtime_visitor(self, visitor_session, request):
        """تحديث بيانات الزائر الفوري"""
        if not visitor_session:
            return
        
        RealTimeVisitor.objects.update_or_create(
            session=visitor_session,
            defaults={'current_page': request.build_absolute_uri()[:200]},
        )
    
    def get_page_title(self, request):
        """استخراج عنوان الصفحة"""
        # يمكن تحسين هذا لاستخراج العنوان الفعلي من response
        return None
    
    def process_exception(self, request, exception):
        """معالجة الاستثناءات"""
        pass
    
    def __del__(self):
        """إغلاق قارئ GeoIP عند الإغلاق"""
        if self.geoip_reader:
            self.geoip_reader.close()