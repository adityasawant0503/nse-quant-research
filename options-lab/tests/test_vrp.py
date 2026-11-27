import numpy as np
import pandas as pd
import pytest

from optlab import bs, vrp


def _synthetic(vol_true=0.15, vix=0.15, n=1500, seed=0):
    rng = np.random.default_rng(seed)
    lr = (0.08 - 0.5 * vol_true**2) / 252 + vol_true / np.sqrt(252) * rng.standard_normal(n)
    idx = pd.bdate_range("2010-01-01", periods=n)
    return pd.DataFrame({"close": 20000 * np.exp(np.cumsum(lr)), "vix": np.full(n, vix)}, index=idx)


def test_no_premium_when_implied_equals_realised():
    t = vrp.vrp_table(_synthetic()).dropna()
    assert abs(t.gap.mean()) < 0.01


def test_selling_rich_volatility_earns_and_cheap_loses():
    rich = vrp.summary(vrp.backtest(_synthetic(vol_true=0.12, vix=0.18), "hedged_straddle"))
    cheap = vrp.summary(vrp.backtest(_synthetic(vol_true=0.20, vix=0.14), "hedged_straddle"))
    assert rich["avg_pct"] > 0 > cheap["avg_pct"]


def test_iron_condor_loss_never_exceeds_max_risk_plus_costs():
    tr = vrp.backtest(_synthetic(vol_true=0.30, vix=0.12, seed=3), "iron_condor")
    assert (tr.pnl >= -(tr.max_risk + tr.costs) - 1e-9).all()
    assert (tr.gross <= tr.credit + 1e-9).all()  # can never earn more than the credit


def test_strangle_expiry_pnl_matches_hand_calculation():
    df = _synthetic(seed=5)
    tr = vrp.backtest(df, "short_strangle")
    r = tr.iloc[0]
    move = r.S0 * r.vix * np.sqrt(21 / 252)
    kc, kp = round((r.S0 + move) / 50) * 50, round((r.S0 - move) / 50) * 50
    T = 21 / 252
    credit = bs.price(r.S0, kc, T, vrp.R, r.vix, "call", vrp.Q) + bs.price(r.S0, kp, T, vrp.R, r.vix, "put", vrp.Q)
    gross = credit - max(r.ST - kc, 0) - max(kp - r.ST, 0)
    assert r.credit == pytest.approx(credit) and r.gross == pytest.approx(gross)


def test_costs_include_sell_side_stt_and_minimum_slippage():
    assert vrp.leg_cost(100.0, -1) - vrp.leg_cost(100.0, 1) == pytest.approx(0.0015 * 100 - 0.00003 * 100)
    assert vrp.leg_cost(1.0, 1) > vrp.SLIP_MIN


def test_filters_only_use_information_known_on_the_entry_day():
    df = _synthetic(seed=7)
    f1 = vrp.filters(df)
    df2 = df.copy()
    df2.iloc[1000:, df2.columns.get_loc("close")] *= 1.5  # change the future
    f2 = vrp.filters(df2)
    for k in f1:
        assert (f1[k][:1000] == f2[k][:1000]).all()


def test_skew_makes_downside_strikes_richer():
    v = vrp.strike_vol(0.15, 20000, np.array([18000, 20000, 22000]), 21 / 252, skew=0.02)
    assert v[0] > v[1] > v[2]
