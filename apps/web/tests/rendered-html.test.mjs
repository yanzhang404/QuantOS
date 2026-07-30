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
  assert.match(html, /<title>QuantOS — Strategy Research Workspace<\/title>/i);
  assert.match(html, /Donchian ATR/);
  assert.match(html, /Drawdown controlled/);
  assert.match(html, /Research mode/);
  assert.match(html, /Live trading disabled/);
  assert.match(html, /Price, decisions, and risk/);
  assert.match(html, /Kline \+ executed fills/);
  assert.match(html, /Portfolio equity/);
  assert.match(html, /Underwater drawdown/);
  assert.match(html, /Edit parameters and save a reproducible run/);
  assert.match(html, /Run backtest/);
  assert.match(html, /Backtest history/);
  assert.match(html, /Research center/);
  assert.match(html, /Strategy library/);
  assert.match(html, /Final capital/);
  assert.match(html, /AI-assisted strategy discovery/);
  assert.match(html, />5m</);
  assert.match(html, />1d</);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton/i);
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
});

test("connects the parameter lab to durable backtest tasks", async () => {
  const [lab, api, workbench] = await Promise.all([
    readFile(new URL("../app/backtest-lab.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/backtest-api.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/strategy-workbench.tsx", import.meta.url), "utf8"),
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
  assert.match(workbench, /getStrategyCatalog/);
  assert.match(lab, /definition\.parameters\.map/);
  assert.doesNotMatch(lab, /const parameters: Record/);
});
