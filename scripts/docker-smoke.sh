#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Unique, disposable resources; never touch the developer's default stack.
project="alpha-smoke-$(date +%s)-$$"
compose=(docker compose -p "$project" -f docker-compose.yml -f docker-compose.smoke.yml)
mkdir -p reports/docker-smoke
cleanup() {
  status=$?
  "${compose[@]}" logs --no-color > reports/docker-smoke/compose.log 2>&1 || true
  "${compose[@]}" down --volumes --remove-orphans || true
  exit "$status"
}
trap cleanup EXIT
"${compose[@]}" up -d --build
"${compose[@]}" exec -T api python -m tests.docker_smoke run
"${compose[@]}" restart api worker
"${compose[@]}" exec -T api python -m tests.docker_smoke verify
"${compose[@]}" cp api:/data/smoke-report.md reports/docker-smoke/benchmark.md
