#!/usr/bin/env bash
set -e

# Strip quotes nếu MONGO_URI như "mongodb+srv://..."
if [[ "${MONGO_URI}" == \"*\" ]]; then
  export MONGO_URI=${MONGO_URI%\"}
  export MONGO_URI=${MONGO_URI#\"}
fi

# Lấy PORT do Render cấp, local fallback 8080
: "${PORT:=8080}"

# Chỉ định rõ model để Rasa nạp nhanh và bind cổng sớm
MODEL_PATH=${RASA_MODEL_PATH:-models/20250822-165338-charitable-pilot.tar.gz}

echo "Starting Rasa server on 0.0.0.0:${PORT} ..."
exec rasa run \
  --enable-api \
  --cors "*" \
  -i 0.0.0.0 \
  -p "${PORT}" \
  --endpoints endpoints.yml \
  --credentials credentials.yml \
  --model "${MODEL_PATH}"
  # muốn log chi tiết hơn: thêm -v hoặc -vv ở DÒNG TRÊN (trước dấu \)
