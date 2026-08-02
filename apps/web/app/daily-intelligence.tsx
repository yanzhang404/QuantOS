"use client";

import { useEffect, useState } from "react";
import sampleSnapshot from "../../../examples/intelligence/sample-snapshot.v1.json";
import {
  getIntelligenceHealth,
  getLatestIntelligence,
  type IntelligenceRefreshHealth,
  type IntelligenceSnapshot,
} from "./intelligence-api";

type Locale = "en" | "zh";

const fallback = sampleSnapshot as IntelligenceSnapshot;

const text = {
  en: {
    eyebrow: "Daily market intelligence",
    title: "Sentiment first. Sources attached.",
    live: "Published snapshot",
    partial: "Partial snapshot",
    sample: "Sample snapshot · not current market data",
    asOf: "As of",
    previous: "vs previous",
    market: "Market score",
    news: "News score",
    drivers: "Factor detail",
    brief: "Daily brief",
    sources: "Source-linked news",
    methodology: "Deterministic methodology",
    details: "View factor detail and daily brief",
    refreshUnknown: "Refresh status unavailable",
    refreshRunning: "Daily refresh running",
    refreshFailed: "Refresh failed · prior snapshot retained",
    refreshStale: "Data stale · last success",
    refreshHealthy: "Refresh healthy · last success",
    labels: {
      extreme_fear: "Extreme fear",
      fear: "Fear",
      neutral: "Neutral",
      greed: "Greed",
      extreme_greed: "Extreme greed",
    },
    factors: {
      crypto_volatility: "Crypto volatility",
      options_positioning: "Options positioning",
      perpetual_positioning: "Perpetual positioning",
      momentum_volume: "Momentum & volume",
      liquidation_balance: "Liquidation balance",
      market_breadth: "Market breadth",
      macro_risk: "Macro risk",
    },
  },
  zh: {
    eyebrow: "每日市场情报",
    title: "先看情绪结论，再核对数据来源。",
    live: "已发布快照",
    partial: "部分数据快照",
    sample: "示例快照 · 非当前市场数据",
    asOf: "更新于",
    previous: "较上次",
    market: "市场数据得分",
    news: "新闻情绪得分",
    drivers: "因子明细",
    brief: "每日简报",
    sources: "带来源的新闻",
    methodology: "确定性计算方法",
    details: "查看因子明细和每日报告",
    refreshUnknown: "日更状态暂不可用",
    refreshRunning: "每日数据正在刷新",
    refreshFailed: "刷新失败 · 已保留上一份快照",
    refreshStale: "数据已过期 · 上次成功",
    refreshHealthy: "日更正常 · 上次成功",
    labels: {
      extreme_fear: "极度恐惧",
      fear: "恐惧",
      neutral: "中性",
      greed: "贪婪",
      extreme_greed: "极度贪婪",
    },
    factors: {
      crypto_volatility: "加密资产波动率",
      options_positioning: "期权仓位",
      perpetual_positioning: "永续合约仓位",
      momentum_volume: "动量与成交量",
      liquidation_balance: "多空清算结构",
      market_breadth: "市场广度",
      macro_risk: "宏观风险",
    },
  },
} as const;

