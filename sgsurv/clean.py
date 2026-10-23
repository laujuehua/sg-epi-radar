"""Turn raw data.gov.sg downloads into tidy weekly tables."""

from __future__ import annotations

import re
import warnings
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .config import HAZE_THRESHOLD, PSI_BANDS

# --------------------------------------------------------------------------
# Epidemiological weeks
# --------------------------------------------------------------------------
# MOH epi weeks run Sunday-Saturday. We number them with the MMWR convention:
# week 1 is the first Sunday-Saturday week with at least 4 days in the new
# year. Check a few dates against the MOH bulletin PDFs before relying on
# exact dates.

_EPI_WEEK_RE = re.compile(r"^\s*(\d{4})\s*-?\s*W?\s*(\d{1,2})\s*$", re.IGNORECASE)


def epi_week_one_start(year: int) -> date:
    """Sunday on which epi week 1 of `year` starts."""
    jan1 = date(year, 1, 1)
    days_since_sunday = (jan1.weekday() + 1) % 7  # Monday=0 in Python -> Sunday=0
    sunday_before = jan1 - timedelta(days=days_since_sunday)
    # If Jan 1 falls Sun-Wed, the week containing it is week 1;
    # otherwise week 1 starts the following Sunday.
    return sunday_before if days_since_sunday <= 3 else sunday_before + timedelta(days=7)


def epi_week_start(year: int, week: int) -> date:
    return epi_week_one_start(year) + timedelta(weeks=week - 1)


def parse_epi_week(label: str) -> tuple[int, int]:
    """'2012-W01' -> (2012, 1). Also accepts '2012-01' and '2012W1'."""
    match = _EPI_WEEK_RE.match(str(label))
    if not match:
        raise ValueError(f"Unrecognised epi week label: {label!r}")
    return int(match.group(1)), int(match.group(2))


def to_week_start(dates: pd.Series) -> pd.Series:
    """Map any date to the Sunday that starts its Sunday-Saturday week."""
    dates = pd.to_datetime(dates)
    return (dates - pd.to_timedelta((dates.dt.dayofweek + 1) % 7, unit="D")).dt.normalize()


# --------------------------------------------------------------------------
# Column helpers
# --------------------------------------------------------------------------

