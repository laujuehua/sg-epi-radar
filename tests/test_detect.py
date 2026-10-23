import numpy as np
import pandas as pd

from sgsurv import detect


def _series(values, start="2012-01-01"):
    return pd.DataFrame({
        "disease": "Test",
        "week_start": pd.date_range(start, periods=len(values), freq="7D"),
        "cases": values,
    })


def test_ears_c2_flags_spike_not_flat():
    values = [20] * 15 + [60] + [20] * 4
    out = detect.ears_c2(pd.Series(values))
    assert out["c2_alert"].iloc[15]
    assert not out["c2_alert"].drop(index=15).any()


def test_ears_c2_needs_full_baseline():
    out = detect.ears_c2(pd.Series([5] * 9 + [100]))
    assert out["c2_stat"].iloc[:9].isna().all()  # 7 baseline + 2 guard weeks


def test_historical_limits_respects_seasonality():
    rng = np.random.default_rng(0)
    weeks = 52 * 7
    t = np.arange(weeks)
    seasonal = 50 + 40 * np.sin(2 * np.pi * t / 52.18)
    values = rng.poisson(seasonal).astype(float)
    values[-10] = seasonal[-10] * 3  # a genuine excess in the final year
    df = _series(values)
    out = detect.historical_limits(df, years=5)
    # needs >= 9 baseline weeks, i.e. 3 previous seasons
    assert out["hl_threshold"].iloc[: 52 * 3 - 2].isna().all()
    assert out["hl_threshold"].iloc[52 * 3 + 2 :].notna().all()
    assert out["hl_alert"].iloc[-10]
    # Ordinary seasonal peaks should rarely alert (~5% of weeks at z = 2)
    assert out["hl_alert"].iloc[-52:].sum() <= 4


def test_min_cases_suppresses_rare_disease_alerts():
    df = _series([0] * 20 + [3])
    out = detect.detect_disease(df)
    assert not out["any_alert"].any()


def test_excluded_years_not_in_baseline():
    df = _series([10.0] * (52 * 6))
    df.loc[df["week_start"].dt.year == 2016, "cases"] = 1000
    with_2016 = detect.historical_limits(df, exclude_years=[])
    without = detect.historical_limits(df, exclude_years=[2016])
    assert with_2016["hl_threshold"].iloc[-1] > without["hl_threshold"].iloc[-1]
