"""Publication checks shared by the pipeline and CI."""
import json
from pathlib import Path

import pandas as pd


def validate(results, psi, previous=None):
    if results.empty or psi.empty:
        raise ValueError("Bulletin and PSI tables must contain observations")
    if results.duplicated(["disease", "week_start"]).any():
        raise ValueError("Duplicate disease-weeks")
    if psi.duplicated("week_start").any():
        raise ValueError("Duplicate PSI weeks")
    if results["cases"].dropna().lt(0).any():
        raise ValueError("Negative case counts")
    if not psi["days_with_data"].between(1, 7).all():
        raise ValueError("Invalid PSI coverage")
    latest = results.week_start.max()
    active = results.loc[results.week_start.eq(latest) & results.cases.notna(), "disease"].nunique()
    if not active:
        raise ValueError("No reported diseases in the latest week")
    if previous:
        for key, current in [("bulletin_through", latest), ("psi_through", psi.week_start.max())]:
            if current < pd.Timestamp(previous[key]):
                raise ValueError(f"Coverage regressed: {key}")
        if active < previous.get("n_current_diseases", active) * .9:
            raise ValueError("Latest-week disease coverage fell by more than 10%")
    notes = []
    incomplete = int(psi.days_with_data.lt(7).sum())
    if incomplete:
        notes.append(f"{incomplete} PSI weeks have fewer than 7 days; excluded from correlations.")
    missing = int(results.cases.isna().sum())
    if missing:
        notes.append(f"{missing} disease-week observations are unavailable; not treated as zero.")
    return notes


def main():
    folder = Path(__file__).resolve().parents[1] / "data" / "processed"
    results = pd.read_csv(folder / "bulletin_detection.csv", parse_dates=["week_start"])
    psi = pd.read_csv(folder / "psi_weekly.csv", parse_dates=["week_start"])
    meta = json.loads((folder / "metadata.json").read_text())
    print("Publication checks passed", validate(results, psi, meta))


if __name__ == "__main__":
    main()
