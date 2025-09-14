#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/hitl_orchestrator_local"
exec ./start.sh
