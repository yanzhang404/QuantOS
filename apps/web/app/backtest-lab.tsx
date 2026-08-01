"use client";

import { useEffect, useMemo, useState } from "react";
import {
  APIError,
  type BacktestSubmission,
  type BacktestTask,
  type ExperimentVisualization,
  getExperiment,
  getTask,
  listTasks,
  submitBacktest,
} from "./backtest-api";
import type { StrategyName } from "./research-data";
import {
  fallbackStrategyCatalog,
  parameterLabelsZh,
  type StrategyDefinition,
} from "./strategy-catalog";

type Locale = "en" | "zh";

type Props = {
  dataset: BacktestSubmission["dataset"];
  definition: StrategyDefinition;
  locale: Locale;
  strategy: StrategyName;
  onExperimentLoaded: (experiment: ExperimentVisualization) => void;
};

function initialParameterValues(): Record<
  StrategyName,
  Record<string, string>
> {
  return Object.fromEntries(
    fallbackStrategyCatalog.map((definition) => [
      definition.name,
      Object.fromEntries(
        definition.parameters.map((parameter) => [
          parameter.key,
          String(parameter.default),
        ]),
      ),
    ]),
  ) as Record<StrategyName, Record<string, string>>;
}

const copy = {
  en: {
    eyebrow: "Backtest lab",
    title: "Edit parameters and save a reproducible run",
    strategyParameters: "Strategy parameters",
    assumptions: "Simulation assumptions",
    advanced: "Advanced settings",
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
    historyHint: "Select a saved run to compare its results and parameters.",
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
    loadingResult: "Loading experiment result",
    showingResult: "Charts updated to this Run",
    return: "Return",
    drawdown: "Drawdown",
    finalCapital: "Final",
    bundle: "Bundle",
  },
  zh: {
    eyebrow: "回测实验室",
    title: "修改参数并保存一次可复现回测",
    strategyParameters: "策略参数",
    assumptions: "模拟假设",
    advanced: "高级设置",
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
    historyHint: "点击历史记录即可对比结果与参数。",
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
    loadingResult: "正在加载实验结果",
    showingResult: "图表已切换到本次 Run",
    return: "收益",
    drawdown: "回撤",
    finalCapital: "金额",
    bundle: "Bundle",
  },
} as const;