def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Lower-case column names and map variants onto epi_week/disease/cases."""
    rename = {}
    for col in df.columns:
        key = re.sub(r"[^a-z0-9]+", "_", col.strip().lower()).strip("_")
        if "week" in key:
            rename[col] = "epi_week"
        elif "disease" in key:
            rename[col] = "disease"
        elif "case" in key or key in {"number", "value"}:
            rename[col] = "cases"
        else:
            rename[col] = key
    return df.rename(columns=rename)


def _to_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.astype(str).str.replace(",", "").str.strip(), errors="coerce")


# --------------------------------------------------------------------------
# Disease names
# --------------------------------------------------------------------------
# data.gov.sg (2012-2022) and CDA's Excel files (2023 on) name some diseases
# differently. Everything is mapped onto CDA's current names. Matching ignores
# case, spaces and punctuation. Unlisted names are kept as they are; check
# data/processed/disease_names.csv after a run for diseases that appear in
# only one source, and add their variants here.

_ALIASES = {
    "Dengue": ["Dengue Fever", "Dengue"],
    "DHF": ["Dengue Haemorrhagic Fever", "Dengue Hemorrhagic Fever", "DHF"],
    "Campylobacter enteritis": ["Campylobacter enterosis", "Campylobacterenterosis",
                                "Campylobacter enteritis"],
    "Acute Viral Hepatitis A": ["Viral Hepatitis A", "Acute Viral Hepatitis A"],
    "Acute Viral Hepatitis B": ["Viral Hepatitis B", "Acute Viral Hepatitis B"],
    "Acute Viral Hepatitis C": ["Viral Hepatitis C", "Acute Viral Hepatitis C"],
    "Acute Viral Hepatitis E": ["Viral Hepatitis E", "Acute Viral Hepatitis E"],
    "Salmonellosis (non-enteric fevers)": ["Salmonellosis (non-enteric fevers)",
                                           "Salmonellosis(non-enteric fevers)"],
    "Chikungunya": ["Chikungunya Fever", "Chikungunya"],
    "Zika": ["Zika Virus Infection", "Zika"],
    "Ebola Virus Disease": ["Ebola", "Ebola Virus Disease"],
    "Mpox": ["Monkeypox", "Mpox"],
    "Middle East Respiratory Syndrome": ["MERS", "Middle East Respiratory Syndrome"],
    "HFMD": ["Hand, Foot Mouth Disease", "Hand, Foot and Mouth Disease", "HFMD"],
    "Haemophilus influenzae type b": ["Haemophilus influenzae type b", "Hib"],
    "Nipah": ["Nipah virus infection", "Nipah"],
    # "Encephalitis" (data.gov.sg, to 2022) is not merged into "Japanese
    # Encephalitis": it is a separate, broader category that CDA no longer lists.
}


def _name_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


_ALIAS_LOOKUP = {_name_key(v): canon for canon, variants in _ALIASES.items() for v in variants}


def harmonise_disease(name: str) -> str:
    """Map a disease name onto the CDA naming used throughout the project."""
    cleaned = re.sub(r"\s+", " ", str(name)).strip()
    return _ALIAS_LOOKUP.get(_name_key(cleaned), cleaned)


# --------------------------------------------------------------------------
# CDA yearly Excel files (2023 onwards)
# --------------------------------------------------------------------------
# Layout (checked on 2023-2026 files): row 0 holds group headers
# ("Total Number" = notifications, "Average Daily Number" = polyclinic
# attendances), row 1 holds disease names; columns 0 and 1 are the epi week
# and "dd/mm/yyyy - dd/mm/yyyy". Future weeks in the current year are blank.

_GROUPS = {"totalnumber": "bulletin", "averagedailynumber": "polyclinic"}


def read_cda_excel(path) -> dict[str, pd.DataFrame]:
    """One CDA yearly file -> {'bulletin': df, 'polyclinic': df}.

    Both frames use the data.gov.sg layout (epi_week, disease, no._of_cases)
    so they can be stacked onto the older data and cleaned the same way.
    """
    sheet = pd.read_excel(path, sheet_name=0, header=None)
    groups = sheet.iloc[0].ffill()
    names = sheet.iloc[1]
    body = sheet.iloc[2:].reset_index(drop=True)

    week = pd.to_numeric(body[0], errors="coerce")
    first_day = pd.to_datetime(body[1].astype(str).str.split("-").str[0].str.strip(),
                               dayfirst=True, errors="coerce")
    value_cols = [c for c in sheet.columns if _GROUPS.get(_name_key(groups[c]))]
    has_data = body[value_cols].notna().any(axis=1) & week.notna()
    body, week, first_day = body[has_data], week[has_data].astype(int), first_day[has_data]
    if body.empty:
        raise ValueError(f"No data rows in {path}")

    # The year is the one that contains the end of epi week 1
    year = (first_day[week == 1].iloc[0] + pd.Timedelta(days=6)).year
    expected = pd.to_datetime([epi_week_start(year, w) for w in week])
    mismatched = (expected != first_day.values).sum()
    if mismatched:
        print(f"  warning: {mismatched} week start date(s) in {path} differ from the epi-week rule")

    out = {}
    for group in ("bulletin", "polyclinic"):
        cols = [c for c in value_cols if _GROUPS[_name_key(groups[c])] == group]
        long = body[cols].set_axis([names[c] for c in cols], axis=1)
        long.insert(0, "epi_week", [f"{year}-W{w:02d}" for w in week])
        long = long.melt(id_vars="epi_week", var_name="disease", value_name="no._of_cases")
        out[group] = long.dropna(subset=["no._of_cases"])
    return out


def find_cda_files(*folders) -> list:
    """Excel files in the given folders (Excel lock files '~$...' skipped)."""
    files = []
    for folder in folders:
        if folder.exists():
            files += sorted([p for p in folder.glob("*.xls*") if not p.name.startswith("~$")],
                            key=lambda p: (-p.stat().st_mtime_ns, p.name))
    # First folder is authoritative (pipeline passes the downloaded cda/ first).
    return list(dict.fromkeys(files))


def combine_sources(old: pd.DataFrame | None, new: list[pd.DataFrame]) -> pd.DataFrame:
    """Stack data.gov.sg and CDA rows; where both cover a week, keep CDA."""
    frames = []
    if new:
        cda = pd.concat(new, ignore_index=True).assign(source="CDA")
        frames.append(cda)
    if old is not None:
        old = _normalise_columns(old).rename(columns={"cases": "no._of_cases"})
        frames.append(old[["epi_week", "disease", "no._of_cases"]].assign(source="data.gov.sg"))
    if not frames:
        raise FileNotFoundError("No bulletin data found in data/raw")
    allrows = pd.concat(frames, ignore_index=True)
    allrows["_key"] = allrows["disease"].map(harmonise_disease) + "|" + \
        allrows["epi_week"].map(lambda s: "%d-%02d" % parse_epi_week(s))
    conflicts = allrows.assign(_value=_to_number(allrows["no._of_cases"])).groupby("_key")["_value"].nunique()
    conflicts = conflicts[conflicts > 1]
    if len(conflicts):
        warnings.warn(f"{len(conflicts)} conflicting disease-weeks; using first source in priority order: "
                      + ", ".join(conflicts.index[:5]), UserWarning)
    return allrows.drop_duplicates("_key", keep="first").drop(columns="_key")


def disease_name_report(combined: pd.DataFrame) -> pd.DataFrame:
    """Which source(s) each harmonised disease name appears in, and when."""
    df = combined.assign(disease=combined["disease"].map(harmonise_disease),
                         year=combined["epi_week"].map(lambda s: parse_epi_week(s)[0]))
    report = df.groupby("disease").agg(
        sources=("source", lambda s: " + ".join(sorted(set(s)))),
        first_year=("year", "min"), last_year=("year", "max"),
    ).reset_index()
    return report.sort_values(["sources", "disease"], ignore_index=True)


# --------------------------------------------------------------------------
# Disease tables (bulletin and polyclinic share the same layout)
# --------------------------------------------------------------------------

def clean_weekly_disease(raw: pd.DataFrame) -> pd.DataFrame:
    """Tidy a MOH weekly table -> disease, year, week, week_start, cases.

    Weeks with no row for a disease remain missing within its reporting
    period (first to last week it appears), and are flagged.
    """
    df = _normalise_columns(raw)
    missing = {"epi_week", "disease", "cases"} - set(df.columns)
    if missing:
        raise KeyError(f"Missing columns after normalising: {missing}")

    df["disease"] = df["disease"].map(harmonise_disease)
    yw = df["epi_week"].map(parse_epi_week)
    df["year"] = [y for y, _ in yw]
    df["week"] = [w for _, w in yw]
    df["week_start"] = pd.to_datetime([epi_week_start(y, w) for y, w in yw])
    df["cases"] = _to_number(df["cases"])

    df = (
        df.groupby(["disease", "week_start", "year", "week"], as_index=False)["cases"]
        .sum(min_count=1)
    )

    # Fill gaps inside each disease's reporting period
    filled = []
    for disease, grp in df.groupby("disease"):
        full = pd.date_range(grp["week_start"].min(), grp["week_start"].max(), freq="7D")
        grp = grp.set_index("week_start").reindex(full)
        grp.index.name = "week_start"
        grp["missing_observation"] = grp["cases"].isna()
        grp["imputed_zero"] = False  # retained for older consumers; no zeros are imputed
        grp["disease"] = disease
        filled.append(grp.reset_index())
    out = pd.concat(filled, ignore_index=True)

    # Recompute year/week labels for filled rows from the date
    out["year"], out["week"] = zip(*out["week_start"].map(_date_to_epi_week))
    return out[["disease", "year", "week", "week_start", "cases", "imputed_zero", "missing_observation"]].sort_values(
        ["disease", "week_start"], ignore_index=True
    )


def _date_to_epi_week(ts: pd.Timestamp) -> tuple[int, int]:
    d = ts.date()
    year = d.year + 1
    while epi_week_one_start(year) > d:
        year -= 1
    return year, (d - epi_week_one_start(year)).days // 7 + 1


# --------------------------------------------------------------------------
# PSI
# --------------------------------------------------------------------------

REGIONS = ["north", "south", "east", "west", "central"]


def psi_band(value: float) -> str:
    if pd.isna(value):
        return "No data"
    for low, high, label in PSI_BANDS:
        if low <= value <= high:
            return label
    return "Hazardous"


def parse_timestamps(values: pd.Series) -> pd.Series:
    """Parse ISO ('2014-04-01 01:00') or day-first ('1/4/2014 1:00') timestamps.

    Day-first parsing must not be applied to ISO strings, or 2014-04-01 would
    become 4 January. ISO strings with a UTC offset are converted to
    Singapore time; naive ones are taken as Singapore time already.
    """
    values = values.astype(str).str.strip()
    iso = values.str.match(r"^\d{4}-")
    has_offset = iso & values.str.contains(r"(?:Z|[+-]\d{2}:?\d{2})$", regex=True)
    out = pd.Series(pd.NaT, index=values.index, dtype="datetime64[ns]")
    if has_offset.any():
        parsed = pd.to_datetime(values[has_offset], format="ISO8601", utc=True, errors="coerce")
        out[has_offset] = parsed.dt.tz_convert("Asia/Singapore").dt.tz_localize(None)
    naive_iso = iso & ~has_offset
    if naive_iso.any():
        out[naive_iso] = pd.to_datetime(values[naive_iso], format="ISO8601", errors="coerce")
    if (~iso).any():
        out[~iso] = pd.to_datetime(values[~iso], dayfirst=True, format="mixed", errors="coerce")
    return out


def clean_psi_hourly(raw: pd.DataFrame) -> pd.DataFrame:
    """Hourly regional 24-hr PSI -> timestamp, regions, national (max of regions)."""
    df = raw.copy()
    df.columns = [re.sub(r"[^a-z0-9]+", "_", c.strip().lower()).strip("_") for c in df.columns]
    # The timestamp column is named '24hr_psi' in the NEA dataset
    time_col = next(c for c in df.columns if c not in REGIONS)
    df["timestamp"] = parse_timestamps(df[time_col])
    for region in REGIONS:
        df[region] = _to_number(df[region])
    df = df.dropna(subset=["timestamp"])
    df["national"] = df[REGIONS].max(axis=1)
    return df[["timestamp", *REGIONS, "national"]].sort_values("timestamp", ignore_index=True)


def psi_from_daily_peaks(daily: pd.DataFrame) -> pd.DataFrame:
    """Keep the dashboard's mean-of-daily-peaks definition for refreshed context."""
    daily=daily.copy()
    daily["date"]=pd.to_datetime(daily.date)
    daily["week_start"]=to_week_start(daily.date)
    out=daily.groupby("week_start").agg(psi_mean=("psi_daily_max","mean"),psi_max=("psi_daily_max","max"),
        days_unhealthy=("psi_daily_max",lambda s:int(s.gt(HAZE_THRESHOLD).sum())),days_with_data=("psi_daily_max","count")).reset_index()
    out.psi_mean=out.psi_mean.round(1)
    out["band"]=out.psi_max.map(psi_band)
    out["haze_week"]=out.psi_max.gt(HAZE_THRESHOLD)
    return out


