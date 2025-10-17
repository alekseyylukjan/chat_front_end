#!/bin/sh
set -e

# ===== Defaults (можно переопределить в UI Dockhost) =====
: "${ACCESS_CODE:=777}"
: "${API_URL:=https://example-backend.my.dockhost.ru/ask}"
: "${ENV_JS_PATH:=/usr/share/nginx/html/env.js}"

# ===== Генерим env.js, откуда фронт читает переменные =====
cat > "$ENV_JS_PATH" <<EOF
window.__ENV = {
  ACCESS_CODE: "${ACCESS_CODE}",
  API_URL: "${API_URL}"
};
EOF

echo "[entrypoint] env.js создан: $ENV_JS_PATH"
echo "[entrypoint] API_URL=${API_URL}"

# ===== (Опционально) Шаблоны nginx через envsubst =====
# Если вы положите *.template в /etc/nginx/templates и зададите
# NGINX_ENVSUBST_OUTPUT_DIR, то они будут отрендерены сюда:
if [ -n "${NGINX_ENVSUBST_OUTPUT_DIR:-}" ] && [ -d /etc/nginx/templates ]; then
  echo "[entrypoint] Рендерим nginx-шаблоны → ${NGINX_ENVSUBST_OUTPUT_DIR}"
  mkdir -p "${NGINX_ENVSUBST_OUTPUT_DIR}"
  for tpl in /etc/nginx/templates/*.template; do
    [ -e "$tpl" ] || continue
    out="${NGINX_ENVSUBST_OUTPUT_DIR}/$(basename "${tpl%.template}")"
    envsubst < "$tpl" > "$out"
    echo "  - $tpl -> $out"
  done
fi

# ===== Запуск nginx =====
exec nginx -g "daemon off;"