export function BacktestLab({
  dataset,
  definition,
  locale,
  strategy,
  onExperimentLoaded,
}: Props) {
  const [values, setValues] = useState(initialParameterValues);
  const [initialCash, setInitialCash] = useState("100000");
  const [feeBPS, setFeeBPS] = useState("10");
  const [slippageBPS, setSlippageBPS] = useState("5");
  const [riskLimit, setRiskLimit] = useState("1");
  const [liquidateAtEnd, setLiquidateAtEnd] = useState(true);
  const [label, setLabel] = useState("");
  const [tasks, setTasks] = useState<BacktestTask[]>([]);
  const [experiments, setExperiments] = useState<
    Record<string, ExperimentVisualization>
  >({});
  const [activeTask, setActiveTask] = useState<BacktestTask>();
  const [apiState, setAPIState] = useState<
    "connecting" | "connected" | "offline"
  >("connecting");
  const [message, setMessage] = useState<string>();
  const [submitting, setSubmitting] = useState(false);
  const [loadingExperiment, setLoadingExperiment] = useState(false);
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
    const missingRunIDs = visibleTasks
      .filter(
        (task) =>
          task.status === "succeeded" &&
          task.run_id &&
          experiments[task.run_id] === undefined,
      )
      .map((task) => task.run_id!);
    if (missingRunIDs.length === 0) return;

    const controller = new AbortController();
    void Promise.all(
      missingRunIDs.map(async (runID) => {
        try {
          return [runID, await getExperiment(runID, controller.signal)] as const;
        } catch {
          return undefined;
        }
      }),
    ).then((records) => {
      if (controller.signal.aborted) return;
      setExperiments((current) => ({
        ...current,
        ...Object.fromEntries(records.filter((record) => record !== undefined)),
      }));
    });
    return () => controller.abort();
  }, [experiments, visibleTasks]);

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
          if (next.run_id) {
            setLoadingExperiment(true);
            const experiment = await getExperiment(
              next.run_id,
              controller.signal,
            );
            setExperiments((current) => ({
              ...current,
              [experiment.run_id]: experiment,
            }));
            onExperimentLoaded(experiment);
            setMessage(t.showingResult);
            setLoadingExperiment(false);
          } else {
            setMessage(t.succeeded);
          }
        } else if (next.status === "failed") {
          setMessage(next.error?.message ?? t.failed);
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          setLoadingExperiment(false);
          if (error instanceof APIError && !error.status) {
            setAPIState("offline");
          }
          setMessage(error instanceof APIError ? error.message : t.offline);
        }
      }
    }, 900);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [
    activeTask,
    onExperimentLoaded,
    t.failed,
    t.offline,
    t.showingResult,
    t.succeeded,
  ]);

  const selectTask = async (task: BacktestTask) => {
    setActiveTask(task);
    if (task.status !== "succeeded" || !task.run_id) return;
    setLoadingExperiment(true);
    setMessage(t.loadingResult);
    try {
      const experiment = await getExperiment(task.run_id);
      setExperiments((current) => ({
        ...current,
        [experiment.run_id]: experiment,
      }));
      onExperimentLoaded(experiment);
      setAPIState("connected");
      setMessage(t.showingResult);
    } catch (error) {
      if (error instanceof APIError && !error.status) {
        setAPIState("offline");
      }
      setMessage(error instanceof APIError ? error.message : t.failed);
    } finally {
      setLoadingExperiment(false);
    }
  };

  const validationMessage = validateForm(
    strategy,
    definition,
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
      definition,
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

        <fieldset className="strategy-parameter-group">
          <legend>{t.strategyParameters}</legend>
          <div className="parameter-fields">
            {definition.parameters.map((parameter) => (
              <NumberField
                key={parameter.key}
                label={
                  locale === "zh"
                    ? parameterLabelsZh[parameter.key] ?? parameter.label
                    : parameter.label
                }
                maximum={Number(parameter.maximum)}
                minimum={Number(parameter.minimum)}
                onChange={(value) => updateParameter(parameter.key, value)}
                step={parameter.kind === "integer" ? 1 : 0.01}
                value={activeValues[parameter.key]}
              />
            ))}
          </div>
        </fieldset>

        <div className="run-basics">
          <NumberField
            label={t.initialCash}
            minimum={1}
            onChange={setInitialCash}
            step={1000}
            value={initialCash}
          />
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
        </div>

        <details className="advanced-settings">
          <summary>
            <span>{t.advanced}</span>
            <small>
              {feeBPS} bps fee · {slippageBPS} bps slippage
            </small>
          </summary>
          <div className="advanced-settings-content">
            <div className="parameter-fields assumptions">
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
            <label className="checkbox-label">
              <input
                checked={liquidateAtEnd}
                onChange={(event) => setLiquidateAtEnd(event.target.checked)}
                type="checkbox"
              />
              <span>{t.liquidate}</span>
            </label>
          </div>
        </details>

        <div className="run-actions">
          <div className="run-context">
            <span>
              {dataset.symbol} · {dataset.interval}
            </span>
            <code>
              {t.bundle} {dataset.bundle_version} · {dataset.version}
            </code>
          </div>
          <button
            className="run-backtest"
            disabled={
              submitting ||
              loadingExperiment ||
              activeTask?.status === "queued" ||
              activeTask?.status === "running"
            }
            onClick={submit}
            type="button"
          >
            <span aria-hidden="true">▶</span>
            {submitting
              ? t.queued
              : loadingExperiment
                ? t.loadingResult
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
            visibleTasks.map((task) => {
              const experiment = task.run_id
                ? experiments[task.run_id]
                : undefined;
              return (
                <button
                  className={
                    activeTask?.task_id === task.task_id ? "selected" : ""
                  }
                  key={task.task_id}
                  onClick={() => void selectTask(task)}
                  type="button"
                >
                  <span className={`task-status ${task.status}`} />
                  <div>
                    <strong>
                      {task.request.label ||
                        task.request.strategy.name.replaceAll("-", " ")}
                    </strong>
                    <small>
                      {task.request.dataset.symbol} · {task.request.dataset.interval} ·{" "}
                      {formatTaskTime(task.created_at, localeTag)}
                    </small>
                    {experiment ? (
                      <div className="task-result-row">
                        <span
                          className={
                            experiment.metrics.total_return >= 0
                              ? "positive"
                              : "negative"
                          }
                        >
                          {t.return}{" "}
                          {formatPercent(
                            experiment.metrics.total_return,
                            localeTag,
                          )}
                        </span>
                        <span className="negative">
                          {t.drawdown}{" "}
                          {formatPercent(
                            -experiment.metrics.max_drawdown,
                            localeTag,
                          )}
                        </span>
                        <span>
                          {t.finalCapital}{" "}
                          {formatMoney(
                            experiment.metrics.final_equity,
                            localeTag,
                          )}
                        </span>
                      </div>
                    ) : (
                      <code>
                        {task.run_id
                          ? `${t.saved} ${task.run_id}`
                          : `${t.task} ${task.task_id.slice(-8)}`}
                      </code>
                    )}
                    <code className="task-parameters">
                      {Object.entries(task.request.strategy.parameters)
                        .map(([key, value]) => `${key}=${value}`)
                        .join(" · ")}
                    </code>
                  </div>
                  <span className="task-state-label">
                    {statusLabel(task, t)}
                  </span>
                </button>
              );
            })
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
  definition,
  strategy,
  values,
  initialCash,
  feeBPS,
  slippageBPS,
  riskLimit,
  liquidateAtEnd,
  label,
}: {
  dataset: BacktestSubmission["dataset"];
  definition: StrategyDefinition;
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
    definition.parameters.map((parameter) => [
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
    dataset,
    strategy: {
      name: strategy,
      version: definition.version,
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
  definition: StrategyDefinition,
  values: Record<string, string>,
  initialCash: string,
  feeBPS: string,
  slippageBPS: string,
  riskLimit: string,
  t: (typeof copy)[Locale],
): string | undefined {
  const invalidParameter = definition.parameters.some((parameter) => {
    const value = Number(values[parameter.key]);
    return (
      !Number.isFinite(value) ||
      value < Number(parameter.minimum) ||
      value > Number(parameter.maximum)
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

function formatPercent(value: number, locale: string): string {
  return new Intl.NumberFormat(locale, {
    style: "percent",
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
    signDisplay: "exceptZero",
  }).format(value);
}

function formatMoney(value: number, locale: string): string {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}
