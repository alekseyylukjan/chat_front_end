#!/bin/sh
set -e

: "${ACCESS_CODE:=777}"
: "${API_URL:=http://localhost:8000/ask}"
: "${ENV_JS_PATH:=/usr/share/nginx/html/env.js}"

cat > "$ENV_JS_PATH" <<EOF
window.__ENV = {
  ACCESS_CODE: "${ACCESS_CODE}",
  API_URL: "${API_URL}"
};
EOF

echo "[40-env-js] env.js создан: $ENV_JS_PATH (ACCESS_CODE and API_URL подставлены)"