def psi_weekly(hourly: pd.DataFrame) -> pd.DataFrame:
    """Aggregate hourly PSI to Sunday-start weeks."""
    daily = (
        hourly.assign(date=hourly["timestamp"].dt.normalize())
        .groupby("date", as_index=False)["national"]
        .max()
    )
    daily["week_start"] = to_week_start(daily["date"])
    weekly = daily.groupby("week_start").agg(
        psi_mean=("national", "mean"),
        psi_max=("national", "max"),
        days_unhealthy=("national", lambda s: int((s > HAZE_THRESHOLD).sum())),
        days_with_data=("national", "count"),
    ).reset_index()
    weekly["psi_mean"] = weekly["psi_mean"].round(1)
    weekly["band"] = weekly["psi_max"].map(psi_band)
    weekly["haze_week"] = weekly["psi_max"] > HAZE_THRESHOLD
    return weekly


def join_psi_respiratory(psi_wk: pd.DataFrame, poly: pd.DataFrame, disease: str) -> pd.DataFrame:
    """Weekly PSI joined to one polyclinic series (average daily attendances)."""
    resp = poly.loc[poly["disease"] == disease, ["week_start", "cases"]].rename(
        columns={"cases": "attendances"}
    )
    return psi_wk.merge(resp, on="week_start", how="inner").sort_values("week_start", ignore_index=True)


def lagged_correlations(joined: pd.DataFrame, max_lag: int = 3) -> pd.DataFrame:
    """Spearman correlation of attendances with PSI 0..max_lag weeks earlier.

    Exploratory only: both series are seasonal, so this is not a causal estimate.
    """
    joined = joined.set_index("week_start").asfreq("7D").reset_index()
    rows = []
    for lag in range(max_lag + 1):
        complete = joined["days_with_data"].eq(7) if "days_with_data" in joined else pd.Series(True, index=joined.index)
        x = joined["psi_mean"].where(complete).shift(lag)
        ok = x.notna() & joined["attendances"].notna() & complete
        rho = x[ok].rank().corr(joined.loc[ok, "attendances"].rank()) if ok.sum() > 3 else np.nan
        rows.append({"lag_weeks": lag, "spearman_rho": round(rho, 3), "n_weeks": int(ok.sum())})
    return pd.DataFrame(rows)
