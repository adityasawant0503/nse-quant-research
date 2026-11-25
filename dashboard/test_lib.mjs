// Checks the JavaScript port (lib.js) against the Python reference values that
// build_data.py wrote into data/results.json. Run: node dashboard/test_lib.mjs
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const QL = createRequire(import.meta.url)(join(here, "lib.js"));
const res = JSON.parse(readFileSync(join(here, "data/results.json"), "utf8"));
const nifty = JSON.parse(readFileSync(join(here, "data/nifty.json"), "utf8"));
const ref = res.reference;
let fails = 0;
function close(name, got, want, tol) {
  const ok = Math.abs(got - want) <= tol;
  if (!ok) fails++;
  console.log(`${ok ? "ok  " : "FAIL"} ${name}: got ${got.toPrecision(8)} expected ${Number(want).toPrecision(8)}`);
}

close("BS call", QL.bsPrice(100, 100, 1, 0.05, 0.2), ref.bs_call, 1e-6);
close("BS put", QL.bsPrice(100, 100, 1, 0.05, 0.2, "put"), ref.bs_put, 1e-6);
const g = QL.bsGreeks(100, 100, 1, 0.05, 0.2, "call", 0.013);
for (const k of ["delta", "gamma", "vega", "theta", "rho"]) close(`greek ${k}`, g[k], ref.greeks_call[k], 1e-5 * Math.max(1, Math.abs(ref.greeks_call[k])));
close("binomial American put", QL.binomialPrice(100, 100, 1, 0.05, 0.2, "put", 0, 500, true), ref.binomial_american_put, 1e-9);
const mc = QL.mcPrice(100, 100, 1, 0.05, 0.2, "call", 0, 200000, 7);
close("Monte Carlo within 3 SE", mc.price, ref.bs_call, 3 * mc.se);
close("implied vol round trip", QL.impliedVol(ref.bs_call, 100, 100, 1, 0.05), 0.2, 1e-6);

const px = nifty.close;
for (const [mk, want] of Object.entries(ref.hedge)) {
  const bt = QL.hedgeBacktest(px, { markup: Number(mk) });
  const pnl = bt.map((d) => d.pnl), mean = pnl.reduce((a, b) => a + b) / pnl.length;
  close(`hedge markup ${mk} months`, bt.length, want.n, 0);
  close(`hedge markup ${mk} mean P&L`, mean, want.mean, 1e-6);
  close(`hedge markup ${mk} worst`, Math.min(...pnl), want.min, 1e-6);
}

const ret = px.map((p, i) => (i === 0 ? 0 : p / px[i - 1] - 1) + 0.013 / 252);
const [buy, sell] = res.ma_grid.costs_bps.map((x) => x / 1e4);
const cash = Math.pow(1.06, 1 / 252) - 1;
for (const [key, f, s, kind] of [["ma_sma_50_200", 50, 200, "SMA"], ["ma_ema_20_50", 20, 50, "EMA"]]) {
  const st = QL.perfStats(QL.runRule(px, ret, f, s, kind, buy, sell, cash, 250).r, 0.06);
  for (const m of ["CAGR", "Sharpe", "MaxDD"]) close(`${kind} ${f}/${s} ${m}`, st[m], ref[key][m], 2e-4);
}
// ---- trading tools ----
const raw = res.charges_raw;
for (const [py, js] of [["equity_delivery", "equity_delivery"], ["futures", "futures"]]) {
  const [sb, ss, st, ex] = raw.rates[py], c = QL.CHARGES[js];
  close(`charges ${js} STT buy`, c.sttBuy, sb, 0); close(`charges ${js} STT sell`, c.sttSell, ss, 0);
  close(`charges ${js} stamp`, c.stampBuy, st, 0); close(`charges ${js} exchange`, c.exch, ex, 0);
}
// position size: largest quantity whose loss at the stop (with charges) fits the budget
const ps = QL.positionSize({ capital: 200000, riskPct: 0.01, entry: 1500, stop: 1485, target: 1530, inst: "equity_intraday" });
const next = QL.positionSize({ capital: 200000 * (ps.qty + 1) / ps.qty * 1.0001, riskPct: 0.01, entry: 1500, stop: 1485, inst: "equity_intraday" });
close("position size within budget", Math.min(ps.lossAtStop, 2000), ps.lossAtStop, 0);
close("one more share would exceed budget", ps.lossAtStop + 15 + ps.chargesAtStop.total / ps.qty > 2000 ? 1 : 0, 1, 0);
close("lots are whole", QL.positionSize({ capital: 500000, riskPct: 0.02, entry: 24000, stop: 23900, inst: "futures", lotSize: 75 }).qty % 75, 0, 0);
close("wrong-side stop rejected", QL.positionSize({ capital: 1e5, riskPct: 0.01, entry: 100, stop: 101 }).error ? 1 : 0, 1, 0);
void next;
// expectancy: 1:2 needs 33.3% wins to break even
close("break-even win rate at 1:2", QL.expectancy(0.4, 2).breakevenWinRate, 1 / 3, 1e-12);
close("EV at 40% and 1:2", QL.expectancy(0.4, 2).evR, 0.2, 1e-12);
close("always-win simulation grows exactly", QL.simulateTrades({ winRate: 1, rr: 1, riskPct: 0.01, n: 10, paths: 5 }).p50, Math.pow(1.01, 10), 1e-12);
// option strategies
const S = 24000, T = 7 / 365, r = 0.06, q = 0.013, iv = 0.13, lot = 75;
const price = (name) => QL.strategyTemplate(name, S).map((L) => ({ ...L, premium: QL.legPremium(L, S, T, r, iv, q) }));
const lc = price("Long call"), lcs = QL.strategyStats(lc, S, T, r, iv, q, lot);
close("long call breakeven = strike + premium", lcs.breakevens[0], lc[0].strike + lc[0].premium, 0.05);
close("long call max loss = premium paid", lcs.maxLoss, -lc[0].premium * lot, 1e-6);
close("long call profit unlimited", lcs.maxProfit === Infinity ? 1 : 0, 1, 0);
close("value today = 0 at fair premiums", QL.strategyValue(lc, S, T, r, iv, q, lot), 0, 1e-9);
const T2 = (S * Math.exp((r - q) * T)), d2 = (Math.log(S / lcs.breakevens[0]) + (r - q - iv * iv / 2) * T) / (iv * Math.sqrt(T));
close("long call POP = P(S_T > breakeven)", lcs.pop, QL.normCdf(d2), 1e-4);
void T2;
const ic = price("Iron condor"), ics = QL.strategyStats(ic, S, T, r, iv, q, lot);
close("iron condor max loss = (width - credit) x lot", ics.maxLoss, -(200 * lot - ics.netPremium), 1e-6);
close("short straddle loss unlimited", QL.strategyStats(price("Short straddle"), S, T, r, iv, q, lot).maxLoss === -Infinity ? 1 : 0, 1, 0);

console.log(fails ? `\n${fails} FAILED` : "\nall checks passed");
process.exit(fails ? 1 : 0);
