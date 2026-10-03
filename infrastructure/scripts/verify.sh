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

root_compose = pathlib.Path('compose.yaml')
infrastructure_compose = pathlib.Path('infrastructure/docker-compose.yml')

root_data = yaml.safe_load(root_compose.read_text(encoding='utf-8'))
assert root_data == {'include': [{'path': 'infrastructure/docker-compose.yml'}]}

compose = yaml.safe_load(infrastructure_compose.read_text(encoding='utf-8'))
services = compose['services']
expected = {
    'python-base', 'node-base', 'qdrant', 'memgraph',
    'backend', 'dataset-seed', 'frontend', 'promptfoo'
}
assert expected <= set(services)

for service_name in ('python-base', 'node-base', 'backend', 'dataset-seed', 'frontend'):
    assert services[service_name].get('pull_policy') == 'build', service_name

backend_contexts = services['backend']['build']['additional_contexts']
frontend_contexts = services['frontend']['build']['additional_contexts']
assert backend_contexts['python_base'] == 'service:python-base'
assert frontend_contexts['node_base'] == 'service:node-base'
assert services['frontend']['depends_on']['dataset-seed']['condition'] == 'service_completed_successfully'

print('Docker Compose: estructura de build automático válida')
PY

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  docker compose config >/dev/null
  echo "Docker Compose: configuración semántica válida"
else
  echo "Docker no está disponible; se omite docker compose config."
fi
