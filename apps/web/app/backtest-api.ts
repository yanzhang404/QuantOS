import type { StrategyName } from "./research-data";
import type { StrategyDefinition } from "./strategy-catalog";

export type TaskStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

export type BacktestSubmission = {
  schema_version: "1.0";
  idempotency_key: string;
  label?: string;
  note?: string;
  feature_dataset_version?: string;
  dataset: {
    bundle_version?: string;
    version: string;
    content_sha256: string;
    symbol: string;
    interval: "5m" | "15m" | "1h" | "4h" | "1d";
    data_start?: string;
    data_end?: string;
  };
  strategy: {
    name: StrategyName;
    version: "1.0.0" | "0.1.0";
    parameters: Record<string, number | string>;
  };
  config: {
    initial_cash: string;
    fee_bps: string;
    slippage_bps: string;
    max_target_exposure: string;
    liquidate_at_end: boolean;
  };
};

export type BacktestTask = {
  schema_version: "1.0";
  task_id: string;
  status: TaskStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  request: BacktestSubmission;
  run_id: string | null;
  reused: boolean | null;
  error: {
    code: string;
    message: string;
    retryable: boolean;
  } | null;
};

export type FeatureDataset = {
  dataset_version: string;
  schema_version: "aligned-derivatives.v1";
  alignment_policy_version: "asof-closed-bar.v1";
  series: "funding-rate" | "open-interest";
  exchange: string;
  symbol: string;
  spot_interval: string;
  derivative_period: string | null;
  spot_dataset_version: string;
  spot_content_sha256: string;
  derivative_dataset_version: string;
  derivative_content_sha256: string;
  requested_start: string;
  requested_end: string;
  max_age_ms: number;
  row_count: number;
  matched_count: number;
  stale_count: number;
  no_prior_count: number;
  content_sha256: string;
  created_at: string;
  producer: string;
  file_sha256: string;
};

export type ExperimentVisualization = {
  schema_version: "1.0";
  run_id: string;
  created_at: string;
  dataset: BacktestSubmission["dataset"];
  strategy: BacktestSubmission["strategy"];
  features: Array<{
    feature_id: string;
    instance: string;
    version: string;
    definition_sha256: string;
    implementation: string;
    inputs: string[];
    parameters: Record<string, number>;
    strategy_parameter: string;
    warmup_bars: number;
    uses_current_closed_bar: boolean;
  }>;
  feature_datasets?: FeatureDataset[];
  config: BacktestSubmission["config"];
  engine_version: string;
  metrics_version: string;
  metrics: {
    initial_equity: number;
    final_equity: number;
    total_return: number;
    sharpe_ratio: number | null;
    max_drawdown: number;
    trade_count: number;
    fill_count: number;
    fees_paid: number;
  };
  bars: Array<{
    time: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
  }>;
  equity: Array<{
    time: string;
    equity: number;
    drawdown: number;
    position: number;
  }>;
  fills: Array<{
    time: string;
    side: "buy" | "sell";
    price: number;
    quantity: number;
    fee: number;
    reason: string;
  }>;
};

export type ExperimentSummary = Omit<
  ExperimentVisualization,
  "bars" | "equity" | "fills" | "features" | "feature_datasets"
> & {
  archived_at: string | null;
};

export type ExperimentFilters = {
  symbol?: string;
  interval?: BacktestSubmission["dataset"]["interval"];
  strategy?: StrategyName;
  archived?: "exclude" | "include" | "only";
  limit?: number;
};

type TaskList = {
  tasks: BacktestTask[];
};

type StrategyCatalog = {
  schema_version: "1.0";
  strategies: StrategyDefinition[];
};

type ExperimentList = {
  experiments: ExperimentSummary[];
};

type FeatureDatasetList = {
  schema_version: "1.0";
  feature_datasets: FeatureDataset[];
};

export const apiBase =
  process.env.NEXT_PUBLIC_QUANTOS_API_URL ?? "http://localhost:8080";

export class APIError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
  }
}

export async function submitBacktest(
  request: BacktestSubmission,
  signal?: AbortSignal,
): Promise<BacktestTask> {
  return requestJSON<BacktestTask>(
    "/api/v1/backtests",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": request.idempotency_key,
      },
      body: JSON.stringify(request),
    },
    signal,
  );
}

export async function getTask(
  taskID: string,
  signal?: AbortSignal,
): Promise<BacktestTask> {
  return requestJSON<BacktestTask>(
    `/api/v1/tasks/${encodeURIComponent(taskID)}`,
    {},
    signal,
  );
}

export async function listTasks(
  signal?: AbortSignal,
): Promise<BacktestTask[]> {
  const response = await requestJSON<TaskList>("/api/v1/tasks", {}, signal);
  return response.tasks;
}

export async function listCompatibleFeatureDatasets(
  dataset: BacktestSubmission["dataset"],
  signal?: AbortSignal,
): Promise<FeatureDataset[]> {
  const query = new URLSearchParams({
    series: "funding-rate",
    symbol: dataset.symbol,
    interval: dataset.interval,
    spot_dataset_version: dataset.version,
    spot_content_sha256: dataset.content_sha256,
  });
  const response = await requestJSON<FeatureDatasetList>(
    `/api/v1/feature-datasets?${query.toString()}`,
    {},
    signal,
  );
  return response.feature_datasets;
}

export async function getExperiment(
  runID: string,
  signal?: AbortSignal,
): Promise<ExperimentVisualization> {
  return requestJSON<ExperimentVisualization>(
    `/api/v1/experiments/${encodeURIComponent(runID)}`,
    {},
    signal,
  );
}

export async function listExperiments(
  filters: ExperimentFilters = {},
  signal?: AbortSignal,
): Promise<ExperimentSummary[]> {
  const query = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== "") query.set(key, String(value));
  });
  const suffix = query.size ? `?${query.toString()}` : "";
  const response = await requestJSON<ExperimentList>(
    `/api/v1/experiments${suffix}`,
    {},
    signal,
  );
  return response.experiments;
}

export async function setExperimentArchived(
  runID: string,
  archived: boolean,
  signal?: AbortSignal,
): Promise<void> {
  await requestJSON(
    `/api/v1/experiment-archives/${encodeURIComponent(runID)}`,
    { method: archived ? "PUT" : "DELETE" },
    signal,
  );
}

export async function getStrategyCatalog(
  signal?: AbortSignal,
): Promise<StrategyDefinition[]> {
  const response = await requestJSON<StrategyCatalog>(
    "/api/v1/strategies",
    {},
    signal,
  );
  return response.strategies;
}

export async function requestJSON<T>(
  path: string,
  init: RequestInit,
  signal?: AbortSignal,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBase}${path}`, {
      ...init,
      signal,
    });
  } catch {
    throw new APIError("QuantOS API is unavailable.");
  }
  const payload = (await response.json().catch(() => undefined)) as
    | { error?: { message?: string } }
    | undefined;
  if (!response.ok) {
    throw new APIError(
      payload?.error?.message ?? `Request failed with status ${response.status}.`,
      response.status,
    );
  }
  return payload as T;
}
