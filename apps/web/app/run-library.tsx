"use client";

import { useEffect, useMemo, useState } from "react";
import {
  APIError,
  type ExperimentFilters,
  type ExperimentSummary,
  type ExperimentVisualization,
  getExperiment,
  listExperiments,
  setExperimentArchived,
} from "./backtest-api";
import type { StrategyName } from "./research-data";
import { RobustnessEvidence } from "./robustness-evidence";

type Locale = "en" | "zh";
type Interval = "5m" | "15m" | "1h" | "4h" | "1d";
type ArchiveMode = "exclude" | "include" | "only";

const colors = ["#187a58", "#3e6ec9", "#c17432", "#9b4f82"];

const copy = {
  en: {
    eyebrow: "Run catalog",
    title: "Find evidence. Compare outcomes.",
    intro:
      "Filter immutable Runs, select up to four, and compare normalized portfolio returns.",
    allMarkets: "All markets",
    allIntervals: "All intervals",
    allStrategies: "All strategies",
    active: "Active Runs",
    all: "All Runs",
    archived: "Archived",
    refresh: "Refresh",
    offline: "Run API is not connected. Start the local API to browse saved Runs.",
    empty: "No Runs match these filters.",
    compare: "Compare",
    archive: "Archive",
    restore: "Restore",
    return: "Return",
    drawdown: "Max drawdown",
    sharpe: "Sharpe",
    final: "Final capital",
    trades: "Trades",
    fee: "Fees",
    selected: "selected",
    selectHint: "Select 2–4 Runs to compare.",
    chartTitle: "Normalized portfolio return",
    chartHint:
      "Every line starts at 0%. The horizontal axis is evaluation progress; exact windows remain visible below.",
    progress: "Evaluation progress",
    parameters: "Parameters",
    costs: "Fee / slippage",
    created: "Created",
    window: "Evaluation window",
    archiveError: "Archive state could not be updated.",
  },
  zh: {
    eyebrow: "Run 目录",
    title: "查找证据，对比结果",
    intro: "筛选不可变 Run，最多选择四项，对比归一化组合收益。",
    allMarkets: "全部市场",
    allIntervals: "全部周期",
    allStrategies: "全部策略",
    active: "未归档",
    all: "全部 Run",
    archived: "已归档",
    refresh: "刷新",
    offline: "Run API 尚未连接。启动本地 API 后即可浏览保存的 Run。",
    empty: "没有符合筛选条件的 Run。",
    compare: "加入对比",
    archive: "归档",
    restore: "恢复",
    return: "收益",
    drawdown: "最大回撤",
    sharpe: "夏普",
    final: "最终金额",
    trades: "交易",
    fee: "手续费",
    selected: "项已选择",
    selectHint: "请选择 2–4 个 Run 进行对比。",
    chartTitle: "归一化组合收益",
    chartHint: "每条线都从 0% 开始；横轴表示各自评估进度，具体时间窗口列在下方。",
    progress: "评估进度",
    parameters: "参数",
    costs: "手续费 / 滑点",
    created: "创建时间",
    window: "评估区间",
    archiveError: "无法更新归档状态。",
  },
} as const;

