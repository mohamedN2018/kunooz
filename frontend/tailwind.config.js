/** Tailwind مبني مسبقاً بدل cdn.tailwindcss.com (غير مخصص للإنتاج وكان يولّد CSS في متصفح كل زائر).
 *  إعادة البناء بعد تعديل القوالب:  cd frontend && npm ci && npm run build
 */
module.exports = {
  darkMode: 'class',
  content: [
    '../templates/**/*.html',
    '../core/**/*.py',
    '../static/js/**/*.js',
  ],
  // كلاسات JavaScript تُكتب كنصوص كاملة داخل القوالب فيلتقطها المسح؛ هذه احتياط إضافي
  safelist: ['bg-green-500', 'bg-gray-100', 'border-green-500', 'translate-x-full', 'opacity-0'],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#eff6ff', 100: '#dbeafe', 200: '#bfdbfe', 300: '#93c5fd', 400: '#60a5fa',
          500: '#3b82f6', 600: '#2563eb', 700: '#1d4ed8', 800: '#1e40af', 900: '#1e3a8a',
        },
      },
      fontFamily: { cairo: ['Cairo', 'sans-serif'] },
    },
  },
  plugins: [],
};
