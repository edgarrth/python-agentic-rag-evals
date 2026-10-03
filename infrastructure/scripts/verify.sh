#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
export PYTHONPATH="${PYTHONPATH:-}:backend/src:frontend/src"
python -m compileall -q backend/src frontend/src datasets
pytest -q
python - <<'PY'
import pathlib, yaml
path = pathlib.Path('infrastructure/docker-compose.yml')
data = yaml.safe_load(path.read_text())
assert {'qdrant','memgraph','backend','dataset-seed','frontend','promptfoo'} <= set(data['services'])
print('docker-compose.yml: estructura YAML válida')
PY
