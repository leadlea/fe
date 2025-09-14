#!/usr/bin/env bash
set -euo pipefail
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export ALLOWED_ORIGINS="https://*.github.io,https://github.io,https://leadlea.github.io,https://localhost"
uvicorn app:app --host 127.0.0.1 --port 8000
