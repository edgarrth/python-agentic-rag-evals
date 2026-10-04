#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

echo 'Se detiene la pila asociada al compose actual.'
docker compose down --remove-orphans || true

for name in axiz-evals-frontend axiz-evals-backend axiz-evals-dataset-seed axiz-evals-python-base axiz-evals-node-base axiz-evals-qdrant axiz-evals-memgraph; do
  if docker ps -a --format '{{.Names}}' | grep -qx "$name"; then
    echo "Se elimina contenedor previo no asociado correctamente: $name"
    docker rm -f "$name" >/dev/null
  fi
done

echo 'Se reconstruyen las imágenes :local sobre el mismo tag y se recrean los contenedores.'
docker compose up --build --force-recreate
