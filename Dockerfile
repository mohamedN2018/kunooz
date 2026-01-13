FROM nginx:alpine

# حذف ملفات nginx الافتراضية
RUN rm -rf /usr/share/nginx/html/*

# نسخ index.html فقط
COPY index.html /usr/share/nginx/html/index.html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
