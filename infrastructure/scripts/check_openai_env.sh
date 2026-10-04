#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
BACKEND_CONTAINER="axiz-evals-backend"

cd "$ROOT_DIR"
printf 'Verificación de configuración OpenAI\n'
printf '%s\n' '---------------------------------'

if [[ ! -f "$ENV_FILE" ]]; then
  echo "[ERROR] No existe $ENV_FILE"
  echo "Crea el archivo con: cp .env.example .env"
  exit 1
fi

if python - "$ENV_FILE" <<'PY'
import sys
from pathlib import Path
path = Path(sys.argv[1])
configured = False
for raw in path.read_text(encoding='utf-8').splitlines():
    line = raw.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    key, value = line.split('=', 1)
    if key.strip() == 'OPENAI_API_KEY':
        value = value.strip().strip('"').strip("'")
        configured = bool(value)
        break
raise SystemExit(0 if configured else 1)
PY
then
  echo '[OK] .env contiene OPENAI_API_KEY con un valor no vacío.'
else
  echo '[ERROR] OPENAI_API_KEY está ausente o vacía en .env.'
  exit 1
fi

if docker compose config --services 2>/dev/null | grep -qx 'backend'; then
  echo '[OK] El compose raíz reconoce el servicio backend.'
else
  echo '[ERROR] El compose actual no reconoce el servicio backend.'
  echo 'Asegúrate de ejecutar el comando desde la raíz de esta versión del proyecto.'
  exit 1
fi

if docker ps --format '{{.Names}}' | grep -qx "$BACKEND_CONTAINER"; then
  IMAGE="$(docker inspect -f '{{.Config.Image}}' "$BACKEND_CONTAINER" 2>/dev/null || true)"
  echo "[INFO] Contenedor activo: $BACKEND_CONTAINER ($IMAGE)"
  if docker exec "$BACKEND_CONTAINER" python -c 'import os,sys; sys.exit(0 if os.getenv("OPENAI_API_KEY") else 1)'; then
    echo '[OK] El contenedor backend recibió OPENAI_API_KEY.'
  else
    echo '[ERROR] El contenedor backend NO recibió OPENAI_API_KEY.'
    echo 'Recrea el backend después de modificar .env: docker compose up --force-recreate backend'
    exit 1
  fi
else
  echo "[WARN] $BACKEND_CONTAINER no está ejecutándose; no se pudo inspeccionar su entorno."
fi

if docker compose ps --status running --services 2>/dev/null | grep -qx 'backend'; then
  if docker compose exec backend python -c 'import os,sys; sys.exit(0 if os.getenv("OPENAI_API_KEY") else 1)'; then
    echo '[OK] docker compose exec backend reconoce el servicio y la clave.'
  else
    echo '[ERROR] El servicio backend existe en Compose pero no ve OPENAI_API_KEY.'
    exit 1
  fi
elif docker ps --format '{{.Names}}' | grep -qx "$BACKEND_CONTAINER"; then
  echo '[WARN] El contenedor está activo pero el Compose actual no lo considera su servicio backend.'
  echo 'Esto suele indicar que quedó una pila de una versión anterior. Ejecuta ./infrastructure/scripts/recreate_stack.sh'
fi

if command -v curl >/dev/null 2>&1 && curl -fsS http://localhost:8000/api/v1/runtime/options >/tmp/axiz-runtime-options.json 2>/dev/null; then
  python - <<'PY'
import json
from pathlib import Path
payload = json.loads(Path('/tmp/axiz-runtime-options.json').read_text())
configured = bool(payload.get('external_judges', {}).get('openai_key_configured'))
models = payload.get('models', {}).get('openai', [])
defaults = payload.get('defaults', {})
print('[INFO] OpenAI key reportada por API:', configured)
print('[INFO] Modelo SUT por defecto:', defaults.get('model'))
print('[INFO] Modelo Judge por defecto:', defaults.get('judge_model'))
print('[INFO] Modelos OpenAI:', ', '.join(models) if models else '(ninguno)')
if not configured:
    raise SystemExit(1)
PY
  echo '[OK] El endpoint runtime confirma que OpenAI está configurado.'
else
  echo '[WARN] No se pudo consultar http://localhost:8000/api/v1/runtime/options.'
fi
