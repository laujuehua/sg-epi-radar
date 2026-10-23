import pandas as pd
import pytest

from sgsurv import clean, detect
from sgsurv.validate import validate


def test_reported_zero_and_invalid_values_stay_distinct():
    raw = pd.DataFrame({"epi_week":["2026-W01","2026-W02","2026-W03"],
                        "disease":["Dengue"]*3,"cases":["0","-","8"]})
    result = clean.clean_weekly_disease(raw)
    assert result.cases.iloc[0] == 0
    assert pd.isna(result.cases.iloc[1])
    assert result.missing_observation.tolist() == [False,True,False]


def test_missing_baseline_does_not_create_artificial_zero():
    data = pd.DataFrame({"week_start":pd.date_range("2012-01-01",periods=52*6,freq="7D"),"cases":10.})
    data.loc[20,"cases"] = float("nan")
    result = detect.historical_limits(data)
    assert result.hl_expected.dropna().eq(10).all()
    c2 = detect.ears_c2(pd.Series([10.]*5+[float("nan")]+[10.]*4+[50.]))
    assert pd.isna(c2.c2_threshold.iloc[-1])


def test_conflicting_sources_warn_and_keep_priority():
    first=pd.DataFrame({"epi_week":["2026-W01"],"disease":["Dengue"],"no._of_cases":[10]})
    second=first.assign(**{"no._of_cases":20})
    with pytest.warns(UserWarning,match="conflicting"):
        out=clean.combine_sources(None,[first,second])
    assert out["no._of_cases"].iloc[0] == 10


def test_lag_uses_calendar_weeks_and_excludes_partial_psi():
    dates=pd.date_range("2026-01-04",periods=8,freq="7D")
    df=pd.DataFrame({"week_start":dates,"psi_mean":range(8),"attendances":range(8),"days_with_data":7})
    df=df.drop(index=3)
    df.loc[4,"days_with_data"]=3
    result=clean.lagged_correlations(df)
    assert result.n_weeks.tolist()[:2] == [6,4]


def test_publication_rejects_duplicates_and_coverage_regression():
    result=pd.DataFrame({"disease":["Dengue"],"week_start":pd.to_datetime(["2026-10-04"]),"cases":[10]})
    psi=pd.DataFrame({"week_start":pd.to_datetime(["2026-10-04"]),"days_with_data":[3]})
    assert "fewer than 7" in validate(result,psi)[0]
    with pytest.raises(ValueError,match="Duplicate disease"):
        validate(pd.concat([result,result]),psi)
    with pytest.raises(ValueError,match="regressed"):
        validate(result,psi,{"bulletin_through":"2026-10-11","psi_through":"2026-10-04"})
    with pytest.raises(ValueError,match="fell"):
        validate(result,psi,{"bulletin_through":"2026-10-04","psi_through":"2026-10-04","n_current_diseases":2})
