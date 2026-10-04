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

compose_path = pathlib.Path('compose.yaml')
compose = yaml.safe_load(compose_path.read_text(encoding='utf-8'))
services = compose['services']
expected = {
    'python-base', 'node-base', 'qdrant', 'memgraph',
    'backend', 'dataset-seed', 'frontend', 'promptfoo'
}
assert expected <= set(services)

for service_name in ('python-base', 'node-base', 'backend', 'dataset-seed', 'frontend'):
    assert services[service_name].get('pull_policy') == 'build', service_name

assert services['python-base']['image'] == 'axiz/payments-evals-python-base:local'
assert services['node-base']['image'] == 'axiz/payments-evals-node-base:local'
assert services['backend']['image'] == 'axiz/payments-evals-backend:local'
assert services['dataset-seed']['image'] == 'axiz/payments-evals-backend:local'
assert services['frontend']['image'] == 'axiz/payments-evals-frontend:local'
assert services['promptfoo']['image'] == 'axiz/payments-evals-promptfoo:local'

backend_contexts = services['backend']['build']['additional_contexts']
frontend_contexts = services['frontend']['build']['additional_contexts']
assert backend_contexts['python_base'] == 'service:python-base'
assert frontend_contexts['node_base'] == 'service:node-base'
assert services['frontend']['depends_on']['dataset-seed']['condition'] == 'service_completed_successfully'
assert services['backend']['env_file'][0]['path'] == './.env'

print('Docker Compose: tags :local y build automático válidos')
PY

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  docker compose config >/dev/null
  echo "Docker Compose: configuración semántica válida"
else
  echo "Docker no está disponible; se omite docker compose config."
fi
