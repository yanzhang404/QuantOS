"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  type ExperimentVisualization,
  getStrategyCatalog,
} from "./backtest-api";
import { BacktestLab } from "./backtest-lab";
import { getBacktestDataset } from "./market-data-coverage";
import type {
  Asset,
  Period,
  StrategyName,
} from "./research-data";
import {
  fallbackStrategyCatalog,
  mergeStrategyCatalog,
  type StrategyCategory,
  type StrategyInterval,
} from "./strategy-catalog";
import {
  type Bar,
  type Fill,
  getVisualizationDataset,
  type VisualizationRun,
  visualizationSchemaVersion,
} from "./visualization-data";

type Locale = "en" | "zh";

type Props = {
  asset: Asset;
  period: Period;
  locale: Locale;
  onAssetChange: (asset: Asset) => void;
  onPeriodChange: (period: Period) => void;
};

const categories: StrategyCategory[] = [
  "trend",
  "mean-reversion",
  "intraday",
  "benchmark",
];

const intervals: StrategyInterval[] = ["5m", "15m", "1h", "4h", "1d"];

const copy = {
  en: {
    eyebrow: "Strategy workbench",
    title: "Price, decisions, and risk—on one clock.",
    intro:
      "Inspect the exact fills and portfolio path behind every aggregate result.",
    strategy: "Strategy",
    market: "Market",
    period: "Window",
    periods: { evaluation: "Evaluation", development: "Development" },
    names: {
      "donchian-atr": "Donchian ATR",
      "ema-cross": "EMA 20 / 50",
      "buy-and-hold": "Buy & Hold",
    },
    descriptions: {
      "donchian-atr": "Breakout with volatility-sized exposure",
      "ema-cross": "Long-only trend confirmation baseline",
      "buy-and-hold": "Passive market exposure benchmark",
    },
    bars: "bars",
    priceChart: "Kline + executed fills",
    chartHint: "Move across the chart to inspect a bar",
    buy: "Buy",
    sell: "Sell",
    open: "O",
    high: "H",
    low: "L",
    close: "C",
    equity: "Portfolio equity",
    equityHint: "Changes only while the strategy has market exposure",
    drawdown: "Underwater drawdown",
    currentPosition: "Current position",
    flat: "Flat",
    units: "units",
    fills: "Visible fills",
    time: "Time",
    side: "Side",
    price: "Price",
    quantity: "Quantity",
    fee: "Fee",
    reason: "Execution reason",
    noFills: "No fills in the selected chart range.",
    clickHint: "Select a fill to locate it on the Kline chart.",
    run: "Run",
    source: "Immutable source",
    manualResult: "Manual backtest result",
    parameters: "Parameters",
    features: "Resolved features",
    library: "Strategy library",
    categories: {
      trend: "Trend following",
      benchmark: "Benchmarks",
      "mean-reversion": "Mean reversion",
      intraday: "Intraday / Daytrade",
    },
    emptyFolder: "No approved strategy yet",
    stages: {
      candidate: "candidate",
      validated: "validated",
      benchmark: "benchmark",
    },
    finalCapital: "Final capital",
    pnl: "Net P&L",
    feesPaid: "Fees paid",
    totalReturn: "Total return",
    interval: "Timeframe",
    intervalUnavailable: "not supported by this strategy",
    selectedMetrics: "Selected run results",
    pendingRun: "Run a backtest to load this timeframe's exact Klines and results.",
  },
  zh: {
    eyebrow: "策略工作台",
    title: "价格、交易决策与风险，统一在同一时间轴。",
    intro: "查看每个汇总结果背后的真实成交与投资组合变化。",
    strategy: "策略",
    market: "市场",
    period: "区间",
    periods: { evaluation: "评估期", development: "开发期" },
    names: {
      "donchian-atr": "唐奇安 ATR",
      "ema-cross": "EMA 20 / 50",
      "buy-and-hold": "买入并持有",
    },
    descriptions: {
      "donchian-atr": "突破信号与波动率动态仓位",
      "ema-cross": "仅做多的趋势确认基线",
      "buy-and-hold": "被动市场敞口基准",
    },
    bars: "根 K 线",
    priceChart: "K 线与实际成交",
    chartHint: "移动鼠标查看每根 K 线",
    buy: "买入",
    sell: "卖出",
    open: "开",
    high: "高",
    low: "低",
    close: "收",
    equity: "投资组合权益",
    equityHint: "仅在策略持仓期间随市场变化",
    drawdown: "水下回撤",
    currentPosition: "当前仓位",
    flat: "空仓",
    units: "单位",
    fills: "可见成交",
    time: "时间",
    side: "方向",
    price: "价格",
    quantity: "数量",
    fee: "手续费",
    reason: "成交原因",
    noFills: "当前图表区间内没有成交。",
    clickHint: "点击成交记录可在 K 线图中定位。",
    run: "运行",
    source: "不可变数据源",
    manualResult: "手动回测结果",
    parameters: "参数",
    features: "已解析特征",
    library: "策略库",
    categories: {
      trend: "趋势策略",
      benchmark: "基准策略",
      "mean-reversion": "均值回归",
      intraday: "日内 / Daytrade",
    },
    emptyFolder: "暂无已验证策略",
    stages: {
      candidate: "候选",
      validated: "已验证",
      benchmark: "基准",
    },
    finalCapital: "最终金额",
    pnl: "净盈亏",
    feesPaid: "支付费用",
    totalReturn: "总收益",
    interval: "时间尺度",
    intervalUnavailable: "当前策略不支持此时间尺度",
    selectedMetrics: "当前回测结果",
    pendingRun: "运行一次回测后，将加载该时间尺度的真实 K 线与结果。",
  },
} as const;

