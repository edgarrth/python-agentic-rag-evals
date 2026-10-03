#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
export PYTHONPATH="${PYTHONPATH:-}:backend/src"

printf '\n[1/4] Verificación de código, pytest, Angular y Compose\n'
./infrastructure/scripts/verify.sh

printf '\n[2/4] Suite full + benchmark de las cinco estrategias RAG\n'
python backend/scripts/run_evals_matrix.py

printf '\n[3/4] Aplicación Docker para pruebas HTTP/Promptfoo\n'
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose es obligatorio para ejecutar Promptfoo dentro de test_all.sh."
  exit 1
fi
# --wait permite que Compose construya, levante y espere healthchecks sin usar -d explícitamente.
docker compose up --wait

printf '\n[4/4] Promptfoo: prompts, formato, safety y red team\n'
docker compose --profile eval-tools run --rm promptfoo

printf '\nTodas las pruebas finalizaron. La aplicación permanece levantada para inspección.\n'
printf 'Frontend: http://localhost:8080\nBackend:  http://localhost:8000\n'
printf 'Matriz Evals: .runtime/evals-matrix.json\n'
