// Records the "how to use" videos for each dashboard tab.
// Usage (from dashboard/, after build_data.py): node videos/make_videos.js [name ...]
// Needs Playwright (Chromium) and ffmpeg with libx264. Output: videos/<name>.mp4
const { chromium } = require("playwright");
const http = require("http"), fs = require("fs"), path = require("path"), { execFileSync } = require("child_process");

const ROOT = path.resolve(__dirname, ".."), OUT = __dirname, W = 1280, H = 720;
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".json": "application/json", ".mp4": "video/mp4" };
function serve() {
  return new Promise((res) => {
    const srv = http.createServer((req, rsp) => {
      const f = path.join(ROOT, decodeURIComponent(req.url.split("?")[0]).replace(/^\/$/, "/index.html"));
      if (!f.startsWith(ROOT) || !fs.existsSync(f)) { rsp.writeHead(404); return rsp.end(); }
      rsp.writeHead(200, { "Content-Type": TYPES[path.extname(f)] || "application/octet-stream" });
      fs.createReadStream(f).pipe(rsp);
    }).listen(0, () => res(srv));
  });
}

// overlay: caption bar + visible cursor, injected into every page
const OVERLAY = `
  const st = document.createElement('style');
  st.textContent = '#cap{position:fixed;left:50%;bottom:26px;transform:translateX(-50%);max-width:1000px;background:rgba(12,16,22,.92);color:#fff;font:600 24px/1.35 Inter,system-ui,sans-serif;padding:14px 22px;border-radius:12px;z-index:99999;text-align:center;box-shadow:0 8px 30px rgba(0,0,0,.35);transition:opacity .25s}#cap small{display:block;font-weight:400;font-size:17px;opacity:.85;margin-top:4px}#cur{position:fixed;width:22px;height:22px;border-radius:50%;background:rgba(235,104,52,.85);border:3px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.4);z-index:100000;pointer-events:none;transform:translate(-50%,-50%);transition:transform .12s}#cur.down{transform:translate(-50%,-50%) scale(.7)}';
  document.head.appendChild(st);
  const cap = document.createElement('div'); cap.id = 'cap'; cap.style.opacity = 0; document.body.appendChild(cap);
  const cur = document.createElement('div'); cur.id = 'cur'; cur.style.left = '640px'; cur.style.top = '360px'; document.body.appendChild(cur);
  addEventListener('mousemove', e => { cur.style.left = e.clientX + 'px'; cur.style.top = e.clientY + 'px'; });
  addEventListener('mousedown', () => cur.classList.add('down')); addEventListener('mouseup', () => cur.classList.remove('down'));
  window.__cap = (t, s) => { cap.innerHTML = t + (s ? '<small>' + s + '</small>' : ''); cap.style.opacity = t ? 1 : 0; };
`;

function director(page) {
  let mx = 640, my = 360;
  const wait = (ms) => page.waitForTimeout(ms);
  const say = async (t, s = "", ms = 2600) => { await page.evaluate(([a, b]) => window.__cap(a, b), [t, s]); await wait(ms); };
  const show = async (sel) => { await page.locator(sel).first().evaluate((e) => e.scrollIntoView({ behavior: "smooth", block: "center" })); await wait(700); };
  const moveTo = async (sel, fx = 0.5, fy = 0.5) => {
    await page.locator(sel).first().waitFor({ state: "visible", timeout: 10000 });
    const b = await page.locator(sel).first().boundingBox();
    const x = b.x + b.width * fx, y = b.y + b.height * fy;
    await page.mouse.move(x, y, { steps: 18 }); mx = x; my = y; await wait(250);
  };
  const click = async (sel) => { await show(sel); await moveTo(sel); await page.mouse.down(); await wait(80); await page.mouse.up(); await wait(500); };
  const type = async (sel, v) => { await show(sel); await moveTo(sel); await page.mouse.down(); await page.mouse.up(); await wait(150); await page.locator(sel).first().fill(String(v)); await page.locator(sel).first().dispatchEvent("change"); await wait(450); };
  const select = async (sel, v) => { await show(sel); await moveTo(sel); await page.selectOption(sel, v); await page.locator(sel).first().dispatchEvent("input"); await wait(700); };
  // drag a range input from its current value to v, through the real mouse
  const slide = async (sel, v) => {
    await show(sel);
    const el = page.locator(sel).first(), b = await el.boundingBox();
    const { min, max, val } = await el.evaluate((e) => ({ min: +e.min, max: +e.max, val: +e.value }));
    const X = (x) => b.x + 8 + (b.width - 16) * (x - min) / (max - min), y = b.y + b.height / 2;
    await page.mouse.move(X(val), y, { steps: 14 }); await page.mouse.down();
    await page.mouse.move(X(v), y, { steps: 28 }); await page.mouse.up(); mx = X(v); my = y; await wait(700);
  };
  const scrollTo = async (sel) => show(sel);
  const go = async (hash) => { await page.evaluate((h) => { location.hash = h; }, hash); await wait(900); await page.evaluate(() => scrollTo({ top: 0 })); };
  const step = async (t, sub, fn, hold = 1800) => { await page.evaluate(([a, b]) => window.__cap(a, b), [t, sub]); await wait(900); if (fn) await fn(); await wait(hold); };
  return { wait, say, step, show, moveTo, click, type, select, slide, scrollTo, go };
}

