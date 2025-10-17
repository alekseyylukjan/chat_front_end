# Используем официальный образ nginx
FROM nginx:alpine

# Включаем полезные пакеты (не обязательно, но удобно для отладки)
RUN apk add --no-cache bash

# Копируем сайт
COPY ./index.html /usr/share/nginx/html/index.html
COPY ./styles.css /usr/share/nginx/html/styles.css
COPY ./app.js /usr/share/nginx/html/app.js

# entrypoint с генерацией env.js на основе переменных окружения
COPY ./docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Папка для env.js, создаётся entrypoint'ом
# (index.html уже ссылается на ./env.js)
# EXPOSE 80 — порт по умолчанию nginx
EXPOSE 80

# Запуск nginx через наш entrypoint (сначала создаст env.js)
CMD ["/docker-entrypoint.sh"]
