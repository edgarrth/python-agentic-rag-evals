#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
export PYTHONPATH="${PYTHONPATH:-}:frontend/src"
exec python -m pe.axiz.payments_evals_ui.main
