"""Run the full pipeline: fetch -> clean -> detect -> write data/processed/.

Usage (from the project folder, with the virtual environment active):
    python -m sgsurv.pipeline              # download fresh data (data.gov.sg + CDA), then process
    python -m sgsurv.pipeline --skip-fetch # reuse files already in data/raw/
    python -m sgsurv.pipeline --ai         # also draft an AI situation summary
"""

from __future__ import annotations

import argparse
import json
import hashlib
from datetime import datetime, timezone

import pandas as pd

from datetime import date

from . import ai_summary, clean, detect, fetch, fetch_cda
from .config import PROCESSED_DIR, RAW_DIR, RESPIRATORY_DISEASE
from .validate import validate
from .revisions import record_snapshot


def run(skip_fetch: bool = False, ai: bool = False) -> None:
    if not skip_fetch:
        fetch.fetch_all()                                          # data.gov.sg: 2012-2022 + PSI
        fetch_cda.fetch_all(list(range(2023, date.today().year + 1)))  # CDA: 2023 onwards

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    meta_path = PROCESSED_DIR / "metadata.json"
    previous = json.loads(meta_path.read_text()) if meta_path.exists() else None
    previous_path = PROCESSED_DIR / "bulletin_detection.csv"
    previous_results = pd.read_csv(previous_path, parse_dates=["week_start"]) if previous_path.exists() else None

    def read(name):
        path = RAW_DIR / f"{name}.csv"
        if path.exists():
            return pd.read_csv(path, dtype=str)
        print(f"  {path.name} not found; continuing without it")
        return None

    # CDA yearly Excel files (2023 onwards), from data/raw/cda/ or data/raw/
    cda = {"bulletin": [], "polyclinic": []}
    source_files = clean.find_cda_files(RAW_DIR / "cda", RAW_DIR)
    for path in source_files:
        print(f"Reading CDA file {path.name}")
        for group, frame in clean.read_cda_excel(path).items():
            cda[group].append(frame)

    bulletin_raw = clean.combine_sources(read("bulletin"), cda["bulletin"])
    poly_raw = clean.combine_sources(read("polyclinic"), cda["polyclinic"])
    names = pd.concat([clean.disease_name_report(bulletin_raw).assign(table="bulletin"),
                       clean.disease_name_report(poly_raw).assign(table="polyclinic")])
    single = names[(names["table"] == "bulletin") & ~names["sources"].str.contains(r"\+")
                   & (names["first_year"] <= 2022) & (names["last_year"] >= 2022)]
    if len(single):
        print("Check names: these bulletin diseases stop at 2022 (renamed or dropped by CDA?):")
        print("  " + ", ".join(single["disease"]))

    print("Cleaning bulletin ...")
    bulletin = clean.clean_weekly_disease(bulletin_raw)
    print("Running aberration detection ...")
    results = detect.detect_all(bulletin)
    alerts = detect.recent_alerts(results)

    print("Cleaning polyclinic attendances and PSI ...")
    poly = clean.clean_weekly_disease(poly_raw)
    psi_raw = read("psi")
    if psi_raw is None:
        raise FileNotFoundError("data/raw/psi.csv is needed; run without --skip-fetch first")
    hourly=clean.clean_psi_hourly(psi_raw)
    psi_observed_through=hourly.timestamp.max().date().isoformat()
    psi_wk = clean.psi_weekly(hourly)
    context_daily=PROCESSED_DIR.parent / "extra" / "processed" / "psi_daily.csv"
    context_notes=[]
    if context_daily.exists():
        daily=pd.read_csv(context_daily,parse_dates=["date"])
        if daily.date.max() >= psi_wk.week_start.max()+pd.Timedelta(days=6):
            psi_observed_through=daily.date.max().date().isoformat()
            psi_wk=clean.psi_from_daily_peaks(daily)
            context_notes=["PSI weekly charts include supplementary historical and real-time observations; mean remains the mean of daily peaks. Partial hourly days remain provisional."]
    quality_notes = validate(results, psi_wk, previous)+context_notes
    names.to_csv(PROCESSED_DIR / "disease_names.csv", index=False)
    poly.to_csv(PROCESSED_DIR / "polyclinic_weekly.csv", index=False)
    results.to_csv(PROCESSED_DIR / "bulletin_detection.csv", index=False)
    alerts.to_csv(PROCESSED_DIR / "recent_alerts.csv", index=False)
    psi_wk.to_csv(PROCESSED_DIR / "psi_weekly.csv", index=False)
    joined = clean.join_psi_respiratory(psi_wk, poly, RESPIRATORY_DISEASE)
    joined.to_csv(PROCESSED_DIR / "psi_respiratory.csv", index=False)
    clean.lagged_correlations(joined).to_csv(PROCESSED_DIR / "psi_lag_correlation.csv", index=False)

    data_through = results["week_start"].max()
    meta = {
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bulletin_through": str(data_through.date()),
        "psi_through": str(psi_wk["week_start"].max().date()),
        "psi_observed_through": psi_observed_through,
        "n_diseases": int(results["disease"].nunique()),
        "n_recent_alerts": int(len(alerts)),
        "n_current_diseases": int(results.loc[results.week_start.eq(data_through) & results.cases.notna(), "disease"].nunique()),
        "quality_notes": quality_notes,
        "source_priority": [str(p.relative_to(RAW_DIR)) for p in source_files],
        "snapshot_id": hashlib.sha256((results.to_csv(index=False) + psi_wk.to_csv(index=False)).encode()).hexdigest(),
    }
    (PROCESSED_DIR / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    revision_path = PROCESSED_DIR / "revision_history.json"
    history = json.loads(revision_path.read_text(encoding="utf-8")) if revision_path.exists() else None
    history = record_snapshot(history, previous_results, results, meta["snapshot_id"], meta["run_at"],
                              previous.get("snapshot_id") if previous else None)
    revision_path.write_text(json.dumps(history, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(meta, indent=2))

    summary_meta = PROCESSED_DIR / "ai_summary.json"
    ai_summary.prune_stale_summary(meta["snapshot_id"], PROCESSED_DIR / "ai_summary.md")
    if ai:
        psi_recent = psi_wk[psi_wk["week_start"] > data_through - pd.Timedelta(weeks=8)]
        psi_recent = psi_recent[psi_recent["week_start"] <= data_through]
        context = ai_summary.build_context(alerts, psi_recent, str(data_through.date()))
        try:
            written = ai_summary.write_summary(context)
            if written:
                summary_meta.write_text(json.dumps({"snapshot_id": meta["snapshot_id"]}), encoding="utf-8")
        except Exception as err:
            print(f"Optional AI summary unavailable: {type(err).__name__}; computed summary remains available")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--skip-fetch", action="store_true", help="use existing data/raw files")
    parser.add_argument("--ai", action="store_true", help="draft an AI summary (needs ANTHROPIC_API_KEY)")
    args = parser.parse_args()
    run(skip_fetch=args.skip_fetch, ai=args.ai)


if __name__ == "__main__":
    main()