const SCRIPTS = {
  tour: async (d) => {
    await d.step("Nifty Quant Lab", "Tools to plan trades on Indian markets, and research on 20+ years of Nifty data", null, 2200);
    await d.step("Tools you can use today", "Size a trade, build an option strategy, price an option", () => d.moveTo("#cards-tools .card:nth-child(1)"), 1800);
    await d.step("Research", "The one edge that held up on unseen data, with real NSE charges", async () => { await d.show("#cards-research"); await d.moveTo("#cards-research .card:nth-child(1)"); }, 1800);
    await d.step("Each section says: use it, learn from it, or avoid it", "", () => d.show("#use-table"), 2000);
    await d.step("Trade planner", "How many shares to buy so your stop-loss costs exactly what you planned", () => d.click('nav.tabs a[href="#planner"]'), 2200);
    await d.step("Option strategy builder", "Max profit, max loss, breakevens and chance of profit for any Nifty options trade", () => d.click('nav.tabs a[href="#strategy"]'), 2400);
    await d.step("Volatility edge", "18 years of India VIX data: where option sellers have an edge", () => d.click('nav.tabs a[href="#edge"]'), 2400);
    await d.step("Every tab has a plain-English guide", "and a short video like this one", () => d.moveTo(".view:not([hidden]) .explain summary"), 2400);
  },
  planner: async (d) => {
    await d.step("Trade planner", "Work out position size before you enter a trade", null, 1600);
    await d.step("1. Choose what you trade", "Intraday, delivery, futures or buying options: each has different NSE charges", () => d.select("#tp-inst", "equity_intraday"), 1600);
    await d.step("2. Your capital and risk per trade", "Risking 1% of ₹3 lakh means a stop-loss costs ₹3,000 at most", async () => { await d.type("#tp-cap", 300000); await d.slide("#tp-risk", 1); }, 1600);
    await d.step("3. Entry, stop-loss and target", "", async () => { await d.type("#tp-tgt", 2500); await d.type("#tp-entry", 2450); await d.type("#tp-stop", 2425); }, 1000);
    await d.step("Buy this many shares", "The loss at the stop includes brokerage, STT, GST and every other charge", () => d.moveTo("#tp-stats .stat:nth-child(1)"), 2200);
    await d.step("Every charge, itemised", "Small intraday targets can lose a big share to charges", () => d.show("#tp-charges"), 2200);
    await d.step("4. Enter your real win rate", "At 35% wins and this reward : risk, the plan barely makes money", () => d.slide("#tp-wr", 35), 2200);
    await d.step("100 trades, simulated 2,000 times", "Same skill, different luck: expect losing streaks and drawdowns", async () => { await d.slide("#tp-wr", 50); await d.show("#tp-sim"); }, 2600);
  },
  strategy: async (d) => {
    await d.step("Option strategy builder", "See what any Nifty options strategy can make or lose", null, 1600);
    await d.step("Pick a strategy", "An iron condor bets that Nifty stays in a range", () => d.select("#os-name", "Iron condor"), 1600);
    await d.step("Max profit, max loss and breakevens", "Read these before you place the trade", async () => { await d.show("#os-stats"); await d.moveTo("#os-stats .stat:nth-child(3)"); }, 1800);
    await d.step("Chance of profit", "Estimated from implied volatility (India VIX)", () => d.moveTo("#os-stats .stat:nth-child(5)"), 1600);
    await d.step("Orange: profit or loss at expiry", "Blue: today's value if Nifty jumped there right now", () => d.show("#os-chart"), 2400);
    await d.step("Higher volatility: bigger premiums", "but a wider range of likely outcomes", () => d.slide("#os-iv", 20), 1800);
    await d.step("A short straddle has unlimited loss", "The builder warns you", async () => { await d.select("#os-name", "Short straddle"); await d.show("#os-stats"); await d.moveTo("#os-stats .stat:nth-child(3)"); }, 2000);
    await d.step("Type real premiums from your broker's option chain", "to plan an actual trade", async () => { await d.show("#os-legs"); await d.moveTo('#os-legs input[data-k="premium"]'); }, 2200);
  },
  pricer: async (d) => {
    await d.step("Option pricer", "Fair value of a Nifty option, three independent ways", null, 1600);
    await d.step("Black-Scholes, binomial tree and Monte Carlo", "If they agree, the maths is right", () => d.show("#p-prices"), 1800);
    await d.step("Fewer days left: cheaper option", "Time decay (theta) speeds up near expiry", () => d.slide("#p-days", 5), 1800);
    await d.step("Higher volatility: more expensive option", "Vega measures this", () => d.slide("#p-vol", 25), 1600);
    await d.step("The Greeks in plain words", "How the price reacts to Nifty, time and volatility", () => d.show("#p-greeks"), 2200);
    await d.step("Type a market price", "to see the volatility the market is implying", async () => { await d.type("#p-mkt", 600); await d.moveTo("#p-iv"); }, 2200);
  },
  edge: async (d) => {
    await d.step("Volatility edge", "Do Indian option prices assume more movement than really happens?", null, 2000);
    await d.step("Since 2008, India VIX was above what followed on 81% of days", "That gap is what option sellers earn", () => d.show("#e-stats"), 2400);
    await d.step("Blue: what options priced in. Orange: what Nifty actually did", "", () => d.show("#e-chart1"), 2400);
    await d.step("Three ways to sell options, after all NSE charges", "Rules chosen on 2008–2016, judged only on 2017–2025", () => d.show("#e-chart2"), 2600);
    await d.step("Results on data the rules never saw", "Small gains most months, occasional sharp losses", () => d.show("#e-table"), 2400);
    await d.step("Check today: type today's India VIX", "It tells you if conditions match the selling rule", async () => { await d.type("#e-vix", 13.5); await d.moveTo("#e-verdict"); }, 2400);
    await d.step("A VIX spike breaks the rule", "Selling into a panic is when this strategy loses most", async () => { await d.type("#e-vix", 19); await d.moveTo("#e-verdict"); }, 2600);
  },
};