export function RunLibrary({ locale }: { locale: Locale }) {
  const [symbol, setSymbol] = useState("");
  const [interval, setInterval] = useState<"" | Interval>("");
  const [strategy, setStrategy] = useState<"" | StrategyName>("");
  const [archiveMode, setArchiveMode] = useState<ArchiveMode>("exclude");
  const [runs, setRuns] = useState<ExperimentSummary[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [details, setDetails] = useState<Record<string, ExperimentVisualization>>({});
  const [state, setState] = useState<"loading" | "ready" | "offline">("loading");
  const [message, setMessage] = useState<string>();
  const [revision, setRevision] = useState(0);
  const t = copy[locale];
  const localeTag = locale === "zh" ? "zh-CN" : "en-US";

  useEffect(() => {
    const controller = new AbortController();
    const filters: ExperimentFilters = {
      symbol: symbol || undefined,
      interval: interval || undefined,
      strategy: strategy || undefined,
      archived: archiveMode,
      limit: 100,
    };
    void listExperiments(filters, controller.signal)
      .then((records) => {
        setRuns(records);
        setSelected((current) =>
          current.filter((runID) => records.some((run) => run.run_id === runID)),
        );
        setState("ready");
        setMessage(undefined);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState("offline");
        setMessage(error instanceof APIError ? error.message : t.offline);
      });
    return () => controller.abort();
  }, [archiveMode, interval, revision, strategy, symbol, t.offline]);

  useEffect(() => {
    const missing = selected.filter((runID) => !details[runID]);
    if (!missing.length) return;
    const controller = new AbortController();
    void Promise.all(
      missing.map(async (runID) => [runID, await getExperiment(runID, controller.signal)] as const),
    )
      .then((loaded) => {
        if (controller.signal.aborted) return;
        setDetails((current) => ({ ...current, ...Object.fromEntries(loaded) }));
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setMessage(error instanceof APIError ? error.message : t.offline);
        }
      });
    return () => controller.abort();
  }, [details, selected, t.offline]);

  const selectedRuns = useMemo(
    () => selected.map((runID) => details[runID]).filter(Boolean),
    [details, selected],
  );

  const toggleSelected = (runID: string) => {
    setSelected((current) => {
      if (current.includes(runID)) return current.filter((value) => value !== runID);
      return current.length < 4 ? [...current, runID] : current;
    });
  };

  const toggleArchive = async (run: ExperimentSummary) => {
    try {
      await setExperimentArchived(run.run_id, run.archived_at === null);
      setSelected((current) => current.filter((runID) => runID !== run.run_id));
      setRevision((value) => value + 1);
    } catch (error) {
      setMessage(error instanceof APIError ? error.message : t.archiveError);
    }
  };

  return (
    <section className="run-library">
      <header className="run-library-heading">
        <div>
          <p className="eyebrow">{t.eyebrow}</p>
          <h2>{t.title}</h2>
          <p>{t.intro}</p>
        </div>
        <div className="run-selection-count">
          <strong>{selected.length} / 4</strong>
          <span>{t.selected}</span>
        </div>
      </header>

      <RobustnessEvidence locale={locale} />

      <div className="run-filterbar">
        <select aria-label={t.allMarkets} onChange={(event) => setSymbol(event.target.value)} value={symbol}>
          <option value="">{t.allMarkets}</option>
          <option value="BTCUSDT">BTC / USDT</option>
          <option value="ETHUSDT">ETH / USDT</option>
        </select>
        <select aria-label={t.allIntervals} onChange={(event) => setInterval(event.target.value as "" | Interval)} value={interval}>
          <option value="">{t.allIntervals}</option>
          {(["5m", "15m", "1h", "4h", "1d"] as const).map((value) => <option key={value}>{value}</option>)}
        </select>
        <select aria-label={t.allStrategies} onChange={(event) => setStrategy(event.target.value as "" | StrategyName)} value={strategy}>
          <option value="">{t.allStrategies}</option>
          <option value="buy-and-hold">Buy &amp; Hold</option>
          <option value="ema-cross">EMA Cross</option>
          <option value="donchian-atr">Donchian ATR</option>
          <option value="funding-filtered-ema">Funding-filtered EMA</option>
        </select>
        <select aria-label={t.archived} onChange={(event) => setArchiveMode(event.target.value as ArchiveMode)} value={archiveMode}>
          <option value="exclude">{t.active}</option>
          <option value="include">{t.all}</option>
          <option value="only">{t.archived}</option>
        </select>
        <button onClick={() => setRevision((value) => value + 1)} type="button">{t.refresh}</button>
      </div>

      {message ? <p className="run-library-message" role="status">{state === "offline" ? t.offline : message}</p> : null}

      {state === "ready" && runs.length === 0 ? <p className="run-library-empty">{t.empty}</p> : null}

      <div className="run-catalog-list">
        {runs.map((run) => {
          const isSelected = selected.includes(run.run_id);
          return (
            <article className={`run-catalog-card ${isSelected ? "selected" : ""}`} key={run.run_id}>
              <label className="run-compare-toggle">
                <input
                  checked={isSelected}
                  disabled={!isSelected && selected.length >= 4}
                  onChange={() => toggleSelected(run.run_id)}
                  type="checkbox"
                />
                <span>{t.compare}</span>
              </label>
              <div className="run-card-identity">
                <strong>{humanize(run.strategy.name)}</strong>
                <span>{run.dataset.symbol} · {run.dataset.interval}</span>
                <code>{run.run_id}</code>
              </div>
              <RunMetric label={t.return} tone={run.metrics.total_return} value={formatPercent(run.metrics.total_return, localeTag)} />
              <RunMetric label={t.drawdown} tone={-run.metrics.max_drawdown} value={formatPercent(-run.metrics.max_drawdown, localeTag)} />
              <RunMetric label={t.sharpe} value={run.metrics.sharpe_ratio === null ? "—" : run.metrics.sharpe_ratio.toFixed(2)} />
              <RunMetric label={t.final} value={formatMoney(run.metrics.final_equity, localeTag)} />
              <button className="run-archive-action" onClick={() => void toggleArchive(run)} type="button">
                {run.archived_at ? t.restore : t.archive}
              </button>
            </article>
          );
        })}
      </div>

      <section className="run-comparison-panel">
        <div className="run-comparison-heading">
          <div>
            <p className="eyebrow">{t.chartTitle}</p>
            <h3>{selected.length >= 2 ? `${selected.length} Runs` : t.selectHint}</h3>
          </div>
          <p>{t.chartHint}</p>
        </div>
        {selectedRuns.length >= 2 ? (
          <>
            <NormalizedReturnChart locale={locale} runs={selectedRuns} />
            <div className="run-comparison-table">
              {selectedRuns.map((run, index) => (
                <article key={run.run_id}>
                  <div className="comparison-run-title">
                    <i style={{ backgroundColor: colors[index] }} />
                    <div><strong>{humanize(run.strategy.name)}</strong><code>{run.run_id}</code></div>
                  </div>
                  <dl>
                    <div><dt>{t.window}</dt><dd>{formatWindow(run, localeTag)}</dd></div>
                    <div><dt>{t.parameters}</dt><dd>{formatParameters(run.strategy.parameters)}</dd></div>
                    <div><dt>{t.costs}</dt><dd>{run.config.fee_bps} / {run.config.slippage_bps} bps</dd></div>
                    <div><dt>{t.trades}</dt><dd>{run.metrics.trade_count}</dd></div>
                    <div><dt>{t.fee}</dt><dd>{formatMoney(run.metrics.fees_paid, localeTag)}</dd></div>
                    <div><dt>{t.created}</dt><dd>{new Date(run.created_at).toLocaleString(localeTag)}</dd></div>
                  </dl>
                </article>
              ))}
            </div>
          </>
        ) : null}
      </section>
    </section>
  );
}

