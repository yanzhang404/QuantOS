#!/usr/bin/env bash
set -euo pipefail

required_files=(
  README.md
  PROJECT_CONTEXT.md
  AGENTS.md
  ROADMAP.md
  ARCHITECTURE.md
  CONTRIBUTING.md
  LICENSE
  compose.yaml
  docs/adr/0001-modular-monolith.md
  docs/adr/0002-go-python-boundary.md
  docs/adr/0003-parquet-duckdb.md
  docs/adr/0004-a-share-market-radar.md
  docs/adr/0005-us-equity-live-radar.md
  docs/adr/0006-top-candidate-option-snapshots.md
  docs/adr/0007-radar-outcome-evaluation.md
  services/market-data/pyproject.toml
  services/market-data/src/quantos_market_data/us_radar.py
  apps/worker/us_market_radar.py
)

required_directories=(
  apps/web
  apps/api
  apps/worker
  services/market-data
  services/research
  services/backtest
  services/execution
  services/risk
  services/agent
  packages/strategy-sdk
  packages/event-schema
  packages/exchange-sdk
  packages/metrics
  packages/common
  docs/vision
  docs/architecture
  docs/adr
  deployments/docker
  deployments/compose
  examples
  tests
)

failed=0

for path in "${required_files[@]}"; do
  if [[ ! -s "$path" ]]; then
    echo "missing or empty required file: $path" >&2
    failed=1
  fi
done

for path in "${required_directories[@]}"; do
  if [[ ! -d "$path" ]]; then
    echo "missing required directory: $path" >&2
    failed=1
  fi
done

if git ls-files -co --exclude-standard \
  | grep -Ev '(^|/)\.env\.example$' \
  | grep -E '(^|/)(\.env($|\.)|id_rsa$|.*\.(pem|key)$)' >/dev/null; then
  echo "potential secret file detected in repository contents" >&2
  failed=1
fi

if [[ "$failed" -ne 0 ]]; then
  exit 1
fi

echo "QuantOS repository structure is valid."
