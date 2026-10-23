"""Retrospective comparisons with explicitly defined, sourced event windows."""
import pandas as pd


METHODS = {"Combined rule": ("any_alert", None), "Seasonal": ("hl_alert", "hl_threshold"),
           "EARS C2": ("c2_alert", "c2_threshold")}


def evaluate_events(results, events):
    rows = []
    for event in events:
        anchor = pd.Timestamp(event["anchor_week"])
        weeks = int(event["window_weeks"])
        calendar = pd.date_range(anchor, periods=weeks, freq="7D")
        disease = results[results.disease.eq(event["disease"])].set_index("week_start").sort_index()
        if disease.index.duplicated().any():
            raise ValueError("Duplicate disease-weeks in evaluation")
        window = disease.reindex(calendar)
        for method, (flag, threshold) in METHODS.items():
            baseline = window[threshold].notna() if threshold else (window.hl_threshold.notna() | window.c2_threshold.notna())
            observed = window.cases.notna() & baseline
            signals = window[observed & window[flag].fillna(False).astype(bool)]
            fully_observed = bool(observed.all())
            status = "Signal in window" if len(signals) else ("No signal in window" if fully_observed else "Insufficient coverage")
            first = signals.index.min() if len(signals) else None
            year = disease[disease.index.year == anchor.year]
            eligible = year.cases.notna() & (year[threshold].notna() if threshold else (year.hl_threshold.notna() | year.c2_threshold.notna()))
            outside = ~year.index.isin(calendar)
            rows.append(dict(event=event["event"], disease=event["disease"], method=method,
                anchor_week=str(anchor.date()), window_end=str((calendar[-1]+pd.Timedelta(days=6)).date()),
                evaluable_weeks=int(observed.sum()), window_weeks=weeks, status=status,
                first_signal_week=None if first is None else str(first.date()),
                weeks_after_anchor=None if first is None else int((first-anchor).days//7),
                signal_weeks=int(len(signals)),
                unclassified_signals_outside_window=int((year[flag].fillna(False).astype(bool) & eligible & outside).sum()),
                evaluable_weeks_outside_window=int((eligible & outside).sum())))
    return pd.DataFrame(rows)
