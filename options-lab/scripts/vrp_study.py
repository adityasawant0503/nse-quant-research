"""India volatility risk premium: measurement, strategy backtests, walk-forward test.

Writes results/vrp_premium.png, results/vrp_strategies.png and results/vrp_results.json
(read by the dashboard and PulsEdge Trade).

Usage: python scripts/vrp_study.py --data data
"""

import argparse
import json
import os

import matplotlib
import numpy as np
import pandas as pd

import _path  # noqa: F401
from optlab import vrp

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

BLUE, ORANGE, AQUA, RED = "#2a78d6", "#eb6834", "#1baf7a", "#e34948"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK2,
        "xtick.color": INK2,
        "ytick.color": INK2,
        "text.color": INK,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "lines.linewidth": 2,
        "legend.frameon": False,
    }
)
SPLIT = "2017-01-01"
STRATS = {"hedged_straddle": "Hedged straddle", "short_strangle": "Short strangle", "iron_condor": "Iron condor"}
MARGIN = 0.12  # assumed margin as a fraction of notional, for the return-on-capital column


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="results")
    a = ap.parse_args()
    df = vrp.load_vix_nifty(a.data)
    t = vrp.vrp_table(df)
    m = t.dropna()
    F = vrp.filters(df)
    print(f"India VIX vs Nifty, {df.index[0].date()} -> {df.index[-1].date()} ({len(df)} days)")
    print(f"  VIX average {m.vix.mean():.1%}, volatility over the following month {m.rv_next.mean():.1%}")
    print(
        f"  VIX above the following month's volatility on {(m.gap > 0).mean():.0%} of days; "
        f"median gap {m.gap.median() * 100:.1f} vol points"
    )
    yearly = m.gap.groupby(m.index.year).median()
    print(f"  median gap positive in {(yearly > 0).sum()} of {len(yearly)} years")

    rows, curves = [], {}
    for s, name in STRATS.items():
        for fname, f in F.items():
            tr = vrp.backtest(df, s, entry_filter=f)
            ins, oos, full = vrp.summary(tr[:SPLIT]), vrp.summary(tr[SPLIT:]), vrp.summary(tr)
            rows.append(
                dict(
                    strategy=s,
                    name=name,
                    filter=fname,
                    sharpe_in=ins["sharpe"],
                    **{f"oos_{k}": v for k, v in oos.items()},
                    full_avg=full["avg_pct"],
                    full_worst=full["worst_pct"],
                    full_worst_date=str(full["worst_date"].date()),
                    full_win=full["win_rate"],
                    full_sharpe=full["sharpe"],
                    full_trades=full["trades"],
                )
            )
            curves[(s, fname)] = tr
    R = pd.DataFrame(rows)
    picks = {s: g.loc[g.sharpe_in.idxmax(), "filter"] for s, g in R.groupby("strategy")}
    print(
        f"\nWalk-forward: filter chosen on 2008-2016, tested on 2017-2025 (margin assumption {MARGIN:.0%} of notional)"
    )
    print(
        f"  {'strategy':16s} {'filter':28s} {'OOS avg/mo':>10s} {'on margin':>9s}"
        f" {'win':>5s} {'worst':>8s} {'Sharpe':>6s}"
    )
    for s, f in picks.items():
        r = R[(R.strategy == s) & (R["filter"] == f)].iloc[0]
        print(
            f"  {s:16s} {f:28s} {r.oos_avg_pct:+10.3%} {r.oos_avg_pct / MARGIN:+9.2%} {r.oos_win_rate:5.0%} "
            f"{r.oos_worst_pct:+8.2%} {r.oos_sharpe:6.2f}"
        )
    best = picks["hedged_straddle"]
    bt = curves[("hedged_straddle", best)]
    print(f"\nWorst months, hedged straddle ('{best}'):")
    for d, r in bt.nsmallest(5, "pnl_pct").iterrows():
        print(f"  {d.date()}  {r.pnl_pct:+.2%}  VIX {r.vix:.0%} -> realised {r.rv:.0%}")

    os.makedirs(a.out, exist_ok=True)
    # ---- figure 1: premium
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.2), gridspec_kw={"width_ratios": [2.2, 1]})
    mm = m.resample("ME").mean()
    a1.plot(mm.index, mm.vix * 100, color=BLUE, label="India VIX (what options priced in)")
    a1.plot(mm.index, mm.rv_next * 100, color=ORANGE, label="What Nifty actually moved, next month")
    a1.fill_between(mm.index, mm.rv_next * 100, mm.vix * 100, where=mm.vix > mm.rv_next, color=BLUE, alpha=0.12, lw=0)
    a1.set_ylabel("Volatility, % a year")
    a1.set_title("Options in India are usually priced for more movement than happens")
    a1.legend(loc="upper right", fontsize=9)
    a2.hist(np.clip(m.gap * 100, -25, 25), bins=50, range=(-25, 25), color=BLUE, edgecolor=SURFACE)
    a2.axvline(0, color=INK2, lw=1)
    a2.axvline(m.gap.median() * 100, color=ORANGE, lw=2)
    a2.text(
        m.gap.median() * 100 + 0.6,
        a2.get_ylim()[1] * 0.9,
        f"median +{m.gap.median() * 100:.1f} pts",
        color=INK,
        fontsize=9,
    )
    a2.set_xlabel("VIX minus next month's volatility (points, clipped at ±25)")
    a2.set_title(f"Positive on {(m.gap > 0).mean():.0%} of days")
    fig.tight_layout()
    fig.savefig(os.path.join(a.out, "vrp_premium.png"), dpi=160)
    plt.close(fig)
    # ---- figure 2: strategies
    fig, ax = plt.subplots(figsize=(11, 4.6))
    ends = []
    for s, c in [("hedged_straddle", BLUE), ("iron_condor", AQUA), ("short_strangle", ORANGE)]:
        cum = curves[(s, picks[s])].pnl_pct.cumsum() * 100
        lab = f"{STRATS[s]}" + (" (with entry filter)" if picks[s] != "always" else "")
        ax.plot(cum.index, cum, color=c, label=lab)
        ends.append([cum.iloc[-1], cum.index[-1], f" {STRATS[s].split()[-1]} {cum.iloc[-1]:+.0f}%"])
    ends.sort()
    for i in range(1, len(ends)):  # keep end labels at least 3 points apart
        ends[i][0] = max(ends[i][0], ends[i - 1][0] + 3.5)
    for y, x, txt in ends:
        ax.annotate(txt, (x, y), fontsize=9, color=INK, va="center", annotation_clip=False)
    ax.axvspan(pd.Timestamp(SPLIT), df.index[-1], color=INK2, alpha=0.06, lw=0)
    ax.text(
        pd.Timestamp(SPLIT),
        ax.get_ylim()[1] * 0.95,
        "  2017-2025: rules not fitted here",
        fontsize=9,
        color=INK2,
        va="top",
    )
    ax.axhline(0, color=INK2, lw=0.8)
    ax.set_ylabel("Cumulative P&L, % of Nifty notional")
    ax.set_title("Selling Nifty options monthly at India VIX prices, after all NSE charges and spreads")
    ax.legend(loc="upper left", fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(a.out, "vrp_strategies.png"), dpi=160)
    plt.close(fig)

    # ---- JSON for the terminal and dashboard
    last = t.iloc[-1]
    hist = m.gap.values
    res = {
        "period": [str(df.index[0].date()), str(df.index[-1].date())],
        "premium": {
            "vix_avg": m.vix.mean(),
            "rv_next_avg": m.rv_next.mean(),
            "share_positive": (m.gap > 0).mean(),
            "median_gap": m.gap.median(),
            "gap_pct": {str(p): float(np.quantile(hist, p)) for p in (0.1, 0.25, 0.5, 0.75, 0.9)},
            "yearly_median_gap": {str(k): float(v) for k, v in yearly.items()},
        },
        "latest": {
            "date": str(df.index[-1].date()),
            "nifty": float(last.close),
            "vix": float(last.vix),
            "rv_past": float(last.rv_past),
            "vix_pct_1y": float(vrp.vix_percentile(df.vix).iloc[-1]),
        },
        "vix_history": {
            "dates": [str(d.date()) for d in df.index[::5]],
            "vix": [round(float(x), 4) for x in df.vix.values[::5]],
            "rv_past": [None if np.isnan(x) else round(float(x), 4) for x in t.rv_past.values[::5]],
        },
        "margin_assumption": MARGIN,
        "split": SPLIT,
        "strategies": [
            {
                k: (None if isinstance(v, float) and np.isnan(v) else (str(v.date()) if hasattr(v, "date") else v))
                for k, v in r.items()
            }
            for r in R.to_dict("records")
        ],
        "picks": picks,
        "curves": {
            s: {
                "dates": [str(d.date()) for d in curves[(s, picks[s])].index],
                "pnl_pct": [round(float(x), 6) for x in curves[(s, picks[s])].pnl_pct],
            }
            for s in STRATS
        },
    }
    with open(os.path.join(a.out, "vrp_results.json"), "w") as f:
        json.dump(res, f, separators=(",", ":"), default=float)
    print(f"\nwrote {a.out}/vrp_premium.png, vrp_strategies.png, vrp_results.json")


if __name__ == "__main__":
    main()