function RunMetric({ label, value, tone }: { label: string; value: string; tone?: number }) {
  const className = tone === undefined ? "" : tone > 0 ? "positive" : tone < 0 ? "negative" : "";
  return <div className="run-card-metric"><span>{label}</span><strong className={className}>{value}</strong></div>;
}

function NormalizedReturnChart({ runs, locale }: { runs: ExperimentVisualization[]; locale: Locale }) {
  const width = 760;
  const height = 260;
  const padding = { top: 20, right: 18, bottom: 34, left: 58 };
  const series = runs.map((run) => ({
    run,
    values: sampleSeries(
      run.equity.map((point) => point.equity / run.metrics.initial_equity - 1),
      600,
    ),
  }));
  const allValues = series.flatMap((item) => item.values);
  let minimum = Math.min(0, ...allValues);
  let maximum = Math.max(0, ...allValues);
  if (maximum - minimum < 0.01) {
    maximum += 0.005;
    minimum -= 0.005;
  }
  const x = (index: number, length: number) => padding.left + (index / Math.max(1, length - 1)) * (width - padding.left - padding.right);
  const y = (value: number) => padding.top + ((maximum - value) / (maximum - minimum)) * (height - padding.top - padding.bottom);
  const ticks = [minimum, (minimum + maximum) / 2, maximum];
  const percent = new Intl.NumberFormat(locale === "zh" ? "zh-CN" : "en-US", { style: "percent", maximumFractionDigits: 1 });
  return (
    <div className="normalized-chart">
      <svg aria-label={copy[locale].chartTitle} role="img" viewBox={`0 0 ${width} ${height}`}>
        {ticks.map((tick) => <g key={tick}><line x1={padding.left} x2={width - padding.right} y1={y(tick)} y2={y(tick)} /><text x={padding.left - 10} y={y(tick) + 4}>{percent.format(tick)}</text></g>)}
        {series.map((item, index) => (
          <polyline
            fill="none"
            key={item.run.run_id}
            points={item.values.map((value, pointIndex) => `${x(pointIndex, item.values.length)},${y(value)}`).join(" ")}
            stroke={colors[index]}
            strokeWidth="2.5"
            vectorEffect="non-scaling-stroke"
          />
        ))}
        <text className="chart-axis-label" x={(padding.left + width - padding.right) / 2} y={height - 6}>{copy[locale].progress}</text>
      </svg>
    </div>
  );
}

function humanize(value: string): string {
  return value.split("-").map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");
}

function sampleSeries(values: number[], maximum: number): number[] {
  if (values.length <= maximum) return values;
  const sampled = Array.from({ length: maximum }, (_, index) => {
    const sourceIndex = Math.round((index / (maximum - 1)) * (values.length - 1));
    return values[sourceIndex];
  });
  sampled[0] = values[0];
  sampled[sampled.length - 1] = values[values.length - 1];
  return sampled;
}

function formatPercent(value: number, locale: string): string {
  return new Intl.NumberFormat(locale, { style: "percent", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}

function formatMoney(value: number, locale: string): string {
  return new Intl.NumberFormat(locale, { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
}

function formatParameters(parameters: Record<string, string | number>): string {
  return Object.entries(parameters).map(([key, value]) => `${key}=${value}`).join(" · ");
}

function formatWindow(run: ExperimentVisualization, locale: string): string {
  const start = run.dataset.data_start ?? run.equity.at(0)?.time;
  const end = run.dataset.data_end ?? run.equity.at(-1)?.time;
  if (!start || !end) return "—";
  const formatter = new Intl.DateTimeFormat(locale, { year: "numeric", month: "short", day: "numeric" });
  return `${formatter.format(new Date(start))} – ${formatter.format(new Date(end))}`;
}
