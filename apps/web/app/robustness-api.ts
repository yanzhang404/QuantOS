import { requestJSON } from "./backtest-api";

export type RobustnessGate = {
  name:
    | "walk_forward"
    | "neighboring_parameters"
    | "doubled_costs"
    | "multiple_markets";
  passed: boolean;
  reason: string;
  observations: Record<string, unknown>;
  run_ids: string[];
};

export type RobustnessSummary = {
  schema_version: "robustness-review.v1" | "robustness-review.v2";
  review_id: string;
  created_at: string;
  passed: boolean;
  strategy: {
    name: "ema-cross" | "donchian-atr";
    version: string;
    winner:
      | { fast_period: number; slow_period: number }
      | {
          entry_period: number;
          exit_period: number;
          atr_period: number;
          target_annual_volatility: string;
          max_exposure: string;
          rebalance_threshold: string;
        };
  };
  datasets: Array<{
    version: string;
    content_sha256: string;
    symbol: string;
    interval: string;
  }>;
  gates: RobustnessGate[];
};

export async function listRobustnessReviews(
  signal?: AbortSignal,
): Promise<RobustnessSummary[]> {
  const response = await requestJSON<{ reviews: RobustnessSummary[] }>(
    "/api/v1/robustness",
    {},
    signal,
  );
  return response.reviews;
}
