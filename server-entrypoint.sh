#!/usr/bin/env bash
set -e

# Strip ngoặc kép nếu MONGO_URI kiểu "mongodb+srv://..."
if [[ "${MONGO_URI}" == \"*\" ]]; then
  export MONGO_URI=${MONGO_URI%\"}
  export MONGO_URI=${MONGO_URI#\"}
fi

# PORT của Render (fallback 8080)
: "${PORT:=8080}"

echo "Starting Rasa server on 0.0.0.0:${PORT} ..."
exec rasa run \
  --enable-api \
  --cors "*" \
  -i 0.0.0.0 \
  -p "${PORT}" \
  --endpoints endpoints.yml \
  --credentials credentials.yml
