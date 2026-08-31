import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("server-renders the QuantOS research workspace", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>QuantOS \| Strategy Research Workspace<\/title>/i);
  assert.match(html, /Donchian ATR/);
  assert.match(html, /Research mode/);
  assert.match(html, /Live trading disabled/);
  assert.match(html, />Overview</);
  assert.match(html, />Strategies</);
  assert.match(html, />Runs</);
  assert.match(html, />Data</);
  assert.match(html, /Market &amp; research pulse/);
  assert.match(html, /Start with market context/);
  assert.match(html, /Total return/);
  assert.match(html, /Latest strategy evidence/);
  assert.match(html, /Candidate queue/);
  assert.match(html, /Dataset coverage/);
  assert.match(html, /Daily market intelligence/);
  assert.match(html, /Sample snapshot · not current market data/);
  assert.match(html, /Market score/);
  assert.match(html, /Source-linked news/);
  assert.match(html, /A-share Market Radar/);
  assert.match(html, /Sample snapshot · not current market data/);
  assert.match(html, /30m acceleration/);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton/i);
});

test("splits the workspace into four hash-addressable views", async () => {
  const source = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");

  assert.match(source, /type WorkspaceView = "overview" \| "strategies" \| "runs" \| "data"/);
  assert.match(source, /window\.addEventListener\("hashchange", syncView\)/);
  assert.match(source, /activeView === "overview"/);
  assert.match(source, /activeView === "strategies"/);
  assert.match(source, /activeView === "runs"/);
  assert.match(source, /activeView === "data"/);
  assert.doesNotMatch(source, /className="hero-grid"/);
  assert.doesNotMatch(source, /className="research-lifecycle panel"/);
});

test("connects daily intelligence to the validated API snapshot", async () => {
  const [component, api] = await Promise.all([
    readFile(new URL("../app/daily-intelligence.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/intelligence-api.ts", import.meta.url), "utf8"),
  ]);

  assert.match(component, /getLatestIntelligence\(controller\.signal\)/);
  assert.match(component, /getIntelligenceHealth\(controller\.signal\)/);
  assert.match(component, /刷新失败 · 已保留上一份快照/);
  assert.match(component, /health\.stale/);
  assert.match(component, /sampleSnapshot/);
  assert.match(component, /非当前市场数据/);
  assert.match(component, /factor\.source/);
  assert.match(component, /sentiment-\$\{tone\}/);
  assert.match(component, /className="sentiment-meter"/);
  assert.match(api, /\/api\/v1\/intelligence\/latest/);
  assert.match(api, /\/api\/v1\/intelligence\/health/);
});

test("connects Market Radar to deterministic snapshots and visible partial coverage", async () => {
  const [component, api] = await Promise.all([
    readFile(new URL("../app/market-radar.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/radar-api.ts", import.meta.url), "utf8"),
  ]);

  assert.match(component, /getLatestRadar\(controller\.signal\)/);
  assert.match(component, /getRadarHealth\(controller\.signal\)/);
  assert.match(component, /刷新失败 · 已保留上一份快照/);
  assert.match(component, /数据源未提供/);
  assert.match(component, /observed_breadth/);
  assert.match(component, /acceleration_30m/);
  assert.match(component, /sampleSnapshot/);
  assert.match(api, /\/api\/v1\/radar\/latest/);
  assert.match(api, /\/api\/v1\/radar\/health/);
});

