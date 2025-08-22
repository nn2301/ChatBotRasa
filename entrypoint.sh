#!/usr/bin/env bash
set -e

# Strip ngoặc kép nếu ai đó lỡ nhập MONGO_URI="mongodb+srv://..."
if [[ "${MONGO_URI}" == \"*\" ]]; then
  export MONGO_URI=${MONGO_URI%\"}
  export MONGO_URI=${MONGO_URI#\"}
fi

# Render sẽ đưa PORT vào env, bạn đang giữ PORT=8080 -> OK
: "${PORT:=8080}"

echo "Starting Rasa server on 0.0.0.0:${PORT} ..."
exec rasa run \
  --enable-api \
  --cors "*" \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --endpoints /app/endpoints.yml \
  --credentials /app/credentials.yml
