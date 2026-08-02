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
    initial_equity?: number;
    final_equity?: number;
    total_return: number;
    sharpe_ratio: number | null;
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
  runs: Partial<Record<StrategyName, VisualizationRun>>;
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

export function findVisualizationDatasetContext(
  symbol: string,
  version: string,
  contentSHA256: string,
): { asset: Asset; period: Period } | undefined {
  const entry = Object.entries(artifact.datasets).find(
    ([, dataset]) =>
      dataset.symbol === symbol &&
      dataset.dataset_version === version &&
      dataset.content_sha256 === contentSHA256,
  );
  if (!entry) return undefined;
  const [asset, period] = entry[0].split("_");
  if (
    (asset !== "btc" && asset !== "eth") ||
    (period !== "evaluation" && period !== "development")
  ) {
    return undefined;
  }
  return { asset, period };
}

export const visualizationSchemaVersion = artifact.schema_version;
