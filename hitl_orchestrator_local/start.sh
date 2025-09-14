#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export OUTPUT_ROOT="${OUTPUT_ROOT:-$HOME/fe/out}"
export ALLOWED_ORIGINS="${ALLOWED_ORIGINS:-https://*.github.io,https://github.io,https://leadlea.github.io,https://localhost}"
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip --disable-pip-version-check
pip install --disable-pip-version-check -r requirements.txt
# 依存（PDF/CSV/アップロード）
pip install --disable-pip-version-check python-multipart pandas==2.2.2 numpy==2.0.2 openpyxl==3.1.5 PyMuPDF==1.24.10
mkdir -p certs
if command -v mkcert >/dev/null 2>&1; then
  [[ -f certs/localhost.crt ]] || mkcert -key-file certs/localhost.key -cert-file certs/localhost.crt localhost 127.0.0.1 ::1
else
  [[ -f certs/localhost.crt ]] || openssl req -x509 -newkey rsa:2048 -nodes -keyout certs/localhost.key -out certs/localhost.crt -days 365 -subj "/CN=localhost"
fi
uvicorn app:app --host 127.0.0.1 --port "${PORT:-8443}" --ssl-keyfile certs/localhost.key --ssl-certfile certs/localhost.crt
