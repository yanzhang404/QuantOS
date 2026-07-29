import study from "../../../examples/backtest/donchian-atr-study/results.json";

export type Asset = "btc" | "eth";
export type Period = "development" | "evaluation";
export type StrategyName = "buy-and-hold" | "ema-cross" | "donchian-atr";

export type Run = {
  dataset: string;
  strategy: StrategyName;
  run_id: string;
  total_return: number;
  sharpe_ratio: number;
  max_drawdown: number;
  trade_count: number;
  fill_count: number;
  fees_paid: number;
  cost_stress?: string;
};

type Dataset = {
  content_sha256: string;
  dataset_version: string;
  rows: number;
};

const runs = study.runs as Run[];
const datasets = study.datasets as Record<string, Dataset>;

export const strategyNames: Record<StrategyName, string> = {
  "buy-and-hold": "Buy & Hold",
  "ema-cross": "EMA 20 / 50",
  "donchian-atr": "Donchian ATR",
};

export function getRuns(asset: Asset, period: Period): Run[] {
  const dataset = `${asset}_${period}`;
  return runs.filter((run) => run.dataset === dataset && !run.cost_stress);
}

export function getStressRun(asset: Asset): Run | undefined {
  return runs.find(
    (run) =>
      run.dataset === `${asset}_evaluation` &&
      run.strategy === "donchian-atr" &&
      run.cost_stress === "2x",
  );
}

export function getDataset(asset: Asset, period: Period): Dataset {
  return datasets[`${asset}_${period}`];
}

export const studyAsOf = study.as_of;
