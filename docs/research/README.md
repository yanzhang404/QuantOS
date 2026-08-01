# Research

Research work begins with a falsifiable hypothesis and ends with versioned
inputs, executable code, metrics, artifacts, and review notes. Notebook-only
state is not a completed experiment.

## Chronological EMA study

The research workflow creates contiguous train, validation, and untouched test
segments. It runs every valid `fast < slow` candidate on train and validation,
ranks candidates only by validation Sharpe ratio, evaluates only the selected
winner on the holdout, then repeats that holdout with doubled fees and slippage.

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
walk-forward folds, checks adjacent EMA parameters on the original holdout,
reuses the doubled-cost holdout, and applies the fixed winner to an aligned peer
market:

```bash
uv run quantos experiment robustness \
  --dataset "<BTC immutable dataset>" \
  --peer-dataset "<ETH immutable dataset>" \
  --fast 10,20,30 \
  --slow 40,50,80 \
  --folds 3 \
  --output-root artifacts
```

The output is a content-addressed review. A failed gate means the evidence is
insufficient for promotion; a passed review never promotes a strategy or
authorizes trading automatically. See [ADR-0017](../adr/0017-deterministic-robustness-gates.md).

## Candidate handoff

An Agent hypothesis enters research through `candidate-proposal.v1`, not by
editing the approved Strategy Library. The guarded lifecycle separately records
implementation symbols and deterministic tests, then accepts a passed
robustness artifact only when its strategy slug matches the proposal. Approval
or rejection requires a named human and rationale. See the command workflow in
[`services/agent`](../../services/agent/README.md) and
[ADR-0018](../adr/0018-guarded-candidate-lifecycle.md).

## Formal strategy studies

- [Donchian ATR strategy study](donchian-atr-study.md)
