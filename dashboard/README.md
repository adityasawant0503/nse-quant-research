# Nifty Quant Lab (interactive dashboard)

One static web page for two audiences: traders who want practical tools, and
recruiters who want to see the research. It opens on a **Start here** page that
explains everything in plain English, with a 1-minute video tour.

**Tools (use them for real decisions)**
- **Trade planner**: position size from capital, risk %, entry and stop. It
  includes every NSE charge (STT, exchange fees, GST, stamp duty, SEBI fee,
  brokerage) for intraday, delivery, futures and option buying. It also checks
  expectancy and simulates 100 trades to show realistic losing streaks.
- **Option strategy builder**: 10 Nifty templates (spreads, straddles,
  strangles, iron condor, covered call, protective put) or custom legs. Shows
  the payoff at expiry and today, max profit and loss, breakevens, chance of
  profit, position Greeks and the charges to open.
- **Option pricer**: Black-Scholes, binomial tree and Monte Carlo prices,
  Greeks, implied volatility and a put-call parity check.

**Research (learn from it)**
- **Hedging lab**: the 2001-2023 Nifty delta-hedging backtest, re-run live.
- **Trend explorer**: any SMA/EMA rule, with costs and a look-ahead toggle.
- **Value at Risk**: four models backtested, and the effect of correlation.
- **Pairs trading**: in-sample vs out-of-sample for 69 Nifty pairs.

Every tab has an "In plain English" panel (what it is, how to use it, what to
notice, key terms) and a 20-40 second how-to video. The videos are recorded
automatically by `videos/make_videos.js` (Playwright + ffmpeg); re-run it with
`make videos` after changing the page.

There's no framework and no build step: `index.html`, `lib.js` (the maths) and
two JSON data files. The charts are hand-written SVG.

## Run locally

```bash
cd dashboard && python -m http.server 8000     # then open http://localhost:8000
```

Opening `index.html` straight from disk won't work, because browsers block
`fetch()` of local files.

## How the numbers stay honest

`lib.js` is a line-for-line JavaScript port of the Python libraries in
`../options-lab` and `../quant-finance`. `build_data.py` exports the Nifty prices
and the precomputed studies, along with Python reference values. `test_lib.mjs`
checks the port against those values, and the NSE charge rates against the Python cost model: prices, Greeks, the American put, Monte
Carlo, implied volatility, all 271 hedging months and two trend rules all agree
to about 6 decimal places.

```bash
python dashboard/build_data.py   # needs both projects' data/fetch_data.sh run first
node dashboard/test_lib.mjs
```

## Hosting

`.github/workflows/pages.yml` publishes the dashboard automatically on every
push to `main`. It downloads the data, rebuilds the JSON, re-runs the JS check,
and `build_site.sh` wraps the page into a standalone site. To switch it on once,
go to the repo's Settings → Pages → Source and choose "GitHub Actions". The site
then appears at `https://<username>.github.io/<repo>/`.

`data/` is not committed, because `nifty.json` repackages a third-party dataset
with no stated licence. The workflow regenerates it on every build.
