"""India volatility risk premium (VRP): measurement and systematic option-selling backtests.

Option prices are set from India VIX on the entry day (VIX is the market's
30-day implied volatility for Nifty), so this uses real implied volatility,
not a model of it. What it can't capture is the exact price of each strike
(the volatility smile) or the live bid-ask spread: a `skew` parameter and a
per-option slippage allowance stand in for those.

Units: P&L is in Nifty index points per unit of each option (multiply by
the lot size for rupees per lot) and also as a % of spot. Each trade is entered
on a trading day and held `days` trading days (21 = a monthly expiry).
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

from . import bs
from .hedging import hedge_pnl

R, Q = 0.06, 0.013  # risk-free rate, Nifty dividend yield
STEP = 50  # Nifty strike interval

# NSE charges on options, fractions of premium turnover (Budget 2026 rates)
OPT_STT_SELL = 0.0015  # STT on the sell side of option premium
OPT_EXCH = 0.0003503  # NSE transaction charge on premium
OPT_STAMP_BUY = 0.00003
SEBI, GST = 0.000001, 0.18
FUT_COST = 0.00078  # futures hedge, per side, all-in
BROKERAGE_PTS = 20 / 75  # Rs 20 per order spread over a 75-unit lot, in index points
SLIP_PCT, SLIP_MIN = 0.005, 0.25  # half bid-ask: 0.5% of premium, at least 0.25 points


# ---------------------------------------------------------------- data
def load_vix_nifty(data_dir: str) -> pd.DataFrame:
    """Daily Nifty close and India VIX (as a decimal), 2008 onwards."""
    a = pd.read_csv(os.path.join(data_dir, "india_vix_2008_2024.csv"), encoding="utf-8-sig")
    a = pd.Series(a["vixPrice"].astype(float).values, index=pd.to_datetime(a["Date"], format="%m/%d/%Y"))
    b = pd.read_csv(os.path.join(data_dir, "india_vix_2015_2025.csv"), parse_dates=["Date"]).set_index("Date")["Close"]
    vix = pd.concat([a[a.index < b.index[0]], b]).sort_index()
    n1 = pd.read_csv(os.path.join(data_dir, "nifty50_index.csv"))
    n1 = pd.Series(n1["Close"].astype(float).values, index=pd.to_datetime(n1["Date"]))
    n2 = pd.read_csv(os.path.join(data_dir, "nifty50_2015_2025.csv"), parse_dates=["Date"]).set_index("Date")["Close"]
    nifty = pd.concat([n1, n2[n2.index > n1.index.max()]]).sort_index()
    df = pd.DataFrame({"close": nifty[~nifty.index.duplicated()], "vix": vix[~vix.index.duplicated()] / 100}).dropna()
    return df[(df.vix > 0) & (df.close > 0)]


# ---------------------------------------------------------------- measurement
def realised_vol(close: pd.Series, days: int = 21, forward: bool = False) -> pd.Series:
    """Annualised close-to-close volatility over `days`; forward=True looks ahead (for measurement only)."""
    lr = np.log(close).diff()
    rv = lr.rolling(days).std() * np.sqrt(252)
    return rv.shift(-days) if forward else rv


def vrp_table(df: pd.DataFrame, days: int = 21) -> pd.DataFrame:
    """VIX vs the volatility that actually followed over the next `days` trading days."""
    out = df.copy()
    out["rv_next"] = realised_vol(df.close, days, forward=True)
    out["rv_past"] = realised_vol(df.close, days)
    out["gap"] = out.vix - out.rv_next  # volatility points (as decimals)
    out["var_premium"] = out.vix**2 - out.rv_next**2
    return out


def vix_percentile(vix: pd.Series, lookback: int = 252) -> pd.Series:
    """Where today's VIX sits in its own trailing one-year range (0-1)."""
    return vix.rolling(lookback).apply(lambda w: (w[:-1] < w[-1]).mean(), raw=True)


# ---------------------------------------------------------------- pricing helpers
def strike_vol(atm_vol, S, K, T, skew=0.0):
    """Smile: `skew` vol points per standard deviation below spot (puts richer). 0 = flat."""
    z = np.log(np.asarray(K, float) / S) / (atm_vol * np.sqrt(T))
    return np.maximum(atm_vol - skew * z, 0.02)


def leg_cost(premium, side):
    """Charges + half-spread on one option order, in index points per unit. side +1 buy, -1 sell."""
    premium = np.asarray(premium, float)
    stt = OPT_STT_SELL * premium if side < 0 else 0.0
    stamp = OPT_STAMP_BUY * premium if side > 0 else 0.0
    exch = OPT_EXCH * premium
    gst = (BROKERAGE_PTS + exch + SEBI * premium) * GST
    slip = np.maximum(SLIP_PCT * premium, SLIP_MIN)
    return stt + stamp + exch + SEBI * premium + BROKERAGE_PTS + gst + slip


def _round(x):
    return np.round(np.asarray(x, float) / STEP) * STEP


