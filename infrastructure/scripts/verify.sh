#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
export PYTHONPATH="${PYTHONPATH:-}:backend/src"

python -m compileall -q backend/src datasets
pytest -q

pushd frontend >/dev/null
if [[ ! -d node_modules ]]; then
  if [[ -f package-lock.json ]]; then
    npm ci --no-audit --no-fund
  else
    npm install --no-audit --no-fund
  fi
fi
npm run build
popd >/dev/null

python - <<'PY'
import pathlib
import yaml
path = pathlib.Path('infrastructure/docker-compose.yml')
data = yaml.safe_load(path.read_text())
assert {'qdrant','memgraph','backend','dataset-seed','frontend','promptfoo'} <= set(data['services'])
print('docker-compose.yml: estructura YAML válida')
PY
