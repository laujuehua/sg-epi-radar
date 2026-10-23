from datetime import date

import pandas as pd
import pytest

from sgsurv import clean


@pytest.mark.parametrize(
    "year, expected",
    [
        (2012, date(2012, 1, 1)),   # Jan 1 is a Sunday
        (2015, date(2015, 1, 4)),   # Jan 1 is a Thursday -> next Sunday
        (2014, date(2013, 12, 29)), # Jan 1 is a Wednesday -> previous Sunday
        (2022, date(2022, 1, 2)),   # Jan 1 is a Saturday
    ],
)
def test_epi_week_one_start(year, expected):
    assert clean.epi_week_one_start(year) == expected
    assert expected.weekday() == 6  # always a Sunday


@pytest.mark.parametrize("label", ["2012-W01", "2012-01", "2012W1", " 2012-w01 "])
def test_parse_epi_week_variants(label):
    assert clean.parse_epi_week(label) == (2012, 1)


def test_parse_epi_week_rejects_garbage():
    with pytest.raises(ValueError):
        clean.parse_epi_week("week one")


def test_clean_weekly_disease_fills_gaps_and_renames():
    raw = pd.DataFrame({
        "Epidemiological Week": ["2012-W01", "2012-W03", "2012-W01"],
        "Disease": ["Dengue Fever", "Dengue Fever", "  HFMD "],
        "No. of Cases": ["10", "1,200", "5"],
    })
    out = clean.clean_weekly_disease(raw)
    dengue = out[out["disease"] == "Dengue"]  # renamed to the CDA name
    assert dengue["cases"].iloc[0] == 10
    assert pd.isna(dengue["cases"].iloc[1])
    assert dengue["cases"].iloc[2] == 1200
    assert list(dengue["missing_observation"]) == [False, True, False]
    assert not dengue["imputed_zero"].any()
    assert list(dengue["week"]) == [1, 2, 3]
    assert "HFMD" in set(out["disease"])                   # whitespace stripped


def test_psi_weekly_aggregation():
    raw = pd.DataFrame({
        "24hr_psi": ["1/4/2014 1:00", "1/4/2014 2:00", "2/4/2014 1:00"],
        "north": ["50", "120", "40"],
        "south": ["60", "80", "45"],
        "east": ["55", "70", "-"],
        "west": ["52", "90", "41"],
        "central": ["58", "95", "44"],
    })
    hourly = clean.clean_psi_hourly(raw)
    assert hourly["timestamp"].iloc[0] == pd.Timestamp("2014-04-01 01:00")  # day-first
    assert hourly["national"].tolist() == [60, 120, 45]
    weekly = clean.psi_weekly(hourly)
    assert len(weekly) == 1
    assert weekly.loc[0, "week_start"] == pd.Timestamp("2014-03-30")  # Sunday
    assert weekly.loc[0, "psi_max"] == 120
    assert weekly.loc[0, "days_unhealthy"] == 1
    assert bool(weekly.loc[0, "haze_week"])
    assert weekly.loc[0, "band"] == "Unhealthy"


def test_parse_timestamps_iso_and_day_first():
    s = pd.Series(["2014-04-01 01:00:00", "1/4/2014 2:00", "2014-04-01T03:00:00+08:00"])
    out = clean.parse_timestamps(s)
    assert list(out) == [pd.Timestamp("2014-04-01 01:00"), pd.Timestamp("2014-04-01 02:00"),
                         pd.Timestamp("2014-04-01 03:00")]


@pytest.mark.parametrize("name, expected", [
    ("Dengue Fever", "Dengue"),
    ("Dengue ", "Dengue"),
    ("Salmonellosis(non-enteric fevers)", "Salmonellosis (non-enteric fevers)"),
    ("Campylobacter enterosis", "Campylobacter enteritis"),
    ("Mumps  ", "Mumps"),
    ("Nipah virus infection", "Nipah"),
    ("Encephalitis", "Encephalitis"),
    ("Some New Disease", "Some New Disease"),
])
def test_harmonise_disease(name, expected):
    assert clean.harmonise_disease(name) == expected


def _fake_cda_sheet(tmp_path):
    rows = [
        ["Epidemiology Wk", "Start to End", None, "Total Number", None, "Average Daily Number"],
        [None, None, None, "Dengue ", "Typhoid ", "Acute Upper Respiratory Tract infections"],
        [1, "04/01/2026 - 10/01/2026", None, 70, 2, 2747.27],
        [2, "11/01/2026 - 17/01/2026", None, 80, 0, 2500.5],
        [3, "18/01/2026 - 24/01/2026", None, None, None, None],  # future week, blank
    ]
    path = tmp_path / "cda_2026.xlsx"
    pd.DataFrame(rows).to_excel(path, header=False, index=False)
    return path


def test_read_cda_excel_splits_groups_and_drops_blank_weeks(tmp_path):
    out = clean.read_cda_excel(_fake_cda_sheet(tmp_path))
    bulletin, poly = out["bulletin"], out["polyclinic"]
    assert set(bulletin["epi_week"]) == {"2026-W01", "2026-W02"}
    assert set(bulletin["disease"]) == {"Dengue ", "Typhoid "}
    assert list(poly["no._of_cases"]) == [2747.27, 2500.5]


def test_combine_sources_prefers_cda_and_cleans(tmp_path):
    cda = clean.read_cda_excel(_fake_cda_sheet(tmp_path))["bulletin"]
    old = pd.DataFrame({"epi_week": ["2022-W52", "2026-W01"], "disease": ["Dengue Fever"] * 2,
                        "no._of_cases": ["100", "999"]})
    combined = clean.combine_sources(old, [cda])
    tidy = clean.clean_weekly_disease(combined)
    dengue = tidy[tidy["disease"] == "Dengue"].set_index("week_start")["cases"]
    assert dengue[pd.Timestamp("2022-12-25")] == 100   # old source, renamed
    assert dengue[pd.Timestamp("2026-01-04")] == 70    # CDA wins over the duplicate
    report = clean.disease_name_report(combined)
    assert report.set_index("disease").loc["Dengue", "sources"] == "CDA + data.gov.sg"
