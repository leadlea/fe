#!/usr/bin/env bash
set -euo pipefail
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
mkdir -p certs
if [ ! -f certs/localhost.key ]; then
  openssl req -x509 -newkey rsa:2048 -nodes -keyout certs/localhost.key -out certs/localhost.crt -days 365 -subj "/CN=localhost"
fi
export ALLOWED_ORIGINS="https://*.github.io,https://github.io,https://leadlea.github.io,https://localhost"
uvicorn app:app --host 127.0.0.1 --port 8443 --ssl-keyfile certs/localhost.key --ssl-certfile certs/localhost.crt
