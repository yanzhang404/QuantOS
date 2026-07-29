import visualization from "../../../examples/backtest/donchian-atr-study/visualization.json";
import type { Asset, Period, StrategyName } from "./research-data";

export type Bar = {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type EquityPoint = {
  time: string;
  equity: number;
  drawdown: number;
  position: number;
};

export type Fill = {
  time: string;
  side: "buy" | "sell";
  price: number;
  quantity: number;
  fee: number;
  reason: string;
};

export type VisualizationRun = {
  run_id: string;
  metrics: {
    total_return: number;
    sharpe_ratio: number;
    max_drawdown: number;
    trade_count: number;
    fill_count: number;
    fees_paid: number;
  };
  equity: EquityPoint[];
  fills: Fill[];
};

export type VisualizationDataset = {
  symbol: string;
  interval: string;
  period: string;
  dataset_version: string;
  content_sha256: string;
  bars: Bar[];
  runs: Record<StrategyName, VisualizationRun>;
};

type Artifact = {
  schema_version: string;
  generated_from: string;
  as_of: string;
  window_bars: number;
  datasets: Record<string, VisualizationDataset>;
};

const artifact = visualization as Artifact;

export function getVisualizationDataset(
  asset: Asset,
  period: Period,
): VisualizationDataset {
  return artifact.datasets[`${asset}_${period}`];
}

export const visualizationSchemaVersion = artifact.schema_version;
