"""Project-wide settings: dataset IDs, file paths and detection parameters."""

from pathlib import Path

# Project root = the folder that contains this package
ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"

# data.gov.sg dataset IDs (see README for links)
DATASETS = {
    # MOH Weekly Infectious Disease Bulletin: epi_week, disease, no._of_cases (2012-2022)
    "bulletin": "d_ca168b2cb763640d72c4600a68f9909e",
    # MOH Average Daily Polyclinic Attendances for Selected Diseases (2012-2022)
    "polyclinic": "d_5d5508f1c954f5630d7b3aa7875d01f9",
    # NEA Historical 24-hr PSI, hourly, by region (2014 onwards)
    "psi": "d_b4cf557f8750260d229c49fd768e11ed",
}

# Respiratory series from the polyclinic dataset compared against PSI
RESPIRATORY_DISEASE = "Acute Upper Respiratory Tract infections"

# PSI bands used by NEA
PSI_BANDS = [
    (0, 50, "Good"),
    (51, 100, "Moderate"),
    (101, 200, "Unhealthy"),
    (201, 300, "Very unhealthy"),
    (301, 10_000, "Hazardous"),
]
HAZE_THRESHOLD = 100  # weekly max 24-hr PSI above this = "haze week"

# Aberration detection
DETECTION = {
    "ears_baseline_weeks": 7,     # EARS C1/C2 baseline length
    "ears_threshold": 3.0,        # alert when (obs - mean) / sd exceeds this
    "hist_years": 5,              # historical limits: years of history
    "hist_half_window": 1,        # +/- weeks around the same week in past years
    "hist_z": 2.0,                # alert when obs > mean + z * sd
    "min_cases": 5,               # never alert below this weekly count
    "sd_floor": 1.0,              # avoid tiny SDs for rare diseases
    # Years left out of the historical baseline (COVID-19 measures distorted
    # reporting of most infections). Set to [] to include them.
    "exclude_baseline_years": [2020, 2021],
}
