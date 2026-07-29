"use client";

import { useEffect, useMemo, useState } from "react";
import {
  APIError,
  type BacktestSubmission,
  type BacktestTask,
  getTask,
  listTasks,
  submitBacktest,
} from "./backtest-api";
import type { StrategyName } from "./research-data";
import type { VisualizationDataset } from "./visualization-data";

type Locale = "en" | "zh";

type Props = {
  dataset: VisualizationDataset;
  locale: Locale;
  strategy: StrategyName;
};

type Parameter = {
  key: string;
  kind: "integer" | "decimal";
  label: { en: string; zh: string };
  minimum: number;
  maximum: number;
  step: number;
};

const parameters: Record<StrategyName, Parameter[]> = {
  "buy-and-hold": [
    {
      key: "target_exposure",
      kind: "decimal",
      label: { en: "Target exposure", zh: "目标仓位" },
      minimum: 0.01,
      maximum: 1,
      step: 0.01,
    },
  ],
  "ema-cross": [
    {
      key: "fast_period",
      kind: "integer",
      label: { en: "Fast EMA", zh: "快速 EMA 周期" },
      minimum: 1,
      maximum: 1000,
      step: 1,
    },
    {
      key: "slow_period",
      kind: "integer",
      label: { en: "Slow EMA", zh: "慢速 EMA 周期" },
      minimum: 2,
      maximum: 2000,
      step: 1,
    },
  ],
  "donchian-atr": [
    {
      key: "entry_period",
      kind: "integer",
      label: { en: "Entry period", zh: "入场周期" },
      minimum: 2,
      maximum: 2000,
      step: 1,
    },
    {
      key: "exit_period",
      kind: "integer",
      label: { en: "Exit period", zh: "退出周期" },
      minimum: 1,
      maximum: 2000,
      step: 1,
    },
    {
      key: "atr_period",
      kind: "integer",
      label: { en: "ATR period", zh: "ATR 周期" },
      minimum: 2,
      maximum: 2000,
      step: 1,
    },
    {
      key: "target_annual_volatility",
      kind: "decimal",
      label: { en: "Target volatility", zh: "目标年化波动率" },
      minimum: 0.01,
      maximum: 2,
      step: 0.01,
    },
    {
      key: "max_exposure",
      kind: "decimal",
      label: { en: "Strategy max exposure", zh: "策略最大仓位" },
      minimum: 0.01,
      maximum: 1,
      step: 0.01,
    },
    {
      key: "rebalance_threshold",
      kind: "decimal",
      label: { en: "Rebalance threshold", zh: "再平衡阈值" },
      minimum: 0,
      maximum: 1,
      step: 0.01,
    },
  ],
};

const initialParameters: Record<StrategyName, Record<string, string>> = {
  "buy-and-hold": { target_exposure: "1" },
  "ema-cross": { fast_period: "20", slow_period: "50" },
  "donchian-atr": {
    entry_period: "55",
    exit_period: "20",
    atr_period: "20",
    target_annual_volatility: "0.20",
    max_exposure: "1",
    rebalance_threshold: "0.05",
  },
};

const copy = {
  en: {
    eyebrow: "Backtest lab",
    title: "Edit parameters and save a reproducible run",
    strategyParameters: "Strategy parameters",
    assumptions: "Simulation assumptions",
    initialCash: "Initial cash",
    fee: "Fee (bps)",
    slippage: "Slippage (bps)",
    riskLimit: "Risk exposure limit",
    liquidate: "Liquidate at period end",
    label: "Run label",
    labelPlaceholder: "e.g. Lower turnover test",
    run: "Run backtest",
    running: "Backtest running",
    queued: "Waiting for worker",
    succeeded: "Run saved",
    failed: "Backtest failed",
    offline: "Local API is not connected",
    offlineHint: "Start the QuantOS API to submit and browse saved runs.",
    retry: "Retry connection",
    history: "Backtest history",
    historyHint: "Every submission is retained as a Task record.",
    empty: "No manual backtests yet.",
    reused: "reused",
    newRun: "new run",
    runID: "Run ID",
    invalidPeriods: "Fast period must be below slow period.",
    invalidExit: "Exit period cannot exceed entry period.",
    invalidExposure: "Strategy exposure cannot exceed the risk limit.",
    invalidValue: "One or more parameters are outside the allowed range.",
    task: "Task",
    saved: "Saved",
  },
  zh: {
    eyebrow: "回测实验室",
    title: "修改参数并保存一次可复现回测",
    strategyParameters: "策略参数",
    assumptions: "模拟假设",
    initialCash: "初始资金",
    fee: "手续费（bps）",
    slippage: "滑点（bps）",
    riskLimit: "风险仓位上限",
    liquidate: "区间结束时强制平仓",
    label: "回测名称",
    labelPlaceholder: "例如：降低换手率测试",
    run: "运行回测",
    running: "回测运行中",
    queued: "等待执行",
    succeeded: "回测记录已保存",
    failed: "回测失败",
    offline: "本地 API 尚未连接",
    offlineHint: "启动 QuantOS API 后即可提交并查看持久化回测记录。",
    retry: "重新连接",
    history: "回测历史",
    historyHint: "每次提交都会保留为独立 Task 记录。",
    empty: "还没有手动回测记录。",
    reused: "复用已有结果",
    newRun: "新回测",
    runID: "Run ID",
    invalidPeriods: "快速周期必须小于慢速周期。",
    invalidExit: "退出周期不能大于入场周期。",
    invalidExposure: "策略仓位不能超过风险仓位上限。",
    invalidValue: "一个或多个参数超出允许范围。",
    task: "任务",
    saved: "已保存",
  },
} as const;

