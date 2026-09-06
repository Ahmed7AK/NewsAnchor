/**
 * Browser smoke test: renders the running app and asserts the things that are
 * easy to break and invisible to unit tests.
 *
 * Prereqs -- backend and frontend both running:
 *   newsanchor serve                       # :8000
 *   npm run dev                            # :5173
 *   node scripts/smoke.mjs
 *
 * Override the URL with SMOKE_URL. Writes screenshots to ./smoke-out.
 *
 * The specific check worth having here: every position claimed in a story's
 * coverage list must be backed by that story's histogram. An earlier bug
 * grouped coverage by the outlet that *reprinted* a wire story rather than the
 * newsroom that reported it, so one AP dispatch appeared under both
 * "lean-left" and "right" and the card contradicted its own bar chart. Unit
 * tests now cover the API side; this catches it end to end.
 */
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";

const URL = process.env.SMOKE_URL ?? "http://127.0.0.1:5173/";
const OUT = "smoke-out";
mkdirSync(OUT, { recursive: true });

const problems = [];
const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH ?? undefined,
});
const page = await browser.newPage({ viewport: { width: 1000, height: 1400 } });

page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
page.on("console", (m) => {
  if (m.type() === "error") problems.push(`console: ${m.text()}`);
});
page.on("response", (r) => {
  if (r.status() >= 400) problems.push(`http ${r.status()}: ${r.url()}`);
});

await page.goto(URL, { waitUntil: "networkidle" });
await page.waitForSelector(".story", { timeout: 15000 });

const stories = await page.$$eval(".story", (els) =>
  els.map((e) => ({
    headline: e.querySelector("h2")?.textContent ?? "",
    cells: [...e.querySelectorAll(".spectrum .cell")].map((c) => c.textContent?.trim()),
    badges: [...e.querySelectorAll(".coverage-row .badge")].map((b) =>
      b.textContent?.trim().toLowerCase(),
    ),
  })),
);

if (stories.length === 0) problems.push("no stories rendered");

for (const story of stories) {
  // Positions named in the coverage list, cross-checked against the bar.
  const shown = new Set(story.badges.filter(Boolean));
  const barred = new Set(
    story.cells
      .map((c, i) => [c, ["left", "lean-left", "center", "lean-right", "right"][i]])
      .filter(([c]) => c && /^\d+$/.test(c))
      .map(([, name]) => name),
  );
  for (const position of shown) {
    if (position === "unrated") continue;
    if (!barred.has(position)) {
      problems.push(
        `"${story.headline}": coverage list claims ${position} but the ` +
          `histogram does not show it`,
      );
    }
  }
}

await page.screenshot({ path: `${OUT}/feed.png`, fullPage: true });
for (const [tab, file] of [
  ["sources", "sources"],
  ["my balance", "balance"],
]) {
  await page.getByRole("tab", { name: tab }).click();
  await page.waitForTimeout(900);
  await page.screenshot({ path: `${OUT}/${file}.png`, fullPage: true });
}

await browser.close();

console.log(`rendered ${stories.length} stories; screenshots in ${OUT}/`);
if (problems.length) {
  console.error("\nPROBLEMS:\n" + problems.join("\n"));
  process.exit(1);
}
console.log("smoke test passed");
