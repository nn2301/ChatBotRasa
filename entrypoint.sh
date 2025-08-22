#!/usr/bin/env bash
set -e

# Bỏ ngoặc kép nếu MONGO_URI là "mongodb+srv://..."
if [[ "${MONGO_URI}" == \"*\" ]]; then
  export MONGO_URI=${MONGO_URI%\"}
  export MONGO_URI=${MONGO_URI#\"}
fi

: "${PORT:=8080}"

echo "Starting Rasa SDK actions on port ${PORT} ..."
exec python -m rasa_sdk.endpoint \
  --actions actions \
  -p "${PORT}"
