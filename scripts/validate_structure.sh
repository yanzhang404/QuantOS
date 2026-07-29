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
  pyproject.toml
  docs/adr/0001-modular-monolith.md
  docs/adr/0002-go-python-boundary.md
  docs/adr/0003-parquet-duckdb.md
  docs/adr/0004-next-bar-open-execution.md
  docs/adr/0005-chronological-out-of-sample-selection.md
  docs/adr/0006-read-only-research-workspace.md
  apps/web/package.json
  docs/market-data/kline-schema.md
)

required_directories=(
  apps/web
  apps/web/app
  apps/api
  apps/worker
  apps/worker/src/quantos_cli
  services/market-data
  services/market-data/src/quantos_market_data
  services/backtest/src/quantos_backtest
  services/research
  services/research/src/quantos_research
  services/backtest
  services/execution
  services/risk
  services/agent
  packages/strategy-sdk
  packages/strategy-sdk/src/quantos_strategy
  packages/event-schema
  packages/event-schema/src/quantos_events
  packages/exchange-sdk
  packages/metrics
  packages/metrics/src/quantos_metrics
  packages/common
  docs/vision
  docs/architecture
  docs/adr
  deployments/docker
  deployments/compose
  examples
  examples/backtest
  tests
  tests/market_data
  tests/backtest
  tests/research
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

if git ls-files -co --exclude-standard | grep -E \
  '(^|/)(\.env($|\.)|id_rsa$|.*\.(pem|key)$)' >/dev/null; then
  echo "potential secret file detected in repository contents" >&2
  failed=1
fi

if [[ "$failed" -ne 0 ]]; then
  exit 1
fi

echo "QuantOS repository structure is valid."
