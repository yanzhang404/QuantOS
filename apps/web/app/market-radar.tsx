"use client";

import { useEffect, useMemo, useState } from "react";
import sampleSnapshot from "../../../examples/radar/sample-snapshot.v1.json";
import {
  getLatestRadar,
  getRadarHealth,
  type RadarRefreshHealth,
  type RadarSnapshot,
} from "./radar-api";

type Locale = "en" | "zh";

const fallback = sampleSnapshot as RadarSnapshot;

const text = {
  en: {
    eyebrow: "A-share Market Radar",
    title: "See what is heating up before chasing the leaderboard.",
    complete: "Full snapshot",
    partial: "Partial coverage",
    sample: "Sample snapshot · not current market data",
    asOf: "Shanghai time",
    healthy: "Radar healthy · last success",
    stale: "Radar stale · last success",
    failed: "Refresh failed · prior snapshot retained",
    running: "Radar refresh running",
    unknown: "Refresh status unavailable",
    themes: "Hot themes",
    rising: "30m acceleration",
    breadth: "observed movers",
    leaders: "Leading stocks",
    heat: "Heat",
    coverage: "data coverage",
    rvol: "RVOL",
    turnover: "turnover",
    speed: "30m move",
    newHigh: "20d high",
    unavailable: "not provided",
    methodology: "Deterministic methodology",
    note: "Breadth counts observed movers, not every theme constituent.",
  },
  zh: {
    eyebrow: "A 股热点雷达",
    title: "先看谁正在升温，再决定是否深入研究。",
    complete: "完整数据快照",
    partial: "部分字段覆盖",
    sample: "示例快照 · 非当前市场数据",
    asOf: "北京时间",
    healthy: "雷达运行正常 · 上次成功",
    stale: "雷达数据已过期 · 上次成功",
    failed: "刷新失败 · 已保留上一份快照",
    running: "热点雷达正在刷新",
    unknown: "刷新状态暂不可用",
    themes: "热门题材",
    rising: "30 分钟热度加速度",
    breadth: "只异动股",
    leaders: "领涨个股",
    heat: "热度",
    coverage: "数据覆盖率",
    rvol: "量比",
    turnover: "换手率",
    speed: "30 分钟涨幅",
    newHigh: "20 日新高",
    unavailable: "数据源未提供",
    methodology: "确定性计算方法",
    note: "题材广度仅统计当前已观测异动股，不代表全部成分股。",
  },
} as const;

