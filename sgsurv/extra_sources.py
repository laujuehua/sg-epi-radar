"""Source recipes extracted from the IDE5011 data scripts; no model code."""
from .config import ROOT

EXTRA = ROOT / "data" / "extra"
IMPORTED = ROOT / "data" / "imported" / "ide5011"
REFERENCE = ROOT / "data" / "reference" / "ide5011"

# Stable internal names avoid pretending a future refresh still ends in 2026.
DATA_GOV = {
    "notifications": ("d_ca168b2cb763640d72c4600a68f9909e", "datagovsg_weekly_notifications_2012_2022.csv"),
    "polyclinic": ("d_5d5508f1c954f5630d7b3aa7875d01f9", "datagovsg_polyclinic_attendances_2012_2022.csv"),
    "psi_historical": ("d_b4cf557f8750260d229c49fd768e11ed", "datagovsg_historical_24hr_psi_2014_2026.csv"),
    "humidity": ("d_e3b1111a26b2aefef4f386c068d4ca5d", "datagovsg_relative_humidity_monthly_mean.csv"),
    "residents": ("d_3cf667d761b4bdc6d4d3d3aeec37dea5", "datagovsg_residents_by_age_ethnic_sex_annual.csv"),
    "total_population": ("d_6c26f6181f2e5dd62bf3210fa1029074", "datagovsg_total_population_broad_age_sex_annual.csv"),
    "public_holidays": ("d_8ef23381f9417e4d4254ee8b4dcdb176", "datagovsg_public_holidays_2020_2027.csv"),
    "visitors": ("d_d1c33009b674dcf70b8e8c790b793f28", "datagovsg_visitor_arrivals_by_residence_monthly.csv"),
    "deaths_cause": ("d_f9e1ec367036b43d97eec96cbcee7827", "datagovsg_deaths_by_cause_certification_2022_2024.csv"),
    "deaths_age": ("d_716c31ea00d7c05d43d4109d8b0db3bb", "datagovsg_cause_of_death_by_age_2024.csv"),
    "deaths_rates": ("d_e2c79c60c046f9a2061328cc3f665688", "datagovsg_deaths_and_death_rates_by_cause_annual.csv"),
    "deaths_monthly": ("d_ccff6769339af25d11a9223031e87da3", "datagovsg_deaths_by_ethnic_sex_monthly.csv"),
}
CURATED = {
    "school_calendar.csv": "moe_school_terms_and_holidays_2012_2026.csv",
    "vaccination_coverage.csv": "moh_nphs_influenza_vaccination_coverage.csv",
    "public_holidays_legacy.csv": "public_holidays_2012_2019_python_holidays.csv",
}
WEATHER_COLUMNS = ["station", "year", "month", "day", "daily_rainfall_total_mm",
    "highest_30min_rainfall_mm", "highest_60min_rainfall_mm", "highest_120min_rainfall_mm",
    "mean_temperature_c", "maximum_temperature_c", "minimum_temperature_c",
    "mean_wind_speed_kmh", "max_wind_speed_kmh"]
FLUNET_COUNTRIES = ["SGP", "MYS", "IDN", "THA", "PHL", "VNM", "KHM", "LAO"]
