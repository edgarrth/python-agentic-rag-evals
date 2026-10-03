#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../frontend"

if [[ ! -d node_modules ]]; then
  if [[ -f package-lock.json ]]; then
    npm ci --no-audit --no-fund
  else
    npm install --no-audit --no-fund
  fi
fi

exec npm start