export function BacktestLab({ dataset, locale, strategy }: Props) {
  const [values, setValues] = useState(initialParameters);
  const [initialCash, setInitialCash] = useState("100000");
  const [feeBPS, setFeeBPS] = useState("10");
  const [slippageBPS, setSlippageBPS] = useState("5");
  const [riskLimit, setRiskLimit] = useState("1");
  const [liquidateAtEnd, setLiquidateAtEnd] = useState(true);
  const [label, setLabel] = useState("");
  const [tasks, setTasks] = useState<BacktestTask[]>([]);
  const [activeTask, setActiveTask] = useState<BacktestTask>();
  const [apiState, setAPIState] = useState<
    "connecting" | "connected" | "offline"
  >("connecting");
  const [message, setMessage] = useState<string>();
  const [submitting, setSubmitting] = useState(false);
  const t = copy[locale];
  const localeTag = locale === "zh" ? "zh-CN" : "en-US";
  const activeValues = values[strategy];
  const effectiveRiskLimit = strategy === "ema-cross" ? "1" : riskLimit;
  const visibleTasks = useMemo(() => tasks.slice(0, 10), [tasks]);

  const connect = async (signal?: AbortSignal) => {
    try {
      const records = await listTasks(signal);
      setTasks(records);
      setAPIState("connected");
    } catch (error) {
      if (signal?.aborted) return;
      setAPIState("offline");
      setMessage(error instanceof APIError ? error.message : t.offline);
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    void listTasks(controller.signal)
      .then((records) => {
        setTasks(records);
        setAPIState("connected");
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setAPIState("offline");
        setMessage(
          error instanceof APIError
            ? error.message
            : "QuantOS API is unavailable.",
        );
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (
      !activeTask ||
      (activeTask.status !== "queued" && activeTask.status !== "running")
    ) {
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const next = await getTask(activeTask.task_id, controller.signal);
        setActiveTask(next);
        setTasks((current) => [
          next,
          ...current.filter((task) => task.task_id !== next.task_id),
        ]);
        if (next.status === "succeeded") {
          setMessage(t.succeeded);
        } else if (next.status === "failed") {
          setMessage(next.error?.message ?? t.failed);
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          setAPIState("offline");
          setMessage(error instanceof APIError ? error.message : t.offline);
        }
      }
    }, 900);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [activeTask, t.failed, t.offline, t.succeeded]);

  const validationMessage = validateForm(
    strategy,
    activeValues,
    initialCash,
    feeBPS,
    slippageBPS,
    effectiveRiskLimit,
    t,
  );

  const updateParameter = (key: string, value: string) => {
    setValues((current) => ({
      ...current,
      [strategy]: { ...current[strategy], [key]: value },
    }));
  };

  const submit = async () => {
    if (validationMessage) {
      setMessage(validationMessage);
      return;
    }
    setSubmitting(true);
    setMessage(undefined);
    const request = buildSubmission({
      dataset,
      strategy,
      values: activeValues,
      initialCash,
      feeBPS,
      slippageBPS,
      riskLimit: effectiveRiskLimit,
      liquidateAtEnd,
      label,
    });
    try {
      const task = await submitBacktest(request);
      setActiveTask(task);
      setTasks((current) => [
        task,
        ...current.filter((item) => item.task_id !== task.task_id),
      ]);
      setAPIState("connected");
      setMessage(task.status === "queued" ? t.queued : t.running);
    } catch (error) {
      setAPIState((current) =>
        error instanceof APIError && !error.status ? "offline" : current,
      );
      setMessage(error instanceof APIError ? error.message : t.failed);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="backtest-lab">
      <div className="parameter-panel">
        <div className="lab-heading">
          <div>
            <p className="eyebrow">{t.eyebrow}</p>
            <h3>{t.title}</h3>
          </div>
          <span className={`api-state ${apiState}`}>
            <i />
            {apiState === "connected" ? "API" : t.offline}
          </span>
        </div>

        <div className="parameter-groups">
          <fieldset>
            <legend>{t.strategyParameters}</legend>
            <div className="parameter-fields">
              {parameters[strategy].map((parameter) => (
                <NumberField
                  key={parameter.key}
                  label={parameter.label[locale]}
                  maximum={parameter.maximum}
                  minimum={parameter.minimum}
                  onChange={(value) => updateParameter(parameter.key, value)}
                  step={parameter.step}
                  value={activeValues[parameter.key]}
                />
              ))}
            </div>
          </fieldset>

          <fieldset>
            <legend>{t.assumptions}</legend>
            <div className="parameter-fields assumptions">
              <NumberField
                label={t.initialCash}
                minimum={1}
                onChange={setInitialCash}
                step={1000}
                value={initialCash}
              />
              <NumberField
                label={t.fee}
                maximum={1000}
                minimum={0}
                onChange={setFeeBPS}
                step={1}
                value={feeBPS}
              />
              <NumberField
                label={t.slippage}
                maximum={1000}
                minimum={0}
                onChange={setSlippageBPS}
                step={1}
                value={slippageBPS}
              />
              <NumberField
                disabled={strategy === "ema-cross"}
                label={t.riskLimit}
                maximum={1}
                minimum={0.01}
                onChange={setRiskLimit}
                step={0.01}
                value={strategy === "ema-cross" ? "1" : riskLimit}
              />
            </div>
          </fieldset>
        </div>

        <div className="run-meta">
          <label>
            <span>{t.label}</span>
            <input
              maxLength={120}
              onChange={(event) => setLabel(event.target.value)}
              placeholder={t.labelPlaceholder}
              type="text"
              value={label}
            />
          </label>
          <label className="checkbox-label">
            <input
              checked={liquidateAtEnd}
              onChange={(event) => setLiquidateAtEnd(event.target.checked)}
              type="checkbox"
            />
            <span>{t.liquidate}</span>
          </label>
        </div>

        <div className="run-actions">
          <div className="run-context">
            <span>
              {dataset.symbol} · {dataset.interval}
            </span>
            <code>{dataset.dataset_version}</code>
          </div>
          <button
            className="run-backtest"
            disabled={
              submitting ||
              activeTask?.status === "queued" ||
              activeTask?.status === "running"
            }
            onClick={submit}
            type="button"
          >
            <span aria-hidden="true">▶</span>
            {submitting
              ? t.queued
              : activeTask?.status === "running"
                ? t.running
                : t.run}
          </button>
        </div>

        {message ? (
          <div
            className={`lab-message ${
              activeTask?.status === "succeeded" ? "success" : ""
            }`}
            role="status"
          >
            <span>{message}</span>
            {apiState === "offline" ? (
              <button onClick={() => void connect()} type="button">
                {t.retry}
              </button>
            ) : null}
            {activeTask?.run_id ? (
              <code>
                {t.runID} {activeTask.run_id}
              </code>
            ) : null}
          </div>
        ) : null}
      </div>

      <aside className="task-history">
        <div className="history-heading">
          <div>
            <p className="eyebrow">{t.history}</p>
            <h3>{visibleTasks.length.toString().padStart(2, "0")}</h3>
          </div>
          <p>{t.historyHint}</p>
        </div>
        <div className="task-list">
          {visibleTasks.length ? (
            visibleTasks.map((task) => (
              <button
                className={activeTask?.task_id === task.task_id ? "selected" : ""}
                key={task.task_id}
                onClick={() => setActiveTask(task)}
                type="button"
              >
                <span className={`task-status ${task.status}`} />
                <div>
                  <strong>
                    {task.request.label ||
                      task.request.strategy.name.replaceAll("-", " ")}
                  </strong>
                  <small>
                    {task.request.dataset.symbol} ·{" "}
                    {formatTaskTime(task.created_at, localeTag)}
                  </small>
                  <code>
                    {task.run_id
                      ? `${t.saved} ${task.run_id}`
                      : `${t.task} ${task.task_id.slice(-8)}`}
                  </code>
                </div>
                <span className="task-state-label">
                  {statusLabel(task, t)}
                </span>
              </button>
            ))
          ) : (
            <p className="empty-history">{t.empty}</p>
          )}
        </div>
      </aside>
    </section>
  );
}

function NumberField({
  label,
  value,
  onChange,
  minimum,
  maximum,
  step,
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  minimum: number;
  maximum?: number;
  step: number;
  disabled?: boolean;
}) {
  return (
    <label>
      <span>{label}</span>
      <input
        disabled={disabled}
        max={maximum}
        min={minimum}
        onChange={(event) => onChange(event.target.value)}
        step={step}
        type="number"
        value={value}
      />
    </label>
  );
}

function buildSubmission({
  dataset,
  strategy,
  values,
  initialCash,
  feeBPS,
  slippageBPS,
  riskLimit,
  liquidateAtEnd,
  label,
}: {
  dataset: VisualizationDataset;
  strategy: StrategyName;
  values: Record<string, string>;
  initialCash: string;
  feeBPS: string;
  slippageBPS: string;
  riskLimit: string;
  liquidateAtEnd: boolean;
  label: string;
}): BacktestSubmission {
  const strategyParameters = Object.fromEntries(
    parameters[strategy].map((parameter) => [
      parameter.key,
      parameter.kind === "integer"
        ? Number.parseInt(values[parameter.key], 10)
        : values[parameter.key],
    ]),
  );
  return {
    schema_version: "1.0",
    idempotency_key: `web:${crypto.randomUUID()}`,
    ...(label.trim() ? { label: label.trim() } : {}),
    dataset: {
      version: dataset.dataset_version,
      content_sha256: dataset.content_sha256,
      symbol: dataset.symbol,
      interval: dataset.interval as "1h" | "4h",
    },
    strategy: {
      name: strategy,
      version: "1.0.0",
      parameters: strategyParameters,
    },
    config: {
      initial_cash: initialCash,
      fee_bps: feeBPS,
      slippage_bps: slippageBPS,
      max_target_exposure: strategy === "ema-cross" ? "1" : riskLimit,
      liquidate_at_end: liquidateAtEnd,
    },
  };
}

function validateForm(
  strategy: StrategyName,
  values: Record<string, string>,
  initialCash: string,
  feeBPS: string,
  slippageBPS: string,
  riskLimit: string,
  t: (typeof copy)[Locale],
): string | undefined {
  const invalidParameter = parameters[strategy].some((parameter) => {
    const value = Number(values[parameter.key]);
    return (
      !Number.isFinite(value) ||
      value < parameter.minimum ||
      value > parameter.maximum
    );
  });
  if (
    invalidParameter ||
    Number(initialCash) <= 0 ||
    Number(feeBPS) < 0 ||
    Number(feeBPS) > 1000 ||
    Number(slippageBPS) < 0 ||
    Number(slippageBPS) > 1000 ||
    Number(riskLimit) <= 0 ||
    Number(riskLimit) > 1
  ) {
    return t.invalidValue;
  }
  if (
    strategy === "ema-cross" &&
    Number(values.fast_period) >= Number(values.slow_period)
  ) {
    return t.invalidPeriods;
  }
  if (
    strategy === "donchian-atr" &&
    Number(values.exit_period) > Number(values.entry_period)
  ) {
    return t.invalidExit;
  }
  const strategyExposure =
    strategy === "buy-and-hold"
      ? Number(values.target_exposure)
      : strategy === "donchian-atr"
        ? Number(values.max_exposure)
        : 1;
  if (strategyExposure > Number(riskLimit)) {
    return t.invalidExposure;
  }
  return undefined;
}

function statusLabel(
  task: BacktestTask,
  t: (typeof copy)[Locale],
): string {
  if (task.status === "queued") return t.queued;
  if (task.status === "running") return t.running;
  if (task.status === "succeeded") {
    return task.reused ? t.reused : t.newRun;
  }
  return t.failed;
}

function formatTaskTime(value: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}
