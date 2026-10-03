#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."

docker compose build python-base node-base

echo "Imágenes base Python y Node/Angular disponibles."