test("ships an accessible Chinese and English language switch", async () => {
  const source = await readFile(
    new URL("../app/page.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /切换至中文/);
  assert.match(source, /Switch to English/);
  assert.match(source, /量化研究操作系统/);
  assert.match(source, /document\.documentElement\.lang/);
  assert.match(source, /aria-label=\{t\.switchLanguage\}/);
});

test("labels the Kline timeline and executed fills with dates", async () => {
  const source = await readFile(
    new URL("../app/strategy-workbench.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /dateTickIndexes/);
  assert.match(source, /formatAxisDate/);
  assert.match(source, /formatFullDate\(fill\.time/);
  assert.match(source, /activeFills/);
  assert.match(source, /performanceDateTickIndexes/);
  assert.match(source, /performance-tooltip/);
  assert.match(source, /xForTime/);
});

test("connects the parameter lab to durable backtest tasks", async () => {
  const [lab, api, workbench, catalog] = await Promise.all([
    readFile(new URL("../app/backtest-lab.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/backtest-api.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/strategy-workbench.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/strategy-catalog.ts", import.meta.url), "utf8"),
  ]);

  assert.match(lab, /submitBacktest\(request\)/);
  assert.match(lab, /getTask\(activeTask\.task_id/);
  assert.match(lab, /listTasks/);
  assert.match(api, /\/api\/v1\/backtests/);
  assert.match(api, /\/api\/v1\/tasks/);
  assert.match(api, /Idempotency-Key/);
  assert.match(api, /\/api\/v1\/experiments/);
  assert.match(lab, /getExperiment\(task\.run_id/);
  assert.match(lab, /onExperimentLoaded\(experiment\)/);
  assert.match(workbench, /selectedExperimentMatches/);
  assert.match(workbench, /const run: VisualizationRun = selectedExperimentMatches/);
  assert.match(workbench, /getBacktestDataset/);
  assert.match(workbench, /selectedExperiment\.bars/);
  assert.match(workbench, /setSelectedInterval\(interval\)/);
  assert.match(lab, /dataset\.bundle_version/);
  assert.match(workbench, /getStrategyCatalog/);
  assert.match(workbench, /mergeStrategyCatalog\(records\)/);
  assert.match(
    workbench,
    /className="result-summary"[\s\S]*className="strategy-library"/,
  );
  assert.match(catalog, /implementation: nonEmptyString\(candidate\.implementation\)/);
  assert.match(lab, /definition\.parameters\.map/);
  assert.match(lab, /className="advanced-settings"/);
  assert.match(lab, /className="task-result-row"/);
  assert.match(lab, /setExperiments/);
  assert.doesNotMatch(lab, /const parameters: Record/);
});

test("shows resolved feature lineage for a loaded Run", async () => {
  const [api, workbench, lab, catalog] = await Promise.all([
    readFile(new URL("../app/backtest-api.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/strategy-workbench.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/backtest-lab.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/strategy-catalog.ts", import.meta.url), "utf8"),
  ]);
  assert.match(api, /definition_sha256/);
  assert.match(api, /uses_current_closed_bar/);
  assert.match(workbench, /selectedExperiment\.features/);
  assert.match(workbench, /已解析特征/);
  assert.match(api, /feature_datasets/);
  assert.match(workbench, /selectedExperiment\.feature_datasets/);
  assert.match(workbench, /外部特征数据/);
  assert.match(catalog, /funding-filtered-ema/);
  assert.match(catalog, /asof-closed-bar\.v1/);
  assert.match(lab, /feature_dataset_version/);
  assert.match(lab, /\^\[0-9a-f\]\{16\}\$/);
  assert.match(api, /\/api\/v1\/feature-datasets/);
  assert.match(lab, /listCompatibleFeatureDatasets\(dataset/);
  assert.match(lab, /feature\.matched_count/);
});

test("manages immutable Runs with filters, archives, and four-way comparison", async () => {
  const [library, api, page] = await Promise.all([
    readFile(new URL("../app/run-library.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/backtest-api.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
  ]);

  assert.match(page, /<RunLibrary locale=\{locale\}/);
  assert.match(library, /listExperiments\(filters/);
  assert.match(library, /setExperimentArchived/);
  assert.match(library, /current\.length < 4/);
  assert.match(library, /selectedRuns\.length >= 2/);
  assert.match(library, /point\.equity \/ run\.metrics\.initial_equity - 1/);
  assert.match(library, /formatParameters\(run\.strategy\.parameters\)/);
  assert.match(api, /\/api\/v1\/experiment-archives/);
  assert.match(api, /archived\?: "exclude" \| "include" \| "only"/);
});

test("shows deterministic robustness promotion gates without automatic promotion", async () => {
  const [component, api, library] = await Promise.all([
    readFile(new URL("../app/robustness-evidence.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/robustness-api.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/run-library.tsx", import.meta.url), "utf8"),
  ]);

  assert.match(library, /<RobustnessEvidence locale=\{locale\}/);
  assert.match(api, /\/api\/v1\/robustness/);
  assert.match(component, /walk_forward/);
  assert.match(component, /neighboring_parameters/);
  assert.match(component, /doubled_costs/);
  assert.match(component, /multiple_markets/);
  assert.match(component, /Donchian\(/);
  assert.match(api, /robustness-review\.v2/);
  assert.match(component, /never promotes or trades automatically/);
});

test("connects the guarded candidate queue without adding browser mutation controls", async () => {
  const [component, api, page] = await Promise.all([
    readFile(new URL("../app/candidate-queue.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/candidate-api.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
  ]);

  assert.match(page, /<CandidateQueue locale=\{locale\}/);
  assert.match(component, /listCandidates\(controller\.signal\)/);
  assert.match(component, /listCandidateDrafts\(controller\.signal\)/);
  assert.match(component, /review_ready/);
  assert.match(component, /owner approval/);
  assert.match(api, /\/api\/v1\/candidates/);
  assert.match(api, /\/api\/v1\/candidate-drafts/);
  assert.doesNotMatch(component, /fetch\([^)]*method:\s*["'](?:POST|PUT|DELETE)/i);
});

test("renders verified BTC and ETH coverage from an immutable bundle", async () => {
  const [page, coverage] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(
      new URL("../app/multi-timeframe-coverage.v1.json", import.meta.url),
      "utf8",
    ),
  ]);

  const evidence = JSON.parse(coverage);
  assert.equal(evidence.schema_version, "dataset-coverage.v1");
  assert.equal(evidence.member_count, 10);
  assert.equal(evidence.requested_start, "2021-01-01T00:00:00Z");
  assert.equal(evidence.requested_end, "2026-08-31T00:00:00Z");
  assert.equal(evidence.total_row_count, 1715846);
  assert.equal(evidence.missing_interval_count, 594);
  assert.deepEqual(
    [...new Set(evidence.members.map((member) => member.interval))],
    ["5m", "15m", "1h", "4h", "1d"],
  );
  assert.deepEqual(
    [...new Set(evidence.members.map((member) => member.symbol))],
    ["BTCUSDT", "ETHUSDT"],
  );
  assert.match(page, /marketDataCoverage\.member_count/);
  assert.match(page, /marketDataCoverage\.total_row_count/);
  assert.match(page, /marketDataCoverage\.missing_interval_count/);
  assert.match(page, /getCoverageMember\("BTCUSDT", interval\)/);
  assert.doesNotMatch(page, /interval === "4h" \? t\.verified : "Pending"/);
});

test("shows the versioned feature registry in the Data view", async () => {
  const [page, registry] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/feature-registry.v1.json", import.meta.url), "utf8"),
  ]);
  assert.match(page, /featureRegistry\.features\.map/);
  assert.match(page, /派生特征也有独立版本/);
  assert.match(registry, /prior-high-channel/);
  assert.match(registry, /uses_current_closed_bar/);
});

test("uses a compact light workspace without the known heading overlap", async () => {
  const [styles, intelligence] = await Promise.all([
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
    readFile(new URL("../app/daily-intelligence.tsx", import.meta.url), "utf8"),
  ]);

  assert.match(styles, /--background: #f3f7f2/);
  assert.match(styles, /\.panel \{\s*padding: 18px;/);
  assert.match(styles, /@media \(max-width: 1180px\)/);
  assert.match(styles, /\.intelligence-title/);
  assert.doesNotMatch(
    styles,
    /\.intelligence-heading > div,\s*\.daily-brief > div:first-child/,
  );
  assert.match(intelligence, /className="intelligence-heading"/);
  assert.match(intelligence, /className="intelligence-title"/);
});