export function StrategyWorkbench({
  asset,
  period,
  locale,
  onAssetChange,
  onPeriodChange,
}: Props) {
  const [strategy, setStrategy] = useState<StrategyName>("donchian-atr");
  const [selectedInterval, setSelectedInterval] =
    useState<StrategyInterval>("4h");
  const [barCount, setBarCount] = useState(120);
  const [focus, setFocus] = useState<{ context: string; time: string }>();
  const [selectedExperiment, setSelectedExperiment] =
    useState<ExperimentVisualization>();
  const [catalog, setCatalog] = useState(fallbackStrategyCatalog);
  const t = copy[locale];
  const dataset = useMemo(
    () => getVisualizationDataset(asset, period),
    [asset, period],
  );
  const executionDataset = useMemo(
    () =>
      getBacktestDataset(
        asset === "btc" ? "BTCUSDT" : "ETHUSDT",
        selectedInterval,
        period,
      ),
    [asset, period, selectedInterval],
  );
  const definition =
    catalog.find((item) => item.name === strategy) ??
    fallbackStrategyCatalog.find((item) => item.name === strategy)!;
  const selectedExperimentMatches =
    selectedExperiment?.dataset.version === executionDataset.version &&
    selectedExperiment.dataset.content_sha256 === executionDataset.content_sha256 &&
    selectedExperiment.dataset.symbol === executionDataset.symbol &&
    selectedExperiment.dataset.interval === executionDataset.interval &&
    selectedExperiment.strategy.name === strategy;
  const run: VisualizationRun = selectedExperimentMatches
    ? selectedExperiment
    : dataset.runs[strategy];
  const chartBars = selectedExperimentMatches && selectedExperiment.bars.length
    ? selectedExperiment.bars
    : dataset.bars;
  const visibleBars = chartBars.slice(-barCount);
  const visibleStart = Date.parse(visibleBars[0]?.time ?? "");
  const visibleEnd = Date.parse(visibleBars.at(-1)?.time ?? "");
  const visibleFills = run.fills.filter((fill) => {
    const timestamp = Date.parse(fill.time);
    return timestamp >= visibleStart && timestamp <= visibleEnd + 4 * 60 * 60 * 1000;
  });
  const localeTag = locale === "zh" ? "zh-CN" : "en-US";
  const focusContext = `${asset}-${period}-${selectedInterval}-${strategy}-${barCount}`;
  const focusTime = focus?.context === focusContext ? focus.time : undefined;
  const finalEquity =
    run.metrics.final_equity ?? run.equity.at(-1)?.equity ?? 0;
  const initialEquity =
    run.metrics.initial_equity ??
    (1 + run.metrics.total_return
      ? finalEquity / (1 + run.metrics.total_return)
      : run.equity[0]?.equity ?? 0);
  const netProfit = finalEquity - initialEquity;
  const loadExperiment = useCallback(
    (experiment: ExperimentVisualization) => {
      onAssetChange(experiment.dataset.symbol === "ETHUSDT" ? "eth" : "btc");
      setSelectedInterval(experiment.dataset.interval);
      onPeriodChange(
        experiment.dataset.data_start === "2021-01-01T00:00:00Z"
          ? "development"
          : "evaluation",
      );
      setStrategy(experiment.strategy.name);
      setFocus(undefined);
      setSelectedExperiment(experiment);
    },
    [onAssetChange, onPeriodChange],
  );

  const clearManualResult = () => {
    setSelectedExperiment(undefined);
    setFocus(undefined);
  };

  useEffect(() => {
    const controller = new AbortController();
    void getStrategyCatalog(controller.signal)
      .then((records) => setCatalog(mergeStrategyCatalog(records)))
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  return (
    <section className="workbench panel" id="strategies">
      <section className="result-summary" aria-label={t.selectedMetrics}>
        <header className="result-summary-header">
          <div>
            <span>{t.selectedMetrics}</span>
            <strong>{t.names[strategy]}</strong>
            <small>
              {asset.toUpperCase()} / USDT ·{" "}
              {selectedExperimentMatches
                ? selectedExperiment.dataset.interval
                : dataset.interval} ·{" "}
              {t.periods[period]}
            </small>
          </div>
          <div className="result-run-ref">
            <span>
              {t.run} {run.run_id}
            </span>
            <small>
              {t.source} ·{" "}
              {selectedExperimentMatches
                ? selectedExperiment.dataset.version
                : dataset.dataset_version} · schema{" "}
              {visualizationSchemaVersion}
            </small>
          </div>
        </header>

        <div className="result-metrics">
          <div className="primary-return">
            <span>{t.totalReturn}</span>
            <strong
              className={run.metrics.total_return >= 0 ? "positive" : "negative"}
            >
              {formatPercent(run.metrics.total_return, localeTag)}
            </strong>
          </div>
          <div>
            <span>{t.finalCapital}</span>
            <strong>{formatMoney(finalEquity, localeTag)}</strong>
          </div>
          <div>
            <span>{t.pnl}</span>
            <strong className={netProfit >= 0 ? "positive" : "negative"}>
              {formatSignedMoney(netProfit, localeTag)}
            </strong>
            <small>
              {t.feesPaid} {formatMoney(run.metrics.fees_paid, localeTag)}
            </small>
          </div>
          <div>
            <span>{locale === "zh" ? "最大回撤" : "Max drawdown"}</span>
            <strong className="negative">
              {formatPercent(-run.metrics.max_drawdown, localeTag)}
            </strong>
          </div>
          <div>
            <span>{locale === "zh" ? "交易 / 成交" : "Trades / fills"}</span>
            <strong>
              {run.metrics.trade_count} / {run.metrics.fill_count}
            </strong>
            <small>
              {locale === "zh" ? "夏普比率" : "Sharpe"}{" "}
              {run.metrics.sharpe_ratio === null
                ? "—"
                : run.metrics.sharpe_ratio.toFixed(2)}
            </small>
          </div>
        </div>
      </section>

      <aside className="strategy-library" aria-label={t.library}>
        <div className="library-title">
          <span aria-hidden="true">⌘</span>
          <strong>{t.library}</strong>
          <small>{String(catalog.length).padStart(2, "0")}</small>
        </div>
        {categories.map((category) => {
          const members = catalog.filter((item) => item.category === category);
          return (
            <div className="strategy-folder" key={category}>
              <div className="folder-label">
                <span aria-hidden="true">▾</span>
                <strong>{t.categories[category]}</strong>
              </div>
              {members.length ? (
                members.map((item) => (
                  <button
                    aria-pressed={strategy === item.name}
                    className={strategy === item.name ? "selected" : ""}
                    key={item.name}
                    onClick={() => {
                      clearManualResult();
                      setStrategy(item.name);
                      setSelectedInterval((current) =>
                        item.supported_intervals.includes(current)
                          ? current
                          : item.supported_intervals[0],
                      );
                    }}
                    type="button"
                  >
                    <span>{item.label}</span>
                    <small className={item.stage}>{t.stages[item.stage]}</small>
                  </button>
                ))
              ) : (
                <p>{t.emptyFolder}</p>
              )}
            </div>
          );
        })}
        <div className="implementation-ref">
          <span>{locale === "zh" ? "策略代码" : "Implementation"}</span>
          <code>
            {definition.implementation?.split(".").at(-1) ?? definition.name}
          </code>
        </div>
      </aside>

      <div className="workbench-controls">
        <div className="timeframe-picker" aria-label={t.interval}>
          <span>{t.interval}</span>
          <div>
          {intervals.map((interval) => {
            const available = definition.supported_intervals.includes(interval);
            return (
            <button
              aria-pressed={interval === selectedInterval}
              className={interval === selectedInterval ? "selected" : ""}
              disabled={!available}
              key={interval}
              onClick={() => {
                clearManualResult();
                setSelectedInterval(interval);
              }}
              title={!available ? t.intervalUnavailable : undefined}
              type="button"
            >
              {interval}
            </button>
            );
          })}
          </div>
        </div>
        <div className="workbench-filters">
          <label>
            <span>{t.market}</span>
            <select
              onChange={(event) => {
                clearManualResult();
                onAssetChange(event.target.value as Asset);
              }}
              value={asset}
            >
              <option value="btc">BTC / USDT</option>
              <option value="eth">ETH / USDT</option>
            </select>
          </label>
          <label>
            <span>{t.period}</span>
            <select
              onChange={(event) => {
                clearManualResult();
                onPeriodChange(event.target.value as Period);
              }}
              value={period}
            >
              <option value="evaluation">{t.periods.evaluation}</option>
              <option value="development">{t.periods.development}</option>
            </select>
          </label>
        </div>
      </div>

      <BacktestLab
        dataset={executionDataset}
        definition={definition}
        locale={locale}
        onExperimentLoaded={loadExperiment}
        strategy={strategy}
      />

      {selectedExperimentMatches ? (
        <div className="active-run-banner" role="status">
          <div>
            <span>{t.manualResult}</span>
            <code>{selectedExperiment.run_id}</code>
          </div>
          <p>
            <strong>{t.parameters}</strong>{" "}
            {Object.entries(selectedExperiment.strategy.parameters)
              .map(([key, value]) => `${key}=${value}`)
              .join(" · ")}
          </p>
          {selectedExperiment.features.length > 0 ? (
            <p>
              <strong>{t.features}</strong>{" "}
              {selectedExperiment.features
                .map((feature) => `${feature.instance}=${feature.warmup_bars}`)
                .join(" · ")}
            </p>
          ) : null}
        </div>
      ) : null}

      {!selectedExperimentMatches && selectedInterval !== dataset.interval ? (
        <div className="active-run-banner pending-run" role="status">
          <div>
            <span>{selectedInterval}</span>
            <code>{executionDataset.version}</code>
          </div>
          <p>{t.pendingRun}</p>
        </div>
      ) : null}

      <div className="chart-panel price-panel">
        <div className="chart-heading">
          <div>
            <strong>{t.priceChart}</strong>
            <span>{t.chartHint}</span>
          </div>
          <div className="range-picker" aria-label={t.bars}>
            {[60, 120, 240].map((value) => (
              <button
                aria-pressed={barCount === value}
                className={barCount === value ? "selected" : ""}
                key={value}
                onClick={() => setBarCount(value)}
                type="button"
              >
                {value}
              </button>
            ))}
            <span>{t.bars}</span>
          </div>
        </div>
        <CandlestickChart
          bars={visibleBars}
          fills={visibleFills}
          focusTime={focusTime}
          locale={locale}
          labels={t}
        />
      </div>

      <div className="performance-grid">
        <PerformanceChart locale={locale} run={run} labels={t} />
      </div>

      <div className="fills-section">
        <div className="fills-heading">
          <div>
            <strong>
              {t.fills} <span>{visibleFills.length}</span>
            </strong>
            <p>{t.clickHint}</p>
          </div>
          <code>
            {t.run} {run.run_id}
          </code>
        </div>
        {visibleFills.length ? (
          <div className="fills-table-wrap">
            <table className="fills-table">
              <thead>
                <tr>
                  <th>{t.time}</th>
                  <th>{t.side}</th>
                  <th>{t.price}</th>
                  <th>{t.quantity}</th>
                  <th>{t.fee}</th>
                  <th>{t.reason}</th>
                </tr>
              </thead>
              <tbody>
                {[...visibleFills].reverse().slice(0, 12).map((fill) => (
                  <tr
                    key={`${fill.time}-${fill.quantity}`}
                    onClick={() =>
                      setFocus({ context: focusContext, time: fill.time })
                    }
                    tabIndex={0}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        setFocus({ context: focusContext, time: fill.time });
                      }
                    }}
                  >
                    <td>{formatTime(fill.time, localeTag)}</td>
                    <td>
                      <span className={`side-tag ${fill.side}`}>
                        {fill.side === "buy" ? t.buy : t.sell}
                      </span>
                    </td>
                    <td>{formatPrice(fill.price, localeTag)}</td>
                    <td>{fill.quantity.toFixed(asset === "btc" ? 4 : 3)}</td>
                    <td>${fill.fee.toFixed(2)}</td>
                    <td>{localizeReason(fill.reason, locale)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty-fills">{t.noFills}</p>
        )}
      </div>
    </section>
  );
}

type Copy = (typeof copy)[Locale];

function CandlestickChart({
  bars,
  fills,
  focusTime,
  locale,
  labels,
}: {
  bars: Bar[];
  fills: Fill[];
  focusTime?: string;
  locale: Locale;
  labels: Copy;
}) {
  const [hovered, setHovered] = useState<number>();
  const width = 1000;
  const height = 360;
  const left = 18;
  const right = 78;
  const top = 20;
  const bottom = 38;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const low = Math.min(...bars.map((bar) => bar.low));
  const high = Math.max(...bars.map((bar) => bar.high));
  const padding = Math.max((high - low) * 0.06, high * 0.002);
  const minPrice = low - padding;
  const maxPrice = high + padding;
  const step = plotWidth / bars.length;
  const candleWidth = Math.max(1.2, step * 0.58);
  const y = (value: number) =>
    top + ((maxPrice - value) / (maxPrice - minPrice)) * plotHeight;
  const indexForTime = (time: string) => {
    const target = Date.parse(time);
    let nearest = 0;
    let distance = Number.POSITIVE_INFINITY;
    bars.forEach((bar, index) => {
      const next = Math.abs(Date.parse(bar.time) - target);
      if (next < distance) {
        distance = next;
        nearest = index;
      }
    });
    return nearest;
  };
  const activeIndex =
    focusTime !== undefined ? indexForTime(focusTime) : hovered;
  const activeBar = activeIndex === undefined ? undefined : bars[activeIndex];
  const activeFills =
    activeIndex === undefined
      ? []
      : fills.filter((fill) => indexForTime(fill.time) === activeIndex);
  const localeTag = locale === "zh" ? "zh-CN" : "en-US";
  const dateTickIndexes = Array.from(
    new Set(
      Array.from({ length: 6 }, (_, index) =>
        Math.round((index / 5) * (bars.length - 1)),
      ),
    ),
  );

  return (
    <div className="candlestick-wrap">
      <svg
        aria-label={labels.priceChart}
        className="candlestick-chart"
        onMouseLeave={() => setHovered(undefined)}
        onMouseMove={(event) => {
          const rect = event.currentTarget.getBoundingClientRect();
          const cursor = ((event.clientX - rect.left) / rect.width) * width;
          const index = Math.floor((cursor - left) / step);
          setHovered(Math.max(0, Math.min(bars.length - 1, index)));
        }}
        role="img"
        viewBox={`0 0 ${width} ${height}`}
      >
        {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
          const gridY = top + ratio * plotHeight;
          const price = maxPrice - ratio * (maxPrice - minPrice);
          return (
            <g key={ratio}>
              <line
                className="chart-grid-line"
                x1={left}
                x2={width - right}
                y1={gridY}
                y2={gridY}
              />
              <text
                className="chart-axis-label"
                x={width - right + 10}
                y={gridY + 4}
              >
                {formatCompactPrice(price, localeTag)}
              </text>
            </g>
          );
        })}
        {dateTickIndexes.map((index) => {
          const x = left + index * step + step / 2;
          return (
            <g className="date-tick" key={bars[index].time}>
              <line
                x1={x}
                x2={x}
                y1={height - bottom}
                y2={height - bottom + 5}
              />
              <text x={x} y={height - bottom + 20}>
                {formatAxisDate(bars[index].time, localeTag)}
              </text>
            </g>
          );
        })}
        {bars.map((bar, index) => {
          const x = left + index * step + step / 2;
          const rising = bar.close >= bar.open;
          const bodyTop = y(Math.max(bar.open, bar.close));
          const bodyHeight = Math.max(1, Math.abs(y(bar.open) - y(bar.close)));
          return (
            <g className={rising ? "candle rising" : "candle falling"} key={bar.time}>
              <line x1={x} x2={x} y1={y(bar.high)} y2={y(bar.low)} />
              <rect
                height={bodyHeight}
                width={candleWidth}
                x={x - candleWidth / 2}
                y={bodyTop}
              />
            </g>
          );
        })}
        {fills.map((fill) => {
          const index = indexForTime(fill.time);
          const x = left + index * step + step / 2;
          const markerY =
            fill.side === "buy"
              ? Math.min(height - bottom - 6, y(bars[index].low) + 15)
              : Math.max(top + 6, y(bars[index].high) - 15);
          return (
            <g
              className={`fill-marker ${fill.side}`}
              key={`${fill.time}-${fill.quantity}`}
            >
              <title>
                {`${fill.side === "buy" ? labels.buy : labels.sell} · ${formatFullDate(fill.time, localeTag)} · ${formatPrice(fill.price, localeTag)} · ${labels.fee} $${fill.fee.toFixed(2)}`}
              </title>
              <circle cx={x} cy={markerY} r={5.5} />
              <text x={x} y={markerY + 2.8}>
                {fill.side === "buy" ? "B" : "S"}
              </text>
            </g>
          );
        })}
        {activeBar && activeIndex !== undefined ? (
          <g className="crosshair">
            <line
              x1={left + activeIndex * step + step / 2}
              x2={left + activeIndex * step + step / 2}
              y1={top}
              y2={height - bottom}
            />
            <line
              x1={left}
              x2={width - right}
              y1={y(activeBar.close)}
              y2={y(activeBar.close)}
            />
          </g>
        ) : null}
      </svg>
      {activeBar ? (
        <div className="chart-tooltip">
          <strong>{formatTime(activeBar.time, localeTag)}</strong>
          <span>
            {labels.open} {formatCompactPrice(activeBar.open, localeTag)}
          </span>
          <span>
            {labels.high} {formatCompactPrice(activeBar.high, localeTag)}
          </span>
          <span>
            {labels.low} {formatCompactPrice(activeBar.low, localeTag)}
          </span>
          <span>
            {labels.close} {formatCompactPrice(activeBar.close, localeTag)}
          </span>
          {activeFills.map((fill) => (
            <span
              className={`tooltip-fill ${fill.side}`}
              key={`${fill.time}-${fill.quantity}`}
            >
              {fill.side === "buy" ? labels.buy : labels.sell} ·{" "}
              {formatFullDate(fill.time, localeTag)} ·{" "}
              {formatPrice(fill.price, localeTag)} · {labels.fee} $
              {fill.fee.toFixed(2)}
            </span>
          ))}
        </div>
      ) : null}
      <div className="chart-legend">
        <span className="buy-dot" /> {labels.buy}
        <span className="sell-dot" /> {labels.sell}
      </div>
    </div>
  );
}

function PerformanceChart({
  run,
  locale,
  labels,
}: {
  run: VisualizationRun;
  locale: Locale;
  labels: Copy;
}) {
  const [hoveredIndex, setHoveredIndex] = useState<number>();
  const width = 720;
  const height = 244;
  const left = 10;
  const right = 10;
  const equityTop = 22;
  const equityBottom = 126;
  const drawdownTop = 156;
  const drawdownBottom = 208;
  const axisLabelY = 232;
  const values = run.equity.map((point) => point.equity);
  const minEquity = Math.min(...values);
  const maxEquity = Math.max(...values);
  const equityRange = Math.max(1, maxEquity - minEquity);
  const maxDrawdown = Math.min(
    -0.01,
    ...run.equity.map((point) => point.drawdown),
  );
  const firstTime = Date.parse(run.equity[0]?.time ?? "");
  const lastTime = Date.parse(run.equity.at(-1)?.time ?? "");
  const timeRange = Math.max(1, lastTime - firstTime);
  const xForTime = (time: string) =>
    left +
    ((Date.parse(time) - firstTime) / timeRange) * (width - left - right);
  const x = (index: number) => xForTime(run.equity[index].time);
  const equityY = (value: number) =>
    equityTop +
    ((maxEquity - value) / equityRange) * (equityBottom - equityTop);
  const drawdownY = (value: number) =>
    drawdownTop +
    (value / maxDrawdown) * (drawdownBottom - drawdownTop);
  const equityPath = linePath(run.equity.map((point) => point.equity), x, equityY);
  const drawdownLine = linePath(
    run.equity.map((point) => point.drawdown),
    x,
    drawdownY,
  );
  const last = run.equity.at(-1);
  const localeTag = locale === "zh" ? "zh-CN" : "en-US";
  const performanceDateTickIndexes = Array.from(
    new Set(
      Array.from({ length: 6 }, (_, index) =>
        Math.round((index / 5) * (run.equity.length - 1)),
      ),
    ),
  );
  const activePoint =
    hoveredIndex === undefined ? undefined : run.equity[hoveredIndex];
  const activeX = activePoint ? xForTime(activePoint.time) : undefined;

  return (
    <div className="chart-panel performance-panel">
      <div className="chart-heading">
        <div>
          <strong>{labels.equity}</strong>
          <span>{labels.equityHint}</span>
        </div>
        <div className="position-readout">
          <span>{labels.currentPosition}</span>
          <strong>
            {last && last.position
              ? `${last.position.toFixed(4)} ${labels.units}`
              : labels.flat}
          </strong>
          <small>{last ? formatMoney(last.equity, localeTag) : "—"}</small>
        </div>
      </div>
      <svg
        aria-label={`${labels.equity} / ${labels.drawdown}`}
        className="performance-chart"
        onMouseLeave={() => setHoveredIndex(undefined)}
        onMouseMove={(event) => {
          const rect = event.currentTarget.getBoundingClientRect();
          const cursor =
            ((event.clientX - rect.left) / rect.width) * width;
          const targetTime =
            firstTime +
            ((Math.max(left, Math.min(width - right, cursor)) - left) /
              (width - left - right)) *
              timeRange;
          let nearestIndex = 0;
          let nearestDistance = Number.POSITIVE_INFINITY;
          run.equity.forEach((point, index) => {
            const distance = Math.abs(Date.parse(point.time) - targetTime);
            if (distance < nearestDistance) {
              nearestDistance = distance;
              nearestIndex = index;
            }
          });
          setHoveredIndex(nearestIndex);
        }}
        role="img"
        viewBox={`0 0 ${width} ${height}`}
      >
        {performanceDateTickIndexes.map((index) => {
          const point = run.equity[index];
          const tickX = xForTime(point.time);
          return (
            <g className="performance-date-tick" key={point.time}>
              <line
                className="performance-time-grid"
                x1={tickX}
                x2={tickX}
                y1={equityTop}
                y2={drawdownBottom}
              />
              <line
                x1={tickX}
                x2={tickX}
                y1={drawdownBottom}
                y2={drawdownBottom + 5}
              />
              <text
                textAnchor={
                  index === 0
                    ? "start"
                    : index === run.equity.length - 1
                      ? "end"
                      : "middle"
                }
                x={tickX}
                y={axisLabelY}
              >
                {formatAxisDate(point.time, localeTag)}
              </text>
            </g>
          );
        })}
        <line
          className="chart-grid-line"
          x1={left}
          x2={width - right}
          y1={equityBottom}
          y2={equityBottom}
        />
        <path className="equity-line" d={equityPath} />
        <text className="chart-caption" x={left} y={15}>
          {labels.equity}
        </text>
        <line
          className="chart-grid-line"
          x1={left}
          x2={width - right}
          y1={drawdownTop}
          y2={drawdownTop}
        />
        <path
          className="drawdown-area"
          d={`${drawdownLine} L ${width - right} ${drawdownTop} L ${left} ${drawdownTop} Z`}
        />
        <path className="drawdown-line" d={drawdownLine} />
        <text className="chart-caption" x={left} y={148}>
          {labels.drawdown} · {formatPercent(maxDrawdown, localeTag)}
        </text>
        {activePoint && activeX !== undefined ? (
          <g className="performance-crosshair">
            <line
              x1={activeX}
              x2={activeX}
              y1={equityTop}
              y2={drawdownBottom}
            />
            <circle
              cx={activeX}
              cy={equityY(activePoint.equity)}
              r={3.5}
            />
          </g>
        ) : null}
      </svg>
      {activePoint && activeX !== undefined ? (
        <div
          className={`performance-tooltip ${
            activeX > width * 0.72 ? "align-right" : ""
          }`}
          style={{ left: `${(activeX / width) * 100}%` }}
        >
          <strong>{formatFullDate(activePoint.time, localeTag)}</strong>
          <span>
            {labels.equity} {formatMoney(activePoint.equity, localeTag)}
          </span>
          <span>
            {labels.drawdown}{" "}
            {formatPercent(activePoint.drawdown, localeTag)}
          </span>
          <span>
            {labels.currentPosition}{" "}
            {activePoint.position
              ? `${activePoint.position.toFixed(4)} ${labels.units}`
              : labels.flat}
          </span>
        </div>
      ) : null}
    </div>
  );
}

function linePath(
  values: number[],
  x: (index: number) => number,
  y: (value: number) => number,
): string {
  return values
    .map((value, index) => `${index ? "L" : "M"} ${x(index)} ${y(value)}`)
    .join(" ");
}

function formatPercent(value: number, locale: string): string {
  return new Intl.NumberFormat(locale, {
    style: "percent",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function formatMoney(value: number, locale: string): string {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatSignedMoney(value: number, locale: string): string {
  const formatted = formatMoney(Math.abs(value), locale);
  return `${value >= 0 ? "+" : "−"}${formatted}`;
}

function formatPrice(value: number, locale: string): string {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

function formatCompactPrice(value: number, locale: string): string {
  return new Intl.NumberFormat(locale, {
    notation: value > 10_000 ? "compact" : "standard",
    maximumFractionDigits: value > 10_000 ? 1 : 0,
  }).format(value);
}

function formatTime(value: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).format(new Date(value));
}

function formatAxisDate(value: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    year: "2-digit",
    month: "2-digit",
    day: "2-digit",
    timeZone: "UTC",
  }).format(new Date(value));
}

function formatFullDate(value: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).format(new Date(value));
}

function localizeReason(reason: string, locale: Locale): string {
  if (locale === "en") return reason;
  if (reason.includes("forced end-of-backtest liquidation")) {
    return "回测结束强制平仓";
  }
  const exposure = reason.match(/target exposure ([0-9.]+)/)?.[1];
  return exposure ? `调整至目标仓位 ${exposure}` : reason;
}
