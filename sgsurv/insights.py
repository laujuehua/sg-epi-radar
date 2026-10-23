"""Interpretation helpers; these do not change the detection thresholds."""
import pandas as pd


def signal_episodes(frame):
    out = frame.sort_values(["disease", "week_start"]).copy()
    runs, starts, states = [], [], []
    disease, previous_date, length, start = None, None, 0, None
    for row in out.itertuples():
        consecutive = row.disease == disease and previous_date is not None and row.week_start - previous_date == pd.Timedelta(weeks=1)
        if not consecutive:
            length, start = 0, None
        if pd.notna(row.cases) and row.any_alert:
            length += 1
            if length == 1:
                start = row.week_start
            state = "New signal" if length == 1 else "Continuing signal"
        else:
            length, start = 0, None
            state = "Unavailable" if pd.isna(row.cases) else "No signal"
        runs.append(length)
        starts.append(start)
        states.append(state)
        disease, previous_date = row.disease, row.week_start
    out["signal_run_weeks"] = runs
    out["episode_start"] = pd.to_datetime(starts)
    out["signal_state"] = states
    return out


def seasonal_comparison(frame, disease, max_years=6):
    """Use epidemiological year/week labels, retaining missing observations."""
    data = frame[frame.disease.eq(disease)].copy()
    years = sorted(data.year.unique())[-max_years:]
    return data[data.year.isin(years)].sort_values(["year", "week"])
