#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."

docker build -f infrastructure/docker/Dockerfile.python-base -t axiz/payments-evals-python-base:1.0.0 .
docker build -f infrastructure/docker/Dockerfile.node-base -t axiz/payments-evals-node-base:1.0.0 .
docker build -f infrastructure/docker/Dockerfile.promptfoo -t axiz/payments-evals-promptfoo:0.123.1 .
echo "Imágenes base disponibles: Python, Node/Angular y Promptfoo."
