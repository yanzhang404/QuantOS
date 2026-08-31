# Research

Research work begins with a falsifiable hypothesis and ends with versioned
inputs, executable code, metrics, artifacts, and review notes. Notebook-only
state is not a completed experiment.

## Chronological strategy study

The research workflow creates contiguous train, validation, and untouched test
segments. A bounded strategy adapter supplies the canonical parameter grid,
warmup, deterministic tie-break, adjacent-grid neighbors, and implementation.
The shared runner ranks candidates only by validation Sharpe ratio, evaluates
only the selected winner on the holdout, then repeats that holdout with doubled
fees and slippage.

EMA Cross uses the default adapter:

```bash
uv run quantos experiment sweep \
  --dataset "<immutable-dataset-version>" \
  --fast 10,20,30 \
  --slow 40,50,80 \
  --train-ratio 0.6 \
  --validation-ratio 0.2 \
  --min-bars 100 \
  --output-root artifacts
```

Donchian ATR exposes its own entry, exit, and ATR grids while recording fixed
volatility sizing assumptions in every Run:

```bash
uv run quantos experiment sweep \
  --strategy donchian-atr \
  --dataset "<immutable-dataset-version>" \
  --entry 20,40,60 \
  --exit 10,20 \
  --atr 14,20 \
  --target-annual-volatility 0.20 \
  --max-exposure 1 \
  --rebalance-threshold 0.05 \
  --output-root artifacts
```

The command writes individual content-addressed backtest runs below
`artifacts/experiments/` and a content-addressed study below
`artifacts/studies/` containing:

- `study.json` with dataset identity, exact split ranges, selection policy,
  winner, and linked run IDs;
- `leaderboard.csv` with train and validation results for every candidate;
- `review.md` with deterministic checks for short samples, low trade counts,
  out-of-sample degradation, drawdown, cost sensitivity, and boundary winners.

The holdout result is deliberately excluded from parameter ranking. A study is
reused when its dataset, grid, split, assumptions, and linked run identities are
unchanged.

## Compare and review

```bash
uv run quantos experiment compare \
  --run artifacts/experiments/<run-a>/run.json \
  --run artifacts/experiments/<run-b>/run.json

uv run quantos review show \
  --study artifacts/studies/<study-id>
```

Comparison emits normalized JSON including evaluation ranges, assumptions, and
metrics. Review findings are evidence prompts, not claims that a strategy is
safe or profitable.

## Robustness gates

The robustness workflow repeats chronological selection across expanding
walk-forward folds, checks strategy-specific adjacent parameters on the
original holdout, reuses the doubled-cost holdout, and applies the fixed winner
to an aligned peer market:

```bash
uv run quantos experiment robustness \
  --strategy donchian-atr \
  --dataset "<BTC immutable dataset>" \
  --peer-dataset "<ETH immutable dataset>" \
  --entry 20,40,60 \
  --exit 10,20 \
  --atr 14,20 \
  --folds 3 \
  --output-root artifacts
```

The output is a content-addressed review. A failed gate means the evidence is
insufficient for promotion; a passed review never promotes a strategy or
authorizes trading automatically. See [ADR-0017](../adr/0017-deterministic-robustness-gates.md).
Strategy-specific adapter ownership is defined by
[ADR-0029](../adr/0029-strategy-specific-research-adapters.md).

### Adapter acceptance evidence

The first real-data Donchian adapter smoke used bundle
`59a3d9414579304a`, BTCUSDT member `54b725ed325487c6`, and ETHUSDT member
`1c1dc028e9e9c56a` at `4h`, with entry `20,30`, exit `10,15`, ATR `14`, and
three folds. It produced `robustness-review.v2` review `62e5fd1af3d7fd1e`:
walk-forward passed, while neighboring parameters, doubled costs, and multiple
markets failed, so the overall review correctly remained failed. Generated
market rows and experiment artifacts stay outside Git; the exact command above
reproduces the evidence by substituting those immutable member paths and grid
values. This smoke validates the adapter and gate boundary, not the strategy's
profitability.

## Candidate handoff

An Agent hypothesis enters research through `candidate-proposal.v1`, not by
editing the approved Strategy Library. The guarded lifecycle separately records
implementation symbols and deterministic tests, then accepts a passed
robustness artifact only when its strategy slug matches the proposal. Approval
or rejection requires a named human and rationale. See the command workflow in
[`services/agent`](../../services/agent/README.md) and
[ADR-0018](../adr/0018-guarded-candidate-lifecycle.md).

Candidate attention is rate-limited separately from lifecycle state. The local
draft scheduler accepts only narrow proposed candidates, prepares at most two
review packages per UTC ISO week, and never opens or merges a remote pull
request. See
[ADR-0019](../adr/0019-rate-limited-candidate-draft-scheduling.md).

## Formal strategy studies

- [Donchian ATR strategy study](donchian-atr-study.md)
