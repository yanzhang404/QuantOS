import type { StrategyName } from "./research-data";

export type StrategyInterval = "5m" | "15m" | "1h" | "4h" | "1d";
export type StrategyCategory =
  | "trend"
  | "benchmark"
  | "mean-reversion"
  | "intraday";
export type StrategyStage = "candidate" | "validated" | "benchmark";

export type StrategyParameter = {
  key: string;
  kind: "integer" | "decimal";
  label: string;
  default: number | string;
  minimum: number | string;
  maximum: number | string;
};

export type StrategyDefinition = {
  name: StrategyName;
  version: "1.0.0";
  label: string;
  description: string;
  category: StrategyCategory;
  stage: StrategyStage;
  implementation: string;
  supported_intervals: StrategyInterval[];
  parameters: StrategyParameter[];
};

export const fallbackStrategyCatalog: StrategyDefinition[] = [
  {
    name: "donchian-atr",
    version: "1.0.0",
    label: "Donchian ATR",
    description: "Channel breakout with ATR volatility-targeted exposure.",
    category: "trend",
    stage: "candidate",
    implementation: "quantos_backtest.strategies.DonchianAtrStrategy",
    supported_intervals: ["1h", "4h", "1d"],
    parameters: [
      parameter("entry_period", "integer", "Entry period", 55, 2, 2000),
      parameter("exit_period", "integer", "Exit period", 20, 1, 2000),
      parameter("atr_period", "integer", "ATR period", 20, 2, 2000),
      parameter(
        "target_annual_volatility",
        "decimal",
        "Target annual volatility",
        "0.20",
        "0.01",
        "2",
      ),
      parameter("max_exposure", "decimal", "Maximum exposure", "1", "0.01", "1"),
      parameter(
        "rebalance_threshold",
        "decimal",
        "Rebalance threshold",
        "0.05",
        "0",
        "1",
      ),
    ],
  },
  {
    name: "ema-cross",
    version: "1.0.0",
    label: "EMA Cross",
    description: "Long-only trend state from fast and slow exponential averages.",
    category: "trend",
    stage: "candidate",
    implementation: "quantos_backtest.strategies.EmaCrossStrategy",
    supported_intervals: ["15m", "1h", "4h", "1d"],
    parameters: [
      parameter("fast_period", "integer", "Fast period", 20, 1, 1000),
      parameter("slow_period", "integer", "Slow period", 50, 2, 2000),
    ],
  },
  {
    name: "buy-and-hold",
    version: "1.0.0",
    label: "Buy & Hold",
    description: "Passive long-only market exposure benchmark.",
    category: "benchmark",
    stage: "benchmark",
    implementation: "quantos_backtest.strategies.BuyAndHoldStrategy",
    supported_intervals: ["5m", "15m", "1h", "4h", "1d"],
    parameters: [
      parameter(
        "target_exposure",
        "decimal",
        "Target exposure",
        "1",
        "0.01",
        "1",
      ),
    ],
  },
];

export const parameterLabelsZh: Record<string, string> = {
  target_exposure: "目标仓位",
  fast_period: "快速 EMA 周期",
  slow_period: "慢速 EMA 周期",
  entry_period: "入场周期",
  exit_period: "退出周期",
  atr_period: "ATR 周期",
  target_annual_volatility: "目标年化波动率",
  max_exposure: "策略最大仓位",
  rebalance_threshold: "再平衡阈值",
};

function parameter(
  key: string,
  kind: StrategyParameter["kind"],
  label: string,
  defaultValue: number | string,
  minimum: number | string,
  maximum: number | string,
): StrategyParameter {
  return {
    key,
    kind,
    label,
    default: defaultValue,
    minimum,
    maximum,
  };
}
