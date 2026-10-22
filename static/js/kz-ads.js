/*
 * يحسب "ظهور" الإعلان عند رؤيته فعلاً: 50% منه داخل الشاشة لمدة ثانية متصلة (معيار IAB/MRC).
 * إعلانات المعاينة (data-preview) لا تُحسب.
 */
(function () {
    'use strict';
    var ads = document.querySelectorAll('.kz-ad[data-ad-id]:not([data-preview])');
    if (!ads.length) return;
    var seen = {};
    function count(id) {
        if (seen[id]) return;
        seen[id] = true;
        var url = '/ads/impression/' + id + '/';
        if (navigator.sendBeacon) { navigator.sendBeacon(url, ''); }
        else { fetch(url, { method: 'POST', keepalive: true, credentials: 'same-origin' }); }
    }
    if (!('IntersectionObserver' in window)) {
        ads.forEach(function (a) { count(a.getAttribute('data-ad-id')); });
        return;
    }
    var timers = {};
    var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
            var id = e.target.getAttribute('data-ad-id');
            if (e.isIntersecting && e.intersectionRatio >= 0.5) {
                if (!timers[id] && !seen[id]) timers[id] = setTimeout(function () { count(id); io.unobserve(e.target); }, 1000);
            } else if (timers[id]) {
                clearTimeout(timers[id]); timers[id] = null;
            }
        });
    }, { threshold: [0, 0.5, 1] });
    ads.forEach(function (a) { io.observe(a); });
})();
