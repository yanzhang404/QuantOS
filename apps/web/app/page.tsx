"use client";

import type { CSSProperties } from "react";
import { useMemo, useState } from "react";
import {
  type Asset,
  getDataset,
  getRuns,
  getStressRun,
  type Period,
  strategyNames,
  studyAsOf,
} from "./research-data";

const percent = new Intl.NumberFormat("en-US", {
  style: "percent",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const number = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

function metricTone(value: number): string {
  if (value > 0.001) return "positive";
  if (value < -0.001) return "negative";
  return "neutral";
}

export default function Home() {
  const [asset, setAsset] = useState<Asset>("btc");
  const [period, setPeriod] = useState<Period>("evaluation");

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
        <nav aria-label="Workspace">
          <a className="nav-item active" href="#research">
            <span>01</span> Research
          </a>
          <a className="nav-item" href="#strategies">
            <span>02</span> Strategies
          </a>
          <a className="nav-item" href="#provenance">
            <span>03</span> Data lineage
          </a>
        </nav>
        <div className="rail-status">
          <span className="status-dot" />
          <div>
            <strong>Research mode</strong>
            <span>Live trading disabled</span>
          </div>
        </div>
      </aside>

      <section className="content" id="research">
        <header className="topbar">
          <div>
            <p className="eyebrow">Strategy review / 001</p>
            <h1>Donchian ATR</h1>
          </div>
          <div className="as-of">
            <span>Evidence as of</span>
            <strong>{studyAsOf}</strong>
          </div>
        </header>

        <section className="hero-grid">
          <article className="verdict-card">
            <div className="card-label">
              <span className="pulse" />
              Fixed evaluation verdict
            </div>
            <h2>
              Drawdown controlled.
              <br />
              Return edge <em>{asset === "btc" ? "unproven" : "modest"}.</em>
            </h2>
            <p>
              The strategy preserved substantially more capital than passive
              exposure. It remains a research candidate—not a production signal.
            </p>
            <div className="verdict-meta">
              <span>Long only</span>
              <span>Next-open fills</span>
              <span>20% vol target</span>
            </div>
          </article>

          <article className="control-card" aria-label="Research filters">
            <div className="control-group">
              <span className="control-label">Market</span>
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
              <span className="control-label">Observation window</span>
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
                    <small>{value}</small>
                  </button>
                ))}
              </div>
            </div>
          </article>
        </section>

        <section className="metric-strip" aria-label="Selected strategy metrics">
          <div>
            <span>Total return</span>
            <strong className={metricTone(donchian?.total_return ?? 0)}>
              {percent.format(donchian?.total_return ?? 0)}
            </strong>
            <small>after 10 bps fee + 5 bps slippage</small>
          </div>
          <div>
            <span>Sharpe ratio</span>
            <strong>{number.format(donchian?.sharpe_ratio ?? 0)}</strong>
            <small>annualized from 4h observations</small>
          </div>
          <div>
            <span>Maximum drawdown</span>
            <strong>{percent.format(donchian?.max_drawdown ?? 0)}</strong>
            <small>
              {drawdownDelta
                ? `${percent.format(drawdownDelta)} below passive`
                : "versus passive benchmark"}
            </small>
          </div>
          <div>
            <span>Completed trades</span>
            <strong>{donchian?.trade_count ?? 0}</strong>
            <small>{donchian?.fill_count ?? 0} total fills</small>
          </div>
        </section>

        <section className="analysis-grid">
          <article className="panel comparison" id="strategies">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Outcome matrix</p>
                <h3>Same market. Same costs.</h3>
              </div>
              <span className="badge">{period}</span>
            </div>

            <div className="comparison-head" aria-hidden="true">
              <span>Strategy</span>
              <span>Net return</span>
              <span>Sharpe</span>
              <span>Drawdown</span>
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
                    <span>{strategyNames[run.strategy]}</span>
                    <small>{run.trade_count} trades</small>
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
                <p className="eyebrow">Cost sensitivity</p>
                <h3>{period === "evaluation" ? "2× friction test" : "Base costs"}</h3>
              </div>
              <span className={stress ? "badge warning" : "badge"}>ATR 55 / 20</span>
            </div>
            {stress && donchian ? (
              <>
                <div className="stress-number">
                  <span className={metricTone(stress.total_return)}>
                    {percent.format(stress.total_return)}
                  </span>
                  <small>return at 20 bps fee + 10 bps slippage</small>
                </div>
                <div className="stress-scale">
                  <div>
                    <span>Base</span>
                    <strong>{percent.format(donchian.total_return)}</strong>
                  </div>
                  <div>
                    <span>2× costs</span>
                    <strong>{percent.format(stress.total_return)}</strong>
                  </div>
                </div>
                <p className="panel-note">
                  {asset === "btc"
                    ? "BTC turns more negative under stress. Turnover remains the primary risk."
                    : "ETH remains positive under stress, but the margin is not large enough for a production claim."}
                </p>
              </>
            ) : (
              <>
                <div className="stress-number">
                  <span>{currency.format(donchian?.fees_paid ?? 0)}</span>
                  <small>simulated fees paid in the development window</small>
                </div>
                <p className="panel-note">
                  Stress results are reserved for the fixed evaluation period to
                  keep development and final evidence clearly separated.
                </p>
              </>
            )}
          </article>
        </section>

        <section className="lower-grid">
          <article className="panel review-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Research review</p>
                <h3>What the evidence says</h3>
              </div>
              <span className="review-count">03 findings</span>
            </div>
            <ul className="findings">
              <li>
                <span className="finding-index">01</span>
                <div>
                  <strong>Risk-control hypothesis supported</strong>
                  <p>
                    Drawdown and Sharpe behavior improved versus passive exposure
                    on both evaluation assets.
                  </p>
                </div>
              </li>
              <li>
                <span className="finding-index caution">02</span>
                <div>
                  <strong>No broad return claim</strong>
                  <p>
                    BTC remained approximately flat before stress. Two assets and
                    one interval are insufficient evidence.
                  </p>
                </div>
              </li>
              <li>
                <span className="finding-index caution">03</span>
                <div>
                  <strong>Turnover needs work</strong>
                  <p>
                    Dynamic volatility sizing adds fills and makes the result
                    sensitive to execution friction.
                  </p>
                </div>
              </li>
            </ul>
          </article>

          <article className="panel provenance" id="provenance">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Evidence trail</p>
                <h3>Reproducible by design</h3>
              </div>
              <span className="verified">Verified</span>
            </div>
            <dl>
              <div>
                <dt>Dataset</dt>
                <dd>{dataset.dataset_version}</dd>
              </div>
              <div>
                <dt>Bars</dt>
                <dd>{dataset.rows.toLocaleString()} × 4h</dd>
              </div>
              <div>
                <dt>Strategy run</dt>
                <dd>{donchian?.run_id}</dd>
              </div>
              <div>
                <dt>Content hash</dt>
                <dd>{dataset.content_sha256.slice(0, 20)}…</dd>
              </div>
            </dl>
            <p className="provenance-note">
              Binance Spot · UTC · closed Klines · immutable source identity
            </p>
          </article>
        </section>

        <footer>
          <span>QuantOS / Research operating system</span>
          <span>Historical simulation · Not investment advice</span>
        </footer>
      </section>
    </main>
  );
}