export function DailyIntelligence({ locale }: { locale: Locale }) {
  const [snapshot, setSnapshot] = useState<IntelligenceSnapshot>(fallback);
  const [health, setHealth] = useState<IntelligenceRefreshHealth | null>(null);
  const t = text[locale];

  useEffect(() => {
    const controller = new AbortController();
    getLatestIntelligence(controller.signal)
      .then(setSnapshot)
      .catch(() => setSnapshot(fallback));
    getIntelligenceHealth(controller.signal)
      .then(setHealth)
      .catch(() => setHealth(null));
    return () => controller.abort();
  }, []);

  const statusText =
    snapshot.status === "complete"
      ? t.live
      : snapshot.status === "partial"
        ? t.partial
        : t.sample;
  const date = new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(new Date(snapshot.as_of));
  const successDate = health?.last_success_at
    ? new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: "UTC",
      }).format(new Date(health.last_success_at))
    : null;
  const healthText = !health
    ? t.refreshUnknown
    : health.state === "running"
      ? t.refreshRunning
      : health.state === "failed"
        ? t.refreshFailed
        : health.stale
          ? `${t.refreshStale} ${successDate ?? "-"}`
          : `${t.refreshHealthy} ${successDate ?? "-"}`;
  const healthTone = !health
    ? "unknown"
    : health.state === "failed" || health.stale
      ? "warning"
      : health.state;
  const summary = locale === "zh" ? snapshot.brief.summary_zh : snapshot.brief.summary;
  const highlights =
    locale === "zh" ? snapshot.brief.highlights_zh : snapshot.brief.highlights;
  const tone =
    snapshot.label === "extreme_fear" || snapshot.label === "fear"
      ? "fear"
      : snapshot.label === "extreme_greed" || snapshot.label === "greed"
        ? "greed"
        : "neutral";

  return (
    <section className={`intelligence panel sentiment-${tone}`} id="intelligence">
      <div className="intelligence-heading">
        <div className="intelligence-title">
          <p className="eyebrow">{t.eyebrow}</p>
          <h2>{t.title}</h2>
        </div>
        <div className="intelligence-state">
          <div className={`intelligence-status ${snapshot.status}`}>{statusText}</div>
          <small className={`intelligence-health ${healthTone}`}>{healthText}</small>
        </div>
      </div>

      <div className="intelligence-overview">
        <div className="sentiment-score">
          <strong>{snapshot.score.toFixed(1)}</strong>
          <span>/ 100</span>
          <em>{t.labels[snapshot.label]}</em>
          <small>
            {t.asOf} {date}
          </small>
        </div>
        <div className="sentiment-meter" aria-label={`${snapshot.score} / 100`}>
          <span className="meter-label fear">0</span>
          <i>
            <b style={{ left: `${snapshot.score}%` }} />
          </i>
          <span className="meter-label greed">100</span>
        </div>
        <div className="intelligence-kpis">
          <div>
            <span>{t.previous}</span>
            <strong className={(snapshot.change ?? 0) < 0 ? "negative" : "positive"}>
              {snapshot.change === null
                ? "-"
                : `${snapshot.change >= 0 ? "+" : ""}${snapshot.change.toFixed(1)}`}
            </strong>
          </div>
          <div>
            <span>{t.market}</span>
            <strong>{snapshot.market_score.toFixed(1)}</strong>
          </div>
          <div>
            <span>{t.news}</span>
            <strong>{snapshot.news_score.toFixed(1)}</strong>
          </div>
        </div>
      </div>

      <details className="intelligence-disclosure">
        <summary>{t.details}</summary>
        <div className="intelligence-detail">
          <div className="factor-list">
          <h3>{t.drivers}</h3>
          {snapshot.factors.map((factor) => (
            <a href={factor.source} key={factor.key} rel="noreferrer" target="_blank">
              <span>{t.factors[factor.key as keyof typeof t.factors] ?? factor.key}</span>
              <i><b style={{ width: `${factor.score}%` }} /></i>
              <strong>{factor.score.toFixed(0)}</strong>
            </a>
          ))}
          </div>
          <article className="daily-brief">
          <div>
            <span className="eyebrow">{t.brief}</span>
            <a
              href="https://github.com/yanzhang404/QuantOS/blob/main/docs/adr/0012-deterministic-daily-market-intelligence.md"
              rel="noreferrer"
              target="_blank"
            >
              {t.methodology}
            </a>
          </div>
          <p>{summary}</p>
          <ul>
            {highlights.map((highlight) => (
              <li key={highlight}>{highlight}</li>
            ))}
          </ul>
          <div className="news-links" aria-label={t.sources}>
            {snapshot.brief.news.map((item) => (
              <a href={item.url} key={item.id} rel="noreferrer" target="_blank">
                <span>{item.source}</span>
                {locale === "zh" ? item.title_zh ?? item.title : item.title}
              </a>
            ))}
          </div>
          </article>
        </div>
      </details>
    </section>
  );
}
