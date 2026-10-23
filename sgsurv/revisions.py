"""Track observed case revisions between locally retained processing snapshots."""
import pandas as pd


def case_changes(previous, current):
    keys = ["disease", "week_start"]
    old = previous[keys + ["cases"]].copy()
    new = current[keys + ["cases"]].copy()
    for data in (old, new):
        data["week_start"] = pd.to_datetime(data.week_start)
        if data.duplicated(keys).any():
            raise ValueError("Cannot track revisions with duplicate disease-weeks")
    merged = old.merge(new, on=keys, suffixes=("_previous", "_current"), how="outer", indicator=True)
    matched = merged["_merge"].eq("both")
    same = merged.cases_previous.eq(merged.cases_current) | (merged.cases_previous.isna() & merged.cases_current.isna())
    changed = merged[matched & ~same].sort_values(keys)
    records = []
    for row in changed.itertuples():
        a = None if pd.isna(row.cases_previous) else float(row.cases_previous)
        b = None if pd.isna(row.cases_current) else float(row.cases_current)
        records.append(dict(disease=row.disease, week_start=row.week_start.strftime("%Y-%m-%d"),
                            previous_cases=a, current_cases=b, change=None if a is None or b is None else b-a))
    return dict(changes=records, added_rows=int(merged["_merge"].eq("right_only").sum()),
                removed_rows=int(merged["_merge"].eq("left_only").sum()))


def record_snapshot(history, previous, current, snapshot_id, run_at, previous_id=None):
    history = history or {"started_at":run_at, "updates":[]}
    if history["updates"] and history["updates"][-1]["snapshot_id"] == snapshot_id:
        return history
    comparison = case_changes(previous, current) if previous is not None else dict(changes=[], added_rows=0, removed_rows=0)
    history["updates"].append(dict(run_at=run_at, snapshot_id=snapshot_id, previous_snapshot_id=previous_id,
                                   comparison_available=previous is not None, **comparison))
    return history
