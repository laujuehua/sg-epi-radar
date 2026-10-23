"""Aberration (outbreak signal) detection for weekly case counts.

Two complementary methods, written out by hand so each step is visible:

* EARS C2 (CDC Early Aberration Reporting System): compares this week with
  the mean and SD of a short recent baseline (7 weeks, skipping the 2 weeks
  just before, so an emerging outbreak does not inflate its own baseline).
  Reacts quickly, ignores seasonality.

* Historical limits (Stroup et al., 1989, adapted to weekly counts): compares
  this week with the same time of year in previous years (+/- 1 week around
  the matching week, over 5 years = 15 baseline values). Accounts for
  seasonality but needs several years of history.

The seasonal method is the primary signal; EARS C2 is used where there is no
seasonal baseline yet, and its threshold is still shown on the dashboard.

A week is flagged only when the count is also >= min_cases, so single cases
of rare diseases do not trigger alerts.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import DETECTION


def ears_c2(cases: pd.Series, baseline: int = 7, guard: int = 2, threshold: float = 3.0,
            sd_floor: float = 1.0) -> pd.DataFrame:
    """EARS C2 statistic for a single weekly series (index ignored)."""
    x = cases.astype(float).reset_index(drop=True)
    lagged = x.shift(guard + 1)
    mean = lagged.rolling(baseline, min_periods=baseline).mean()
    sd = lagged.rolling(baseline, min_periods=baseline).std().clip(lower=sd_floor)
    stat = (x - mean) / sd
    return pd.DataFrame({
        "c2_expected": mean.values,
        "c2_threshold": (mean + threshold * sd).values,
        "c2_stat": stat.values,
        "c2_alert": (stat > threshold).values,
    }, index=cases.index)


def historical_limits(series: pd.DataFrame, years: int = 5, half_window: int = 1, z: float = 2.0,
                      sd_floor: float = 1.0, exclude_years: list[int] | None = None,
                      min_baseline: int = 9) -> pd.DataFrame:
    """Seasonal historical-limits threshold.

    `series` needs columns week_start (datetime) and cases, one row per week.
    For each week, the baseline is the counts in weeks centred on the same
    calendar point 1..`years` years earlier, +/- `half_window` weeks.
    """
    exclude = set(exclude_years or [])
    s = series.set_index("week_start")["cases"].astype(float)
    known = set(s.index)
    expected, threshold = [], []
    for week in s.index:
        values = []
        for k in range(1, years + 1):
            centre = week - pd.Timedelta(weeks=round(k * 365.25 / 7))
            for offset in range(-half_window, half_window + 1):
                d = centre + pd.Timedelta(weeks=offset)
                if d in known and d.year not in exclude and pd.notna(s[d]):
                    values.append(s[d])
        if len(values) >= min_baseline:
            m, sd = float(np.mean(values)), max(float(np.std(values, ddof=1)), sd_floor)
            expected.append(m)
            threshold.append(m + z * sd)
        else:
            expected.append(np.nan)
            threshold.append(np.nan)
    out = pd.DataFrame({"hl_expected": expected, "hl_threshold": threshold}, index=series.index)
    out["hl_alert"] = series["cases"].astype(float).values > out["hl_threshold"].values
    return out


def detect_disease(df: pd.DataFrame, params: dict = DETECTION) -> pd.DataFrame:
    """Run both methods on one disease's weekly series."""
    df = df.sort_values("week_start").reset_index(drop=True)
    c2 = ears_c2(df["cases"], baseline=params["ears_baseline_weeks"],
                 threshold=params["ears_threshold"], sd_floor=params["sd_floor"])
    hl = historical_limits(df[["week_start", "cases"]], years=params["hist_years"],
                           half_window=params["hist_half_window"], z=params["hist_z"],
                           sd_floor=params["sd_floor"],
                           exclude_years=params["exclude_baseline_years"])
    out = pd.concat([df, c2, hl], axis=1)
    big_enough = out["cases"] >= params["min_cases"]
    out["c2_alert"] = out["c2_alert"] & big_enough
    out["hl_alert"] = out["hl_alert"] & big_enough
    # The seasonal method is the primary signal. EARS C2 fires on every steep
    # seasonal upswing of common diseases, so it only counts where there is not
    # yet enough history for a seasonal baseline (new or rare diseases).
    no_baseline = out["hl_threshold"].isna()
    out["any_alert"] = out["hl_alert"] | (out["c2_alert"] & no_baseline)
    return out


def detect_all(weekly: pd.DataFrame, params: dict = DETECTION) -> pd.DataFrame:
    """Run detection for every disease in a tidy weekly table."""
    results = [detect_disease(grp, params) for _, grp in weekly.groupby("disease")]
    out = pd.concat(results, ignore_index=True)
    num = ["c2_expected", "c2_threshold", "c2_stat", "hl_expected", "hl_threshold"]
    out[num] = out[num].round(2)
    return out


def recent_alerts(results: pd.DataFrame, weeks: int = 8) -> pd.DataFrame:
    """Alerts in the last `weeks` weeks of data, most recent first."""
    cutoff = results["week_start"].max() - pd.Timedelta(weeks=weeks - 1)
    cols = ["disease", "year", "week", "week_start", "cases", "c2_threshold", "hl_expected",
            "hl_threshold", "c2_alert", "hl_alert"]
    alerts = results.loc[(results["week_start"] >= cutoff) & results["any_alert"], cols]
    return alerts.sort_values(["week_start", "cases"], ascending=[False, False], ignore_index=True)