export function MarketRadar({ locale }: { locale: Locale }) {
  const [snapshot, setSnapshot] = useState<RadarSnapshot>(fallback);
  const [health, setHealth] = useState<RadarRefreshHealth | null>(null);
  const t = text[locale];

  useEffect(() => {
    const controller = new AbortController();
    getLatestRadar(controller.signal)
      .then(setSnapshot)
      .catch(() => setSnapshot(fallback));
    getRadarHealth(controller.signal)
      .then(setHealth)
      .catch(() => setHealth(null));
    return () => controller.abort();
  }, []);

  const rising = useMemo(
    () =>
      [...snapshot.themes]
        .filter((theme) => theme.acceleration_30m !== null)
        .sort(
          (left, right) =>
            (right.acceleration_30m ?? 0) - (left.acceleration_30m ?? 0) ||
            right.heat_score - left.heat_score,
        ),
    [snapshot],
  );
  const date = formatDate(snapshot.as_of, locale);
  const successDate = health?.last_success_at
    ? formatDate(health.last_success_at, locale)
    : null;
  const statusText =
    snapshot.status === "complete"
      ? t.complete
      : snapshot.status === "partial"
        ? t.partial
        : t.sample;
  const healthText = !health
    ? t.unknown
    : health.state === "running"
      ? t.running
      : health.state === "failed"
        ? t.failed
        : health.stale
          ? `${t.stale} ${successDate ?? "-"}`
          : `${t.healthy} ${successDate ?? "-"}`;
  const healthTone = !health
    ? "unknown"
    : health.state === "failed" || health.stale
      ? "warning"
      : health.state;

  return (
    <section className="market-radar panel" id="market-radar">
      <header className="radar-heading">
        <div>
          <p className="eyebrow">{t.eyebrow}</p>
          <h2>{t.title}</h2>
        </div>
        <div className="radar-state">
          <span className={`radar-status ${snapshot.status}`}>{statusText}</span>
          <small className={`radar-health ${healthTone}`}>{healthText}</small>
          <small>
            {t.asOf} · {date}
          </small>
        </div>
      </header>

      <div className="radar-pulse">
        <div>
          <span>{t.themes}</span>
          <strong>{snapshot.summary.hottest_theme ?? "-"}</strong>
        </div>
        <div>
          <span>{t.rising}</span>
          <strong>{snapshot.summary.fastest_rising_theme ?? "-"}</strong>
        </div>
        <div>
          <span>{t.leaders}</span>
          <strong>{snapshot.summary.leader_symbol ?? "-"}</strong>
        </div>
      </div>

      <div className="radar-grid">
        <article className="theme-radar">
          <div className="radar-subheading">
            <h3>{t.themes}</h3>
            <span>{rising.length ? t.rising : snapshot.provenance.provider}</span>
          </div>
          <div className="theme-rows">
            {snapshot.themes.slice(0, 6).map((theme) => (
              <div key={theme.name}>
                <span className="theme-rank">{String(theme.rank).padStart(2, "0")}</span>
                <div>
                  <strong>{theme.name}</strong>
                  <i>
                    <b style={{ width: `${theme.heat_score}%` }} />
                  </i>
                </div>
                <span>
                  {theme.observed_breadth} {t.breadth}
                </span>
                <strong>{theme.heat_score.toFixed(0)}</strong>
                <em className={(theme.acceleration_30m ?? 0) > 0 ? "positive" : "muted"}>
                  {formatAcceleration(theme.acceleration_30m)}
                </em>
              </div>
            ))}
          </div>
          <p className="radar-note">{t.note}</p>
        </article>

        <article className="stock-radar">
          <div className="radar-subheading">
            <h3>{t.leaders}</h3>
            <a
              href="https://github.com/yanzhang404/QuantOS/blob/main/docs/adr/0028-deterministic-a-share-market-radar.md"
              rel="noreferrer"
              target="_blank"
            >
              {t.methodology}
            </a>
          </div>
          <div className="stock-rows">
            {snapshot.stocks.slice(0, 5).map((stock) => (
              <details key={stock.symbol}>
                <summary>
                  <span>{String(stock.rank).padStart(2, "0")}</span>
                  <div>
                    <strong>{stock.name}</strong>
                    <small>{stock.symbol}</small>
                  </div>
                  <em>+{stock.change_pct.toFixed(1)}%</em>
                  <div className="stock-heat">
                    <span>{t.heat}</span>
                    <strong>{stock.heat_score.toFixed(0)}</strong>
                  </div>
                  <b>{formatAcceleration(stock.acceleration_30m)}</b>
                </summary>
                <div className="stock-detail">
                  <div className="stock-metrics">
                    <Metric label={t.rvol} value={formatNumber(stock.relative_volume, "×", t.unavailable)} />
                    <Metric label={t.turnover} value={formatNumber(stock.turnover_pct, "%", t.unavailable)} />
                    <Metric label={t.speed} value={formatNumber(stock.change_30m_pct, "%", t.unavailable, true)} />
                    <Metric
                      label={t.newHigh}
                      value={
                        stock.new_high_20d === null
                          ? t.unavailable
                          : stock.new_high_20d
                            ? "✓"
                            : "—"
                      }
                    />
                  </div>
                  <div className="stock-tags">
                    {stock.themes.map((theme) => (
                      <span key={theme}>{theme}</span>
                    ))}
                  </div>
                  <p>{stock.signals.join(" · ")}</p>
                  <footer>
                    <a href={stock.source_url} rel="noreferrer" target="_blank">
                      {snapshot.provenance.provider}
                    </a>
                    <span>
                      {Math.round(stock.data_coverage * 100)}% {t.coverage}
                    </span>
                    {stock.catalyst ? (
                      <a href={stock.catalyst.url} rel="noreferrer" target="_blank">
                        {stock.catalyst.title}
                      </a>
                    ) : null}
                  </footer>
                </div>
              </details>
            ))}
          </div>
        </article>
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function formatAcceleration(value: number | null) {
  return value === null ? "—" : `${value >= 0 ? "+" : ""}${value.toFixed(0)}`;
}

function formatNumber(
  value: number | null,
  suffix: string,
  unavailable: string,
  signed = false,
) {
  if (value === null) return unavailable;
  return `${signed && value >= 0 ? "+" : ""}${value.toFixed(1)}${suffix}`;
}

function formatDate(value: string, locale: Locale) {
  return new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Shanghai",
  }).format(new Date(value));
}
