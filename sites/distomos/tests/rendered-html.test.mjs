import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

async function render(path = "/") {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request(`http://localhost${path}`, { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the finished Distomos homepage", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);
  const html = await response.text();
  assert.match(html, /<title>Distomos — See the shape of what’s next<\/title>/i);
  assert.match(html, /See the shape/);
  assert.match(html, /THE CONTEXT WINDOW BY DISTOMOS/);
  const episode = JSON.parse(await readFile(new URL("../app/latest-episode.json", import.meta.url), "utf8"));
  assert.ok(html.includes(episode.title));
  assert.match(html, /https:\/\/contextwindow\.distomostech\.com/);
  assert.match(html, /https:\/\/open\.spotify\.com\/show\/033OoZlyZBlEwCd6kmNdpT/);
  assert.match(html, /https:\/\/www\.youtube\.com\/@TheContextWindow-q1z/);
  assert.match(html, /href="\/business"/);
  assert.match(html, /class="playback-icon"/);
  assert.doesNotMatch(html, /▶|Ⅱ/);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape|SoundHelix/i);
  assert.doesNotMatch(html, /<form|type="email"/i);
});

test("server-renders the business inquiries page", async () => {
  const response = await render("/business");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /Business inquiries — Distomos/);
  assert.match(html, /Good work starts/);
  assert.match(html, /mailto:james@distomostech\.com/);
  assert.match(html, /Partnerships/);
  assert.match(html, /Sponsorships/);
});

test("ships the required imagery and pipeline-owned episode data", async () => {
  const [page, latest, layout] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/latest-episode.json", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
  ]);
  const episode = JSON.parse(latest);
  assert.match(page, /from "\.\/latest-episode\.json"/);
  assert.match(episode.date, /^\d{4}-\d{2}-\d{2}$/);
  assert.match(episode.youtube_url, /^https:\/\/youtube\.com\/watch\?v=/);
  assert.match(layout, /metadataBase: new URL\("https:\/\/distomostech\.com"\)/);
  await access(new URL("../public/landsat-kevir.jpg", import.meta.url));
  await access(new URL("../public/og.png", import.meta.url));
});
