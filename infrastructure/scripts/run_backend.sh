#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
export PYTHONPATH="${PYTHONPATH:-}:backend/src"
exec uvicorn pe.axiz.payments_evals_lab.main:app --host 0.0.0.0 --port "${BACKEND_PORT:-8000}" --no-access-log
