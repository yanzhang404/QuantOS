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
  version: "1.0.0" | "0.1.0";
  label: string;
  description: string;
  category: StrategyCategory;
  stage: StrategyStage;
  implementation: string;
  supported_intervals: StrategyInterval[];
  parameters: StrategyParameter[];
  external_feature?: {
    series: "funding-rate";
    schema_version: "aligned-derivatives.v1";
    alignment_policy_version: "asof-closed-bar.v1";
  };
};

export const fallbackStrategyCatalog: StrategyDefinition[] = [
  {
    name: "funding-filtered-ema",
    version: "0.1.0",
    label: "Funding-filtered EMA",
    description: "EMA trend candidate that fails flat on crowded or unavailable funding.",
    category: "trend",
    stage: "candidate",
    implementation: "quantos_backtest.strategies.FundingFilteredEmaStrategy",
    supported_intervals: ["1h", "4h", "1d"],
    external_feature: {
      series: "funding-rate",
      schema_version: "aligned-derivatives.v1",
      alignment_policy_version: "asof-closed-bar.v1",
    },
    parameters: [
      parameter("fast_period", "integer", "Fast period", 20, 1, 1000),
      parameter("slow_period", "integer", "Slow period", 50, 2, 2000),
      parameter("max_funding_rate", "decimal", "Maximum funding rate", "0.0001", "-0.01", "0.01"),
    ],
  },
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
  max_funding_rate: "最高资金费率",
};

export function mergeStrategyCatalog(remote: unknown): StrategyDefinition[] {
  if (!Array.isArray(remote)) {
    return fallbackStrategyCatalog;
  }

  return fallbackStrategyCatalog.map((fallback) => {
    const candidate = remote.find(
      (item): item is Partial<StrategyDefinition> =>
        isRecord(item) && item.name === fallback.name,
    );

    if (!candidate) {
      return fallback;
    }

    return {
      ...fallback,
      label: nonEmptyString(candidate.label) ? candidate.label : fallback.label,
      description: nonEmptyString(candidate.description)
        ? candidate.description
        : fallback.description,
      category: isStrategyCategory(candidate.category)
        ? candidate.category
        : fallback.category,
      stage: isStrategyStage(candidate.stage)
        ? candidate.stage
        : fallback.stage,
      implementation: nonEmptyString(candidate.implementation)
        ? candidate.implementation
        : fallback.implementation,
      supported_intervals:
        Array.isArray(candidate.supported_intervals) &&
        candidate.supported_intervals.length > 0
          ? candidate.supported_intervals.filter(isStrategyInterval)
          : fallback.supported_intervals,
      parameters:
        Array.isArray(candidate.parameters) && candidate.parameters.length > 0
          ? candidate.parameters
          : fallback.parameters,
      external_feature: fallback.external_feature,
    };
  });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function nonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function isStrategyCategory(value: unknown): value is StrategyCategory {
  return (
    value === "trend" ||
    value === "benchmark" ||
    value === "mean-reversion" ||
    value === "intraday"
  );
}

function isStrategyStage(value: unknown): value is StrategyStage {
  return (
    value === "candidate" ||
    value === "validated" ||
    value === "benchmark"
  );
}

function isStrategyInterval(value: unknown): value is StrategyInterval {
  return (
    value === "5m" ||
    value === "15m" ||
    value === "1h" ||
    value === "4h" ||
    value === "1d"
  );
}

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
