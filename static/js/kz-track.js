/* نبض كل 30 ثانية أثناء ظهور الصفحة + إشارة عند المغادرة → "متصل الآن" و"خرج" بدقة في لوحة التحليلات. */
(function () {
    'use strict';
    if (!navigator.sendBeacon || /bot|crawl|spider/i.test(navigator.userAgent)) return;
    var PING = '/t/ping/', LEAVE = '/t/leave/', timer = null, left = false;
    function send(url) { try { navigator.sendBeacon(url, ''); } catch (e) {} }
    function start() { if (!timer) timer = setInterval(function () { send(PING); }, 30000); }
    function stop() { clearInterval(timer); timer = null; }
    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'visible') { left = false; send(PING); start(); } else { stop(); }
    });
    // pagehide يعمل على الموبايل وعند إغلاق التبويب؛ التنقل داخل الموقع يُستأنف بالطلب التالي تلقائياً
    window.addEventListener('pagehide', function () { if (!left) { left = true; send(LEAVE); } });
    if (document.visibilityState === 'visible') start();
})();
