"use client";

import type { CSSProperties } from "react";
import { useEffect, useMemo, useState } from "react";
import {
  type Asset,
  getDataset,
  getRuns,
  getStressRun,
  type Period,
  studyAsOf,
} from "./research-data";

type Locale = "en" | "zh";

const copy = {
  en: {
    workspace: "Workspace",
    nav: ["Research", "Strategies", "Data lineage"],
    researchMode: "Research mode",
    liveDisabled: "Live trading disabled",
    strategyReview: "Strategy review / 001",
    evidenceAsOf: "Evidence as of",
    switchLanguage: "切换至中文",
    languageLabel: "中文",
    verdict: "Fixed evaluation verdict",
    drawdownControlled: "Drawdown controlled.",
    returnEdge: "Return edge",
    unproven: "unproven",
    modest: "modest",
    hero:
      "The strategy preserved substantially more capital than passive exposure. It remains a research candidate—not a production signal.",
    tags: ["Long only", "Next-open fills", "20% vol target"],
    filters: "Research filters",
    market: "Market",
    observation: "Observation window",
    periods: { evaluation: "evaluation", development: "development" },
    selectedMetrics: "Selected strategy metrics",
    totalReturn: "Total return",
    returnNote: "after 10 bps fee + 5 bps slippage",
    sharpe: "Sharpe ratio",
    sharpeNote: "annualized from 4h observations",
    maxDrawdown: "Maximum drawdown",
    belowPassive: "below passive",
    versusPassive: "versus passive benchmark",
    completedTrades: "Completed trades",
    totalFills: "total fills",
    outcomeMatrix: "Outcome matrix",
    sameMarket: "Same market. Same costs.",
    columns: ["Strategy", "Net return", "Sharpe", "Drawdown"],
    trades: "trades",
    strategies: {
      "buy-and-hold": "Buy & Hold",
      "ema-cross": "EMA 20 / 50",
      "donchian-atr": "Donchian ATR",
    },
    costSensitivity: "Cost sensitivity",
    frictionTest: "2× friction test",
    baseCosts: "Base costs",
    stressReturn: "return at 20 bps fee + 10 bps slippage",
    base: "Base",
    doubledCosts: "2× costs",
    btcStress:
      "BTC turns more negative under stress. Turnover remains the primary risk.",
    ethStress:
      "ETH remains positive under stress, but the margin is not large enough for a production claim.",
    feesDevelopment: "simulated fees paid in the development window",
    stressReserved:
      "Stress results are reserved for the fixed evaluation period to keep development and final evidence clearly separated.",
    researchReview: "Research review",
    evidenceSays: "What the evidence says",
    findingsCount: "03 findings",
    findings: [
      [
        "Risk-control hypothesis supported",
        "Drawdown and Sharpe behavior improved versus passive exposure on both evaluation assets.",
      ],
      [
        "No broad return claim",
        "BTC remained approximately flat before stress. Two assets and one interval are insufficient evidence.",
      ],
      [
        "Turnover needs work",
        "Dynamic volatility sizing adds fills and makes the result sensitive to execution friction.",
      ],
    ],
    evidenceTrail: "Evidence trail",
    reproducible: "Reproducible by design",
    verified: "Verified",
    dataset: "Dataset",
    bars: "Bars",
    strategyRun: "Strategy run",
    contentHash: "Content hash",
    provenance:
      "Binance Spot · UTC · closed Klines · immutable source identity",
    product: "QuantOS / Research operating system",
    disclaimer: "Historical simulation · Not investment advice",
  },
  zh: {
    workspace: "工作台",
    nav: ["研究", "策略", "数据血缘"],
    researchMode: "研究模式",
    liveDisabled: "实盘交易已禁用",
    strategyReview: "策略评审 / 001",
    evidenceAsOf: "证据更新至",
    switchLanguage: "Switch to English",
    languageLabel: "EN",
    verdict: "固定样本外评估结论",
    drawdownControlled: "回撤得到控制。",
    returnEdge: "收益优势",
    unproven: "尚未证实",
    modest: "较为有限",
    hero:
      "相比被动持有，该策略保留了更多资本。目前仍是研究候选，不是可直接使用的生产信号。",
    tags: ["仅做多", "下一根开盘成交", "20% 波动率目标"],
    filters: "研究筛选条件",
    market: "市场",
    observation: "观察区间",
    periods: { evaluation: "评估期", development: "开发期" },
    selectedMetrics: "所选策略指标",
    totalReturn: "总收益率",
    returnNote: "已计入 10 bps 手续费 + 5 bps 滑点",
    sharpe: "夏普比率",
    sharpeNote: "基于 4 小时数据年化",
    maxDrawdown: "最大回撤",
    belowPassive: "低于被动持有",
    versusPassive: "对比被动持有基准",
    completedTrades: "完成交易",
    totalFills: "次成交",
    outcomeMatrix: "结果矩阵",
    sameMarket: "同一市场，同一成本。",
    columns: ["策略", "净收益", "夏普", "回撤"],
    trades: "笔交易",
    strategies: {
      "buy-and-hold": "买入并持有",
      "ema-cross": "EMA 20 / 50",
      "donchian-atr": "唐奇安 ATR",
    },
    costSensitivity: "成本敏感度",
    frictionTest: "2 倍摩擦压力测试",
    baseCosts: "基础成本",
    stressReturn: "20 bps 手续费 + 10 bps 滑点下的收益",
    base: "基础成本",
    doubledCosts: "2 倍成本",
    btcStress: "BTC 在压力测试下亏损扩大，换手率仍是主要风险。",
    ethStress: "ETH 在压力测试下仍为正收益，但优势不足以支持生产级结论。",
    feesDevelopment: "开发期模拟支付的手续费",
    stressReserved:
      "压力测试只用于固定评估期，以清晰区分开发阶段与最终证据。",
    researchReview: "研究评审",
    evidenceSays: "证据说明了什么",
    findingsCount: "03 项发现",
    findings: [
      [
        "风险控制假设得到支持",
        "在两个评估资产上，回撤和夏普表现均优于被动持有。",
      ],
      [
        "不能声称普遍高收益",
        "BTC 在压力测试前接近持平；两个资产和一个周期不足以形成普遍结论。",
      ],
      [
        "换手率仍需优化",
        "动态波动率仓位增加了成交次数，使结果对交易摩擦更加敏感。",
      ],
    ],
    evidenceTrail: "证据链",
    reproducible: "可复现设计",
    verified: "已验证",
    dataset: "数据集",
    bars: "K 线",
    strategyRun: "策略运行",
    contentHash: "内容哈希",
    provenance: "Binance 现货 · UTC · 已收盘 K 线 · 不可变来源标识",
    product: "QuantOS / 量化研究操作系统",
    disclaimer: "历史模拟 · 不构成投资建议",
  },
} as const;