# ---------------------------------------------------------------- strategies
def _windows(df, days, start=None):
    v = df.close.values
    idx = np.arange(0 if start is None else start, len(v) - days, days)
    return idx, v[idx[:, None] + np.arange(days + 1)]


def backtest(
    df: pd.DataFrame,
    strategy: str,
    days: int = 21,
    wing_sd: float = 1.0,
    outer_sd: float = 2.0,
    skew: float = 0.0,
    entry_filter: np.ndarray | None = None,
) -> pd.DataFrame:
    """Sell options every `days` trading days. One row per trade.

    strategy: "hedged_straddle" (ATM straddle, delta-hedged daily with futures),
              "short_strangle" (short calls/puts `wing_sd` expected moves out, held to expiry),
              "iron_condor"    (short strangle plus long wings `outer_sd` moves out).
    entry_filter: boolean array over df rows; trades are skipped where it is False.
    """
    idx, paths = _windows(df, days)
    S0, ST = paths[:, 0], paths[:, -1]
    iv = df.vix.values[idx]
    T = days / 252
    move = S0 * iv * np.sqrt(T)  # one expected move, index points

    def price(K, kind):
        return bs.price(S0, K, T, R, strike_vol(iv, S0, K, T, skew), kind, Q)

    def payoff(K, kind):
        return np.maximum(ST - K, 0) if kind == "call" else np.maximum(K - ST, 0)

    if strategy == "hedged_straddle":
        K = _round(S0)
        sig = strike_vol(iv, S0, K, T, skew)
        # hedge_pnl returns the short option's hedged P&L / S0, with futures costs on the hedge
        pnl = sum(hedge_pnl(paths, K, T, R, sig, kind, Q, 1, FUT_COST) for kind in ("call", "put")) * S0
        credit = price(K, "call") + price(K, "put")
        costs = leg_cost(price(K, "call"), -1) + leg_cost(price(K, "put"), -1)
        risk = np.full_like(S0, np.nan)
    else:
        kc, kp = _round(S0 + wing_sd * move), _round(S0 - wing_sd * move)
        legs = [(-1, kc, "call"), (-1, kp, "put")]
        if strategy == "iron_condor":
            legs += [(1, _round(S0 + outer_sd * move), "call"), (1, _round(S0 - outer_sd * move), "put")]
        elif strategy != "short_strangle":
            raise ValueError(f"unknown strategy {strategy}")
        credit = -sum(s * price(k, t) for s, k, t in legs)
        pnl = credit + sum(s * payoff(k, t) for s, k, t in legs)  # premium kept + what the legs pay at expiry
        costs = sum(leg_cost(price(k, t), s) for s, k, t in legs)
        if strategy == "iron_condor":
            width = np.maximum(legs[2][1] - kc, kp - legs[3][1])
            risk = width - credit
        else:
            risk = np.full_like(S0, np.nan)
    net = pnl - costs
    out = pd.DataFrame(
        {
            "S0": S0,
            "ST": ST,
            "vix": iv,
            "credit": credit,
            "gross": pnl,
            "costs": costs,
            "pnl": net,
            "pnl_pct": net / S0,
            "max_risk": risk,
            "rv": np.diff(np.log(paths), axis=1).std(axis=1, ddof=1) * np.sqrt(252),
        },
        index=pd.Index(df.index[idx], name="date"),
    )
    if entry_filter is not None:
        out = out[np.asarray(entry_filter)[idx]]
    return out


# ---------------------------------------------------------------- entry filters (known on the entry day)
def filters(df: pd.DataFrame) -> dict[str, np.ndarray]:
    rv_past = realised_vol(df.close).values
    vix = df.vix.values
    vix_avg = df.vix.rolling(10).mean().values
    return {
        "always": np.ones(len(df), bool),
        "vix above recent realised": np.nan_to_num(vix - rv_past) > 0,
        "vix not spiking": np.nan_to_num(vix / vix_avg, nan=1) <= 1.10,
        "both": (np.nan_to_num(vix - rv_past) > 0) & (np.nan_to_num(vix / vix_avg, nan=1) <= 1.10),
    }


def summary(trades: pd.DataFrame, per_year: float = 12.0) -> dict:
    """Per-trade statistics. Returns use % of spot; condors also report % of max risk."""
    p = trades.pnl_pct
    if len(p) < 3:
        return {"trades": len(p)}
    eq = p.cumsum()
    out = {
        "trades": len(p),
        "avg_pct": p.mean(),
        "win_rate": (p > 0).mean(),
        "worst_pct": p.min(),
        "worst_date": p.idxmin(),
        "sharpe": p.mean() / p.std() * np.sqrt(per_year) if p.std() > 0 else np.nan,
        "max_dd_pct": (eq - eq.cummax()).min(),
        "cost_share": trades.costs.sum() / trades.credit.sum(),
    }
    if trades.max_risk.notna().all():
        r = trades.pnl / trades.max_risk
        out.update(avg_on_risk=r.mean(), worst_on_risk=r.min())
    return out
