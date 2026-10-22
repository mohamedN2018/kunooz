/*
 * يفعّل محرر Jodit (MIT) على كل textarea[data-rich-editor].
 * بديل CKEditor 4 المنتهي الدعم. رفع الصور عبر /editor/upload-image/ (للمحررين فقط).
 */
(function () {
    'use strict';

    function csrfToken() {
        var input = document.querySelector('input[name=csrfmiddlewaretoken]');
        if (input) return input.value;
        var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return m ? decodeURIComponent(m[1]) : '';
    }

    function isDark() {
        return document.documentElement.classList.contains('dark');
    }

    var BUTTONS = [
        'undo', 'redo', '|',
        'paragraph', 'bold', 'italic', 'underline', 'strikethrough', '|',
        'ul', 'ol', 'outdent', 'indent', '|',
        'align', 'brush', 'font', 'fontsize', '|',
        'link', 'image', 'video', 'table', 'hr', 'quote', '|',
        'eraser', 'source', 'fullsize', 'preview'
    ];

    function init(textarea) {
        if (textarea.dataset.editorReady || typeof Jodit === 'undefined') return;
        textarea.dataset.editorReady = '1';

        var editor = Jodit.make(textarea, {
            language: 'ar',
            direction: 'rtl',
            theme: isDark() ? 'dark' : 'default',
            minHeight: 420,
            height: 480,
            // المحرر يُنشأ داخل تبويب مخفي (عرضه 0) فكان الوضع التكيفي يختار شريط الموبايل المختصر
            toolbarAdaptive: false,
            toolbarSticky: true,
            toolbarStickyOffset: 70,
            buttons: BUTTONS,
            buttonsMD: BUTTONS,
            buttonsSM: ['bold', 'italic', 'underline', '|', 'ul', 'ol', '|', 'paragraph', 'link', 'image', '|', 'undo', 'redo', 'dots'],
            buttonsXS: ['bold', 'italic', '|', 'ul', 'ol', '|', 'link', 'image', 'dots'],
            placeholder: 'اكتب محتوى المنشور هنا...',
            showCharsCounter: true,
            showWordsCounter: true,
            showXPathInStatusbar: false,
            askBeforePasteHTML: false,
            askBeforePasteFromWord: false,
            defaultActionOnPaste: 'insert_clear_html',
            beautifyHTML: false,
            spellcheck: true,
            // لا تُحفظ الصور كـ base64 داخل المحتوى (تضخم قاعدة البيانات)؛ تُرفع للسيرفر
            uploader: {
                url: '/editor/upload-image/',
                insertImageAsBase64URI: false,
                imagesExtensions: ['jpg', 'jpeg', 'png', 'gif', 'webp'],
                headers: { 'X-CSRFToken': csrfToken() },
                withCredentials: true,
                filesVariableName: function (i) { return 'files[' + i + ']'; },
                isSuccess: function (resp) { return resp && resp.success; },
                getMessage: function (resp) {
                    return (resp && resp.data && resp.data.messages || []).join(' ');
                },
                process: function (resp) {
                    return {
                        files: resp.data.files || [],
                        baseurl: resp.data.baseurl || '',
                        isImages: resp.data.isImages || [],
                        messages: resp.data.messages || [],
                        error: resp.success ? 0 : 1
                    };
                },
                error: function (e) {
                    this.j.message.error(e.message || 'تعذر رفع الصورة', 5000);
                }
            },
            image: { editSrc: true, editTitle: true, editAlt: true, editLink: true, editSize: true, editClass: false, editStyle: false, editId: false },
            link: { noFollowCheckbox: true, openInNewTabCheckbox: true },
            controls: {
                paragraph: {
                    list: {
                        p: 'فقرة', h2: 'عنوان رئيسي', h3: 'عنوان فرعي', h4: 'عنوان صغير',
                        blockquote: 'اقتباس', pre: 'كود'
                    }
                }
            },
            style: { fontFamily: 'Cairo, sans-serif', fontSize: '16px', lineHeight: '1.9' }
        });

        // المحتوى يُكتب في الـ textarea تلقائياً؛ نتأكد قبل الإرسال أيضاً
        var form = textarea.form;
        if (form) {
            form.addEventListener('submit', function () { textarea.value = editor.value; }, true);
        }
        textarea.joditEditor = editor;
    }

    function initAll() {
        document.querySelectorAll('textarea[data-rich-editor]').forEach(init);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAll);
    } else {
        initAll();
    }
    window.initPostEditors = initAll;
})();
