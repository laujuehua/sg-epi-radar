"""Refresh/rebuild the full supplementary data library, independently of dashboard selection."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .extra_sources import EXTRA, IMPORTED, REFERENCE, DATA_GOV
from .import_data import import_project, sha256
from . import extra_fetch, extra_clean


DESCRIPTIONS = {
    "weekly_notifications": ("Weekly disease notifications","Surveillance","Notified cases per week","Dates use Singapore epidemiological weeks; unavailable counts remain missing."),
    "polyclinic_attendances": ("Polyclinic attendances","Surveillance","Average attendances per day","Attendances are daily averages within each reporting week, not weekly totals."),
    "psi_daily": ("Daily PSI","Environment","PSI index","Maximum is the daily peak across hourly regional maxima; mean averages hourly regional means. Partial days are flagged by hour counts."),
    "weather_daily": ("Changi daily weather","Environment","Rainfall mm; temperature °C","One station (Changi S24); unavailable observations remain missing."),
    "relative_humidity_monthly": ("Monthly relative humidity","Environment","Relative humidity %","Monthly Changi mean; not daily humidity."),
    "weekly_covariates": ("Weekly environment and calendar context","Context","Mixed units; see columns","PSI mean uses regional means, unlike the main dashboard's mean of daily peak PSI. Calendar coverage is explicit; no future school dates are invented."),
    "population_by_age": ("Population by age","Population","People; resident share 0–1","Resident age groups and total population have different denominators. Repeated total-population columns must not be summed over ages."),
    "contact_matrix_singapore": ("Singapore contact matrices","Contacts","Contacts per person per day","Prem et al. synthetic matrices, 16 age groups and five settings. Rows and columns are age groups; these are modelled estimates."),
    "school_holidays": ("School calendar","Calendar","Dated periods","Curated reference snapshot through 2026; some extra holidays apply specifically to primary schools. New years require review."),
    "public_holidays": ("Public holidays","Calendar","Dates","MOM current data plus curated legacy dates and two documented observed-day reconciliations."),
    "vaccination_coverage": ("Influenza vaccination survey coverage","Vaccination","Self-reported coverage %","Curated NPHS values for specific age groups and survey years. No interpolation or extrapolation; new releases require review."),
    "visitor_arrivals_monthly": ("Monthly visitor arrivals","Travel","Arrivals per month","Totals, regions and countries overlap; do not sum across hierarchy levels."),
    "deaths_respiratory": ("Respiratory deaths","Mortality","Deaths by year and age","Annual all-age totals and age-specific strata overlap. Influenza and pneumonia are separate ICD categories."),
    "deaths_monthly": ("Monthly total deaths","Mortality","Deaths per month","All causes; not a direct influenza-attributable mortality estimate."),
    "deaths_rates_annual": ("Annual deaths and death-rate series","Mortality","Series-specific counts/rates","Preserves the original series labels; rates and counts have different units."),
    "flunet_weekly_by_source": ("FluNet by country and reporting source","Influenza","Tested and positive specimens","Keeps sentinel/non-sentinel/undefined reporting sources separate. Positives are specimens, not all population infections."),
    "flunet_singapore_sentinel": ("Singapore sentinel influenza","Influenza","Tested and positive specimens; positivity %","Consistent SENTINEL source only; positivity is unavailable when the tested denominator is zero or missing."),
    "flunet_southeast_asia_weekly": ("Neighbouring-country influenza","Influenza","Specimens aggregated across reported sources","Source totals are combined as in the extracted recipe; source composition can change and country ascertainment differs."),
    "southeast_asia_tb_annual": ("Southeast Asia annual TB incidence","Regional health","Estimated incident cases per 100,000 population per year","WHO Global Tuberculosis Report via World Bank WDI, indicator SH.TBS.INCD (CC BY 4.0). Modelled annual estimates, not weekly case notifications. Missing estimates remain missing."),
}


def coverage(frame):
    if "incidence_per_100000" in frame:
        frame=frame[pd.to_numeric(frame.incidence_per_100000,errors="coerce").notna()]
    for key in ["week_start","date","month","start_date","year"]:
        if key not in frame:
            continue
        values=frame[key].dropna()
        if key=="year":
            values=pd.to_numeric(values,errors="coerce").dropna()
            return (str(int(values.min())),str(int(values.max()))) if len(values) else (None,None)
        values=pd.to_datetime(values,errors="coerce").dropna()
        if len(values):
            last=pd.to_datetime(frame.end_date,errors="coerce").max() if key=="start_date" and "end_date" in frame else values.max()
            return str(values.min().date()),str(last.date())
    return None,None


def catalog(tables, base=EXTRA):
    status_file=base / "refresh_status.json"
    refresh=json.loads(status_file.read_text(encoding="utf-8")) if status_file.exists() else None
    datasets=[]
    for key,frame in tables.items():
        title,family,units,note=DESCRIPTIONS[key]
        start,through=coverage(frame)
        path=base / "processed" / f"{key}.csv"
        datasets.append(dict(id=key,title=title,family=family,units=units,note=note,rows=len(frame),
                             columns=list(frame.columns),missing_values={c:int(frame[c].isna().sum()) for c in frame},
                             coverage_start=start,coverage_through=through,sha256=sha256(path),
                             curated=key in ["school_holidays","vaccination_coverage"],
                             quality_notes=frame.attrs.get("quality_notes",[]),
                             included_in_dashboard_views=False,path=f"processed/{key}.csv"))
    raw_sources=[dict(id=name,source=f"https://data.gov.sg/datasets/{dataset_id}/view",path=f"raw/{name}.csv") for name,(dataset_id,_) in DATA_GOV.items()]
    previous_catalog=base / "catalog.json"
    imported_files=json.loads(previous_catalog.read_text(encoding="utf-8")).get("imported_files",[]) if previous_catalog.exists() else []
    manifest_path=IMPORTED / "manifest.json"
    if manifest_path.exists():
        manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
        imported_files=manifest["files"]
    result=dict(generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),datasets=datasets,raw_sources=raw_sources,
                refresh=refresh,imported_file_count=len(imported_files),imported_files=imported_files,
                selection_note="All tables are retained. No supplementary table is automatically added to existing analytical views.",
                curated_reference_note="School calendars, legacy holidays and vaccination survey values are retained dated references, not live scraped updates.")
    (base / "catalog.json").write_text(json.dumps(result,indent=2,allow_nan=False),encoding="utf-8")
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--import-from",type=Path,help="One-time read-only import; all subsequent runs use this project's own cache")
    parser.add_argument("--skip-fetch",action="store_true",help="Rebuild from the local cache without network requests")
    parser.add_argument("--fetch-only",action="store_true")
    parser.add_argument("--groups",nargs="+",choices=["data_gov","flunet","psi","weather","contacts","cda","regional"],help="Refresh selected source families")
    args=parser.parse_args()
    if args.import_from:
        result=import_project(args.import_from)
        print(f"Imported {len(result['files'])} verified files; original source unchanged.")
    extra_fetch.seed_cache()
    if not args.skip_fetch:
        extra_fetch.refresh(groups=args.groups)
    if args.fetch_only:
        return
    tables=extra_clean.process()
    result=catalog(tables)
    for item in result["datasets"]:
        print(f"{item['id']}: {item['rows']:,} rows; {item['coverage_start']} to {item['coverage_through']}")
    print(f"Ready: {len(tables)} derived tables, all retained in {EXTRA / 'processed'}.")


if __name__ == "__main__":
    main()
