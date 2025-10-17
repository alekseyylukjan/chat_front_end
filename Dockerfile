FROM nginx:alpine

# Статика
COPY ./index.html /usr/share/nginx/html/index.html
COPY ./styles.css /usr/share/nginx/html/styles.css
COPY ./app.js /usr/share/nginx/html/app.js
COPY ./favicon.svg /usr/share/nginx/html/favicon.svg

# Наш скрипт, который выполнит штатный entrypoint nginx
COPY ./docker-entrypoint.d/40-env-js.sh /docker-entrypoint.d/40-env-js.sh
RUN chmod +x /docker-entrypoint.d/40-env-js.sh

EXPOSE 80
# НИЧЕГО не меняем: остаётся стандартный ENTRYPOINT/CMD из образа nginx
