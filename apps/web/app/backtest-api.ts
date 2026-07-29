import type { StrategyName } from "./research-data";

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
  dataset: {
    version: string;
    content_sha256: string;
    symbol: string;
    interval: "1h" | "4h";
  };
  strategy: {
    name: StrategyName;
    version: "1.0.0";
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

type TaskList = {
  tasks: BacktestTask[];
};

const apiBase =
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

async function requestJSON<T>(
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
