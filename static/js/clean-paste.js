/**
 * تنظيف محتوى الصق من Word والمصادر الأخرى
 */
document.addEventListener('DOMContentLoaded', function() {
    const cleanPaste = function(e) {
        // السماح بالصق العادي إذا كان Ctrl+V
        if (e.ctrlKey && e.key === 'v') {
            setTimeout(function() {
                const editor = e.target.closest('[contenteditable="true"]') || e.target;
                if (editor && editor.innerHTML) {
                    // تنظيف محتوى Word
                    let content = editor.innerHTML;
                    
                    // إزالة أنماط Word غير المرغوب فيها
                    content = content.replace(/<o:p>.*?<\/o:p>/g, '');
                    content = content.replace(/<!--.*?-->/g, '');
                    content = content.replace(/class="[^"]*"/g, '');
                    content = content.replace(/style="[^"]*"/g, '');
                    content = content.replace(/<span[^>]*>/g, '');
                    content = content.replace(/<\/span>/g, '');
                    content = content.replace(/<font[^>]*>/g, '');
                    content = content.replace(/<\/font>/g, '');
                    
                    // تحسين الفقرات
                    content = content.replace(/<p[^>]*>/g, '<p>');
                    
                    editor.innerHTML = content;
                }
            }, 10);
        }
    };
    
    // تطبيق على جميع حقول النصوص القابلة للتحرير
    document.querySelectorAll('textarea, [contenteditable="true"]').forEach(el => {
        el.addEventListener('keydown', cleanPaste);
    });
});

// // clean-paste.js - نظام تنظيف النص التلقائي
// class CleanPaste {
//     constructor() {
//         this.init();
//     }
    
//     init() {
//         // الانتظار حتى تحميل الصفحة
//         if (document.readyState === 'loading') {
//             document.addEventListener('DOMContentLoaded', () => this.setup());
//         } else {
//             this.setup();
//         }
//     }
    
//     setup() {
//         // جميع العناصر التي تقبل النص
//         const elements = document.querySelectorAll('input, textarea, [contenteditable]');
        
//         elements.forEach(element => {
//             // تجاهل حقول كلمات المرور
//             if (element.type === 'password') return;
            
//             // إضافة مستمع حدث paste
//             element.addEventListener('paste', this.handlePaste.bind(this));
            
//             // تنظيف النص الحالي إذا كان يحتوي HTML
//             if (element.value && this.containsHTML(element.value)) {
//                 element.value = this.stripHTML(element.value);
//             }
//         });
        
//         console.log('🧹 CleanPaste: تم تفعيل النظام على ' + elements.length + ' عنصر');
//     }
    
//     handlePaste(e) {
//         e.preventDefault();
        
//         const element = e.target;
//         const clipboardData = e.clipboardData || window.clipboardData;
//         const text = clipboardData.getData('text/plain');
//         const cleanText = this.stripHTML(text);
        
//         if (element.isContentEditable) {
//             // لعناصر contenteditable
//             document.execCommand('insertText', false, cleanText);
//         } else {
//             // للحقول العادية
//             const start = element.selectionStart;
//             const end = element.selectionEnd;
            
//             element.value = element.value.substring(0, start) + 
//                            cleanText + 
//                            element.value.substring(end);
            
//             // تحديث موضع المؤشر
//             const newPos = start + cleanText.length;
//             element.setSelectionRange(newPos, newPos);
//         }
        
//         // تشغيل الأحداث المرتبطة
//         element.dispatchEvent(new Event('input', { bubbles: true }));
//         element.dispatchEvent(new Event('change', { bubbles: true }));
//     }
    
//     containsHTML(text) {
//         return /<\/?[a-z][\s\S]*>/i.test(text) || /&[a-z]+;/i.test(text);
//     }
    
//     stripHTML(text) {
//         if (!text) return '';
        
//         return text
//             .replace(/<\/?[^>]+(>|$)/g, "")  // إزالة tags
//             .replace(/&nbsp;/g, ' ')         // استبدال &nbsp;
//             .replace(/&amp;/g, '&')          // استبدال &amp;
//             .replace(/&lt;/g, '<')           // استبدال &lt;
//             .replace(/&gt;/g, '>')           // استبدال &gt;
//             .replace(/&quot;/g, '"')         // استبدال &quot;
//             .replace(/&#39;/g, "'")          // استبدال &#39;
//             .replace(/\s+/g, ' ')            // إزالة مسافات متعددة
//             .trim();                         // تقليم الأطراف
//     }
// }

// // تفعيل النظام تلقائياً
// window.addEventListener('load', () => {
//     window.cleanPaste = new CleanPaste();
// });