(async () => {
  const want = process.argv.slice(2).length ? process.argv.slice(2) : Object.keys(SCRIPTS);
  const srv = await serve(), port = srv.address().port, browser = await chromium.launch();
  for (const name of want) {
    const tmp = fs.mkdtempSync(path.join(require("os").tmpdir(), "vid-"));
    const ctx = await browser.newContext({ viewport: { width: W, height: H }, colorScheme: "light", recordVideo: { dir: tmp, size: { width: W, height: H } } });
    await ctx.addInitScript(() => { try { localStorage.clear(); } catch { /* ignore */ } });
    const page = await ctx.newPage();
    await page.goto(`http://localhost:${port}/#${name === "tour" ? "start" : name}`);
    await page.waitForFunction(() => document.querySelector("#loading[hidden]") && document.querySelector(".view:not([hidden]) .panel, .view:not([hidden]) .card"), null, { timeout: 30000 });
    await page.addScriptTag({ content: OVERLAY });
    if (name !== "tour") await page.evaluate(() => document.querySelectorAll(".explain").forEach((e) => (e.open = false)));
    await page.waitForTimeout(600);
    await SCRIPTS[name](director(page));
    const video = page.video(); await ctx.close();
    const webm = await video.path(), mp4 = path.join(OUT, name + ".mp4");
    execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-ss", "0.8", "-i", webm, "-vf", "fps=25", "-c:v", "libx264", "-preset", "slow", "-crf", "28",
      "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", mp4]);
    fs.rmSync(tmp, { recursive: true, force: true });
    console.log(`${name}.mp4  ${(fs.statSync(mp4).size / 1024).toFixed(0)} KB`);
  }
  await browser.close(); srv.close();
})();
