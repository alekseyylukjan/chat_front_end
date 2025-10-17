# Используем официальный образ nginx
FROM nginx:alpine

# Копируем файлы сайта в папку, обслуживаемую nginx
COPY ./ /usr/share/nginx/html

# Экспонируем порт 80 (по умолчанию для nginx)
EXPOSE 80

# Запуск nginx в foreground (по умолчанию в образе)
CMD ["nginx", "-g", "daemon off;"]
