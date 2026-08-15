import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the verified SentinelSRE portfolio", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);
  const html = await response.text();
  assert.match(html, /Reliability engineering, with receipts/);
  assert.match(html, /12 \/ 12 showcase gates passed/);
  assert.match(html, /AWS EKS/);
  assert.match(html, /Azure AKS/);
  assert.match(html, /2\.443s/);
  assert.match(html, /No production users/);
  assert.match(html, /live cloud telemetry adapters remain future work/i);
  assert.doesNotMatch(html, /All systems connected|13 services|production deployment/i);
});

test("portfolio source preserves governance and responsive behavior", async () => {
  const [page, layout, css] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
  ]);
  assert.match(page, /Alex Observer/);
  assert.match(page, /Former Engineer/);
  assert.match(page, /canApprove: false/);
  assert.match(page, /ACT-C2E54DAF61EB/);
  assert.match(page, /plan-tested without creating paid resources/);
  assert.match(layout, /SentinelSRE — Reliability engineering, with receipts/);
  assert.match(layout, /openGraph/);
  assert.match(css, /@media\(max-width:560px\)/);
  assert.match(css, /capabilityGrid/);
});