function metricTone(value: number): string {
  if (value > 0.001) return "positive";
  if (value < -0.001) return "negative";
  return "neutral";
}

export default function Home() {
  const [asset, setAsset] = useState<Asset>("btc");
  const [period, setPeriod] = useState<Period>("evaluation");
  const [locale, setLocale] = useState<Locale>("en");
  const t = copy[locale];
  const localeTag = locale === "zh" ? "zh-CN" : "en-US";
  const percent = useMemo(
    () =>
      new Intl.NumberFormat(localeTag, {
        style: "percent",
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }),
    [localeTag],
  );
  const number = useMemo(
    () =>
      new Intl.NumberFormat(localeTag, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }),
    [localeTag],
  );
  const currency = useMemo(
    () =>
      new Intl.NumberFormat(localeTag, {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 0,
      }),
    [localeTag],
  );

  useEffect(() => {
    document.documentElement.lang = locale === "zh" ? "zh-CN" : "en";
  }, [locale]);

  const runs = useMemo(() => getRuns(asset, period), [asset, period]);
  const donchian = runs.find((run) => run.strategy === "donchian-atr");
  const benchmark = runs.find((run) => run.strategy === "buy-and-hold");
  const stress = period === "evaluation" ? getStressRun(asset) : undefined;
  const dataset = getDataset(asset, period);
  const maxMagnitude = Math.max(
    ...runs.map((run) => Math.abs(run.total_return)),
    0.01,
  );
  const drawdownDelta =
    donchian && benchmark
      ? benchmark.max_drawdown - donchian.max_drawdown
      : undefined;

  return (
    <main className="workspace">
      <aside className="rail">
        <div className="brand" aria-label="QuantOS">
          <span className="brand-mark">Q</span>
          <span>QuantOS</span>
        </div>
        <nav aria-label={t.workspace}>
          <a className="nav-item active" href="#research">
            <span>01</span> {t.nav[0]}
          </a>
          <a className="nav-item" href="#strategies">
            <span>02</span> {t.nav[1]}
          </a>
          <a className="nav-item" href="#provenance">
            <span>03</span> {t.nav[2]}
          </a>
        </nav>
        <div className="rail-status">
          <span className="status-dot" />
          <div>
            <strong>{t.researchMode}</strong>
            <span>{t.liveDisabled}</span>
          </div>
        </div>
      </aside>

      <section className="content" id="research">
        <header className="topbar">
          <div>
            <p className="eyebrow">{t.strategyReview}</p>
            <h1>Donchian ATR</h1>
          </div>
          <div className="header-actions">
            <div className="as-of">
              <span>{t.evidenceAsOf}</span>
              <strong>{studyAsOf}</strong>
            </div>
            <button
              aria-label={t.switchLanguage}
              className="language-switch"
              onClick={() => setLocale(locale === "en" ? "zh" : "en")}
              type="button"
            >
              <span aria-hidden="true">文/A</span>
              {t.languageLabel}
            </button>
          </div>
        </header>

        <section className="hero-grid">
          <article className="verdict-card">
            <div className="card-label">
              <span className="pulse" />
              {t.verdict}
            </div>
            <h2>
              {t.drawdownControlled}
              <br />
              {t.returnEdge}{" "}
              <em>{asset === "btc" ? t.unproven : t.modest}.</em>
            </h2>
            <p>{t.hero}</p>
            <div className="verdict-meta">
              {t.tags.map((tag) => (
                <span key={tag}>{tag}</span>
              ))}
            </div>
          </article>

          <article className="control-card" aria-label={t.filters}>
            <div className="control-group">
              <span className="control-label">{t.market}</span>
              <div className="segment">
                {(["btc", "eth"] as const).map((value) => (
                  <button
                    aria-pressed={asset === value}
                    className={asset === value ? "selected" : ""}
                    key={value}
                    onClick={() => setAsset(value)}
                    type="button"
                  >
                    {value.toUpperCase()}
                    <small>USDT</small>
                  </button>
                ))}
              </div>
            </div>
            <div className="control-group">
              <span className="control-label">{t.observation}</span>
              <div className="segment">
                {(["evaluation", "development"] as const).map((value) => (
                  <button
                    aria-pressed={period === value}
                    className={period === value ? "selected" : ""}
                    key={value}
                    onClick={() => setPeriod(value)}
                    type="button"
                  >
                    {value === "evaluation" ? "2025—26" : "2022—24"}
                    <small>{t.periods[value]}</small>
                  </button>
                ))}
              </div>
            </div>
          </article>
        </section>

        <section className="metric-strip" aria-label={t.selectedMetrics}>
          <div>
            <span>{t.totalReturn}</span>
            <strong className={metricTone(donchian?.total_return ?? 0)}>
              {percent.format(donchian?.total_return ?? 0)}
            </strong>
            <small>{t.returnNote}</small>
          </div>
          <div>
            <span>{t.sharpe}</span>
            <strong>{number.format(donchian?.sharpe_ratio ?? 0)}</strong>
            <small>{t.sharpeNote}</small>
          </div>
          <div>
            <span>{t.maxDrawdown}</span>
            <strong>{percent.format(donchian?.max_drawdown ?? 0)}</strong>
            <small>
              {drawdownDelta
                ? `${percent.format(drawdownDelta)} ${t.belowPassive}`
                : t.versusPassive}
            </small>
          </div>
          <div>
            <span>{t.completedTrades}</span>
            <strong>{donchian?.trade_count ?? 0}</strong>
            <small>
              {donchian?.fill_count ?? 0} {t.totalFills}
            </small>
          </div>
        </section>

        <section className="analysis-grid">
          <article className="panel comparison" id="strategies">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">{t.outcomeMatrix}</p>
                <h3>{t.sameMarket}</h3>
              </div>
              <span className="badge">{t.periods[period]}</span>
            </div>

            <div className="comparison-head" aria-hidden="true">
              {t.columns.map((column) => (
                <span key={column}>{column}</span>
              ))}
            </div>
            {runs.map((run) => {
              const barStyle = {
                "--bar-width": `${Math.max(
                  4,
                  (Math.abs(run.total_return) / maxMagnitude) * 100,
                )}%`,
              } as CSSProperties;
              return (
                <div
                  className={`strategy-row ${
                    run.strategy === "donchian-atr" ? "featured" : ""
                  }`}
                  key={run.run_id}
                >
                  <div className="strategy-name">
                    <span>{t.strategies[run.strategy]}</span>
                    <small>
                      {run.trade_count} {t.trades}
                    </small>
                  </div>
                  <div className="return-cell">
                    <span className={metricTone(run.total_return)}>
                      {percent.format(run.total_return)}
                    </span>
                    <div
                      className={`return-bar ${metricTone(run.total_return)}`}
                      style={barStyle}
                    />
                  </div>
                  <span>{number.format(run.sharpe_ratio)}</span>
                  <span>{percent.format(run.max_drawdown)}</span>
                </div>
              );
            })}
          </article>

          <article className="panel stress-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">{t.costSensitivity}</p>
                <h3>
                  {period === "evaluation" ? t.frictionTest : t.baseCosts}
                </h3>
              </div>
              <span className={stress ? "badge warning" : "badge"}>ATR 55 / 20</span>
            </div>
            {stress && donchian ? (
              <>
                <div className="stress-number">
                  <span className={metricTone(stress.total_return)}>
                    {percent.format(stress.total_return)}
                  </span>
                  <small>{t.stressReturn}</small>
                </div>
                <div className="stress-scale">
                  <div>
                    <span>{t.base}</span>
                    <strong>{percent.format(donchian.total_return)}</strong>
                  </div>
                  <div>
                    <span>{t.doubledCosts}</span>
                    <strong>{percent.format(stress.total_return)}</strong>
                  </div>
                </div>
                <p className="panel-note">
                  {asset === "btc" ? t.btcStress : t.ethStress}
                </p>
              </>
            ) : (
              <>
                <div className="stress-number">
                  <span>{currency.format(donchian?.fees_paid ?? 0)}</span>
                  <small>{t.feesDevelopment}</small>
                </div>
                <p className="panel-note">{t.stressReserved}</p>
              </>
            )}
          </article>
        </section>

        <section className="lower-grid">
          <article className="panel review-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">{t.researchReview}</p>
                <h3>{t.evidenceSays}</h3>
              </div>
              <span className="review-count">{t.findingsCount}</span>
            </div>
            <ul className="findings">
              {t.findings.map(([title, detail], index) => (
                <li key={title}>
                  <span
                    className={`finding-index ${index > 0 ? "caution" : ""}`}
                  >
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <div>
                    <strong>{title}</strong>
                    <p>{detail}</p>
                  </div>
                </li>
              ))}
            </ul>
          </article>

          <article className="panel provenance" id="provenance">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">{t.evidenceTrail}</p>
                <h3>{t.reproducible}</h3>
              </div>
              <span className="verified">{t.verified}</span>
            </div>
            <dl>
              <div>
                <dt>{t.dataset}</dt>
                <dd>{dataset.dataset_version}</dd>
              </div>
              <div>
                <dt>{t.bars}</dt>
                <dd>{dataset.rows.toLocaleString(localeTag)} × 4h</dd>
              </div>
              <div>
                <dt>{t.strategyRun}</dt>
                <dd>{donchian?.run_id}</dd>
              </div>
              <div>
                <dt>{t.contentHash}</dt>
                <dd>{dataset.content_sha256.slice(0, 20)}…</dd>
              </div>
            </dl>
            <p className="provenance-note">{t.provenance}</p>
          </article>
        </section>

        <footer>
          <span>{t.product}</span>
          <span>{t.disclaimer}</span>
        </footer>
      </section>
    </main>
  );
}
