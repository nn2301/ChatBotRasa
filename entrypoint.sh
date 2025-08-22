#!/usr/bin/env bash
set -e

# Strip ngoặc kép nếu MONGO_URI như dạng "mongodb+srv://...."
if [[ "${MONGO_URI}" == \"*\" ]]; then
  export MONGO_URI=${MONGO_URI%\"}
  export MONGO_URI=${MONGO_URI#\"}
fi

# PORT từ env của Render, fallback 8080
: "${PORT:=8080}"
echo "Starting Rasa SDK actions on 0.0.0.0:${PORT} ..."
exec start --actions actions --host 0.0.0.0 --port "${PORT}"
