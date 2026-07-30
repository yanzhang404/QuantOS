# Agent Service

Owns tool-gated AI workflows and evidence links. Agents do not receive authority
to activate live trading.

Strategy discovery follows an explicit lifecycle:

```text
hypothesis → candidate implementation → deterministic tests
           → robustness review → human promotion decision
```

An agent may propose strategy code and parameter manifests, run historical
experiments, and summarize evidence. It may not silently mark a candidate
validated, promote it to a production signal, or bypass the shared risk and
backtest boundaries.
