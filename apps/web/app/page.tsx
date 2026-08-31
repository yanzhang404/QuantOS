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
import { DailyIntelligence } from "./daily-intelligence";
import { MarketRadar } from "./market-radar";
import {
  coverageIntervals,
  getCoverageMember,
  marketDataCoverage,
} from "./market-data-coverage";
import { StrategyWorkbench } from "./strategy-workbench";
import { RunLibrary } from "./run-library";
import { CandidateQueue } from "./candidate-queue";
import featureRegistry from "./feature-registry.v1.json";

type Locale = "en" | "zh";
type WorkspaceView = "overview" | "strategies" | "runs" | "data";

const workspaceViews: WorkspaceView[] = ["overview", "strategies", "runs", "data"];

const copy = {
  en: {
    workspace: "Workspace",
    nav: ["Overview", "Strategies", "Runs", "Data"],
    viewEyebrows: {
      overview: "Market & research pulse",
      strategies: "Strategy workspace",
      runs: "Immutable experiment evidence",
      data: "Datasets & lineage",
    },
    viewTitles: {
      overview: "Overview",
      strategies: "Strategies",
      runs: "Runs & comparison",
      data: "Data & reproducibility",
    },
    overviewIntro:
      "Start with market context and the latest reproducible evidence. Sentiment is context, not a trading signal.",
    latestEvidence: "Latest strategy evidence",
    openStrategy: "Open strategy workspace",
    candidateQueue: "Candidate queue",
    candidateNote: "Agent proposals require tests, robustness review, and owner approval.",
    datasetHealth: "Dataset coverage",
    datasetNote:
      "BTC/ETH 5m-1d are verified through the latest complete UTC day. Source maintenance gaps remain visible and are never filled with synthetic bars.",
    coverageWindow: "Verified coverage window",
    bundle: "Dataset bundle",
    barsUnit: "bars",
    totalBars: "Total verified bars",
    sourceGaps: "Source gaps",
    currentThrough: "Current through",
    runsIntro:
      "Every result stays attributable to its dataset, parameters, costs, and Run ID.",
    committedReview: "Open the original committed research review",
    dataIntro:
      "Inspect exactly which immutable market data supports the displayed evidence.",
    featureRegistry: "Feature registry",
    featureRegistryTitle: "Derived inputs are versioned, too.",
    includesCurrent: "current closed bar included",
    priorOnly: "prior closed bars only",
    inputColumns: "inputs",
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
      "The strategy preserved substantially more capital than passive exposure. It remains a research candidate, not a production signal.",
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
      "funding-filtered-ema": "Funding-filtered EMA",
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
    lineageExplanation:
      "This lineage links the displayed result to its exact dataset, strategy code, parameters, costs, engine version, and Run ID.",
    product: "QuantOS / Research operating system",
    disclaimer: "Historical simulation · Not investment advice",
    discovery: "AI-assisted strategy discovery",
    discoveryTitle: "Research turns hypotheses into reviewable candidates.",
    discoveryIntro:
      "Research is the evidence process. Strategies are reusable code modules that enter the library only with explicit parameters, tests, and reproducible Runs.",
    lifecycle: [
      ["01 Hypothesis", "Volatility-sized channel breakout may reduce passive drawdown."],
      ["02 Candidate", "Donchian ATR code, parameter manifest, and deterministic tests registered."],
      ["03 Robustness review", "BTC/ETH · 4h · chronological split · doubled-cost stress."],
      ["04 Promotion", "More intervals and evidence required; owner approval remains mandatory."],
    ],
  },
  zh: {
    workspace: "工作台",
    nav: ["总览", "策略", "运行记录", "数据"],
    viewEyebrows: {
      overview: "市场与研究脉搏",
      strategies: "策略工作区",
      runs: "不可变实验记录",
      data: "数据集与溯源",
    },
    viewTitles: {
      overview: "总览",
      strategies: "策略",
      runs: "运行记录与对比",
      data: "数据与可复现性",
    },
    overviewIntro:
      "先看市场环境，再查看最新的可复现实验。情绪只提供背景，不是交易信号。",
    latestEvidence: "最新策略证据",
    openStrategy: "打开策略工作区",
    candidateQueue: "候选策略队列",
    candidateNote: "Agent 提案必须通过测试、稳健性评审和所有者批准。",
    datasetHealth: "数据覆盖",
    datasetNote:
      "BTC/ETH 的 5 分钟至日线数据已验证至最近完整 UTC 日；交易所维护造成的历史缺口会如实展示，不使用合成 K 线填补。",
    coverageWindow: "已验证覆盖区间",
    bundle: "数据集 Bundle",
    barsUnit: "根 K 线",
    totalBars: "已验证 K 线总数",
    sourceGaps: "数据源缺口",
    currentThrough: "最新数据截至",
    runsIntro: "每个结果都关联到确切的数据集、参数、成本和 Run ID。",
    committedReview: "展开原始研究评审",
    dataIntro: "查看当前证据究竟使用了哪些不可变市场数据。",
    featureRegistry: "特征注册表",
    featureRegistryTitle: "派生特征也有独立版本。",
    includesCurrent: "包含当前已收盘 K 线",
    priorOnly: "仅使用此前已收盘 K 线",
    inputColumns: "输入列",
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
      "funding-filtered-ema": "资金费率过滤 EMA",
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
    lineageExplanation:
      "溯源信息把当前结果关联到确切的数据集、策略代码、参数、成本、引擎版本和 Run ID。",
    product: "QuantOS / 量化研究操作系统",
    disclaimer: "历史模拟 · 不构成投资建议",
    discovery: "AI 辅助策略发现",
    discoveryTitle: "研究把假设转化为可评审的候选策略。",
    discoveryIntro:
      "研究是验证证据的过程；策略是可复用的独立代码模块。只有明确参数、测试和可复现 Run 后，策略才进入策略库。",
    lifecycle: [
      ["01 假设", "波动率仓位控制的通道突破可能降低被动持有回撤。"],
      ["02 候选策略", "已登记 Donchian ATR 代码、参数清单与确定性测试。"],
      ["03 稳健性评审", "BTC/ETH · 4小时 · 时间序列切分 · 双倍成本压力测试。"],
      ["04 晋级", "仍需更多周期和证据，并且必须由项目所有者批准。"],
    ],
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
  const [activeView, setActiveView] = useState<WorkspaceView>("overview");
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

  useEffect(() => {
    const syncView = () => {
      const candidate = window.location.hash.slice(1) as WorkspaceView;
      setActiveView(workspaceViews.includes(candidate) ? candidate : "overview");
    };
    syncView();
    window.addEventListener("hashchange", syncView);
    return () => window.removeEventListener("hashchange", syncView);
  }, []);

  const runs = useMemo(() => getRuns(asset, period), [asset, period]);
  const donchian = runs.find((run) => run.strategy === "donchian-atr");
  const stress = period === "evaluation" ? getStressRun(asset) : undefined;
  const dataset = getDataset(asset, period);
  const maxMagnitude = Math.max(
    ...runs.map((run) => Math.abs(run.total_return)),
    0.01,
  );
  return (
    <main className="workspace">
      <header className="app-header">
        <div className="brand" aria-label="QuantOS">
          <span className="brand-mark">Q</span>
          <span>QuantOS</span>
        </div>
        <nav aria-label={t.workspace}>
          {workspaceViews.map((view, index) => (
            <a
              aria-current={activeView === view ? "page" : undefined}
              className={`nav-item ${activeView === view ? "active" : ""}`}
              href={`#${view}`}
              key={view}
            >
              {t.nav[index]}
            </a>
          ))}
        </nav>
        <div className="app-header-actions">
          <div className="rail-status">
            <span className="status-dot" />
            <div>
              <strong>{t.researchMode}</strong>
              <span>{t.liveDisabled}</span>
            </div>
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

      <section className="content" id={activeView}>
        <header className="topbar">
          <div>
            <p className="eyebrow">{t.viewEyebrows[activeView]}</p>
            <h1>{t.viewTitles[activeView]}</h1>
          </div>
          <div className="header-actions">
            <div className="as-of">
              <span>{t.evidenceAsOf}</span>
              <strong>{studyAsOf}</strong>
            </div>
          </div>
        </header>

        {activeView === "overview" ? (
          <>
            <p className="view-intro">{t.overviewIntro}</p>
            <DailyIntelligence locale={locale} />
            <MarketRadar locale={locale} />
            <section className="overview-grid">
              <article className="panel overview-evidence">
                <div>
                  <p className="eyebrow">{t.latestEvidence}</p>
                  <h2>Donchian ATR</h2>
                  <span>BTC / USDT · 4h · {t.periods[period]}</span>
                </div>
                <dl>
                  <div>
                    <dt>{t.totalReturn}</dt>
                    <dd className={metricTone(donchian?.total_return ?? 0)}>
                      {percent.format(donchian?.total_return ?? 0)}
                    </dd>
                  </div>
                  <div>
                    <dt>{t.sharpe}</dt>
                    <dd>{number.format(donchian?.sharpe_ratio ?? 0)}</dd>
                  </div>
                  <div>
                    <dt>{t.maxDrawdown}</dt>
                    <dd>{percent.format(donchian?.max_drawdown ?? 0)}</dd>
                  </div>
                </dl>
                <a className="text-action" href="#strategies">
                  {t.openStrategy} →
                </a>
              </article>
              <CandidateQueue locale={locale} />
              <article className="panel overview-status-card">
                <p className="eyebrow">{t.datasetHealth}</p>
                <strong>{marketDataCoverage.total_row_count.toLocaleString(localeTag)}</strong>
                <span>
                  {t.currentThrough} {marketDataCoverage.requested_end.slice(0, 10)} UTC
                </span>
                <p>{t.datasetNote}</p>
              </article>
            </section>
          </>
        ) : null}

        {activeView === "strategies" ? (
          <StrategyWorkbench
            asset={asset}
            locale={locale}
            onAssetChange={setAsset}
            onPeriodChange={setPeriod}
            period={period}
          />
        ) : null}

        {activeView === "runs" ? (
          <>
            <p className="view-intro">{t.runsIntro}</p>
            <RunLibrary locale={locale} />
            <details className="committed-review">
              <summary>{t.committedReview}</summary>
            <div className="view-filters" aria-label={t.filters}>
              {(["btc", "eth"] as const).map((value) => (
                <button
                  aria-pressed={asset === value}
                  className={asset === value ? "selected" : ""}
                  key={value}
                  onClick={() => setAsset(value)}
                  type="button"
                >
                  {value.toUpperCase()} / USDT
                </button>
              ))}
              {(["evaluation", "development"] as const).map((value) => (
                <button
                  aria-pressed={period === value}
                  className={period === value ? "selected" : ""}
                  key={value}
                  onClick={() => setPeriod(value)}
                  type="button"
                >
                  {t.periods[value]}
                </button>
              ))}
            </div>
            <section className="analysis-grid" id="comparison">
          <article className="panel comparison">
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
            <section className="lower-grid runs-review">
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

            </section>
            </details>
          </>
        ) : null}

        {activeView === "data" ? (
          <>
            <p className="view-intro">{t.dataIntro}</p>
            <section className="data-layout">
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
            <p className="provenance-explanation">{t.lineageExplanation}</p>
            <p className="provenance-note">{t.provenance}</p>
              </article>
              <article className="panel interval-coverage">
                <div className="panel-heading">
                  <div>
                    <p className="eyebrow">{t.datasetHealth}</p>
                    <h3>BTC / ETH</h3>
                  </div>
                  <span className="verified">{marketDataCoverage.member_count} / 10</span>
                </div>
                <div className="coverage-table">
                  <div className="coverage-header" aria-hidden="true">
                    <strong>UTC</strong>
                    <span>BTC</span>
                    <span>ETH</span>
                  </div>
                  {coverageIntervals.map((interval) => {
                    const btc = getCoverageMember("BTCUSDT", interval);
                    const eth = getCoverageMember("ETHUSDT", interval);
                    return (
                      <div key={interval}>
                        <strong>{interval}</strong>
                        <span className="loaded" title={btc.dataset_version}>
                          {btc.row_count.toLocaleString(localeTag)} {t.barsUnit}
                        </span>
                        <span className="loaded" title={eth.dataset_version}>
                          {eth.row_count.toLocaleString(localeTag)} {t.barsUnit}
                        </span>
                      </div>
                    );
                  })}
                </div>
                <dl className="coverage-meta">
                  <div>
                    <dt>{t.coverageWindow}</dt>
                    <dd>
                      {marketDataCoverage.requested_start.slice(0, 10)} →{" "}
                      {marketDataCoverage.requested_end.slice(0, 10)}
                    </dd>
                  </div>
                  <div>
                    <dt>{t.bundle}</dt>
                    <dd>{marketDataCoverage.bundle_version}</dd>
                  </div>
                  <div>
                    <dt>{t.totalBars}</dt>
                    <dd>{marketDataCoverage.total_row_count.toLocaleString(localeTag)}</dd>
                  </div>
                  <div>
                    <dt>{t.sourceGaps}</dt>
                    <dd>{marketDataCoverage.missing_interval_count.toLocaleString(localeTag)}</dd>
                  </div>
                </dl>
                <p>{t.datasetNote}</p>
              </article>
              <article className="panel feature-registry">
                <div className="panel-heading">
                  <div>
                    <p className="eyebrow">{t.featureRegistry}</p>
                    <h3>{t.featureRegistryTitle}</h3>
                  </div>
                  <span className="verified">{featureRegistry.schema_version}</span>
                </div>
                <div className="feature-grid">
                  {featureRegistry.features.map((feature) => (
                    <div key={feature.feature_id}>
                      <header>
                        <strong>{feature.feature_id}</strong>
                        <code>v{feature.version}</code>
                      </header>
                      <p>{feature.description}</p>
                      <span>
                        {t.inputColumns}: {feature.inputs.join(" · ")}
                      </span>
                      <small>
                        {feature.uses_current_closed_bar ? t.includesCurrent : t.priorOnly}
                      </small>
                      <code>{feature.definition_sha256.slice(0, 12)}…</code>
                    </div>
                  ))}
                </div>
              </article>
            </section>
          </>
        ) : null}

        <footer>
          <span>{t.product}</span>
          <span>{t.disclaimer}</span>
        </footer>
      </section>
    </main>
  );
}
