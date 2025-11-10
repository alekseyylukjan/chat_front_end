FROM nginx:alpine

# Статика
COPY ./index.html /usr/share/nginx/html/index.html
COPY ./styles.css /usr/share/nginx/html/styles.css
COPY ./app.js /usr/share/nginx/html/app.js
COPY ./favicon.svg /usr/share/nginx/html/favicon.svg

# Шаблон конфига nginx (см. ниже)
COPY ./nginx/default.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 80
# ENTRYPOINT/CMD оставляем стандартные из образа nginx
