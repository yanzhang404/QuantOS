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
