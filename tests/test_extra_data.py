import json
from pathlib import Path

import pandas as pd
import pytest

from sgsurv.extra_clean import repair_polyclinic, psi_daily, weather_daily, flu_weekly, weekly_covariates
from sgsurv.extra_fetch import download_flunet, save_bytes


def test_known_chickenpox_repair_does_not_mutate_raw():
    raw=pd.DataFrame({"disease":["Chickenpox"]*2,"epi_week":["2014-W52"]*2,"no._of_cases":[14,19]})
    out=repair_polyclinic(raw)
    assert out.epi_week.tolist()==["2014-W52","2014-W53"]
    assert raw.epi_week.tolist()==["2014-W52"]*2
    with pytest.raises(ValueError,match="Unexpected"):
        repair_polyclinic(raw.assign(**{"no._of_cases":[14,25]}))


def test_invalid_download_keeps_previous_cache(tmp_path):
    target=tmp_path / "dataset.csv"
    target.write_text("date,value\n2026-01-01,1\n")
    old=target.read_bytes()
    with pytest.raises((ValueError,pd.errors.ParserError)):
        save_bytes(target,b"<html>Error</html>",csv=True)
    assert target.read_bytes()==old


def test_psi_preserves_partial_days_and_rejects_conflicting_overlap():
    historical=pd.DataFrame({"24hr_psi":["2016-04-04 010:00:00"],**{r:[40] for r in ["north","south","east","west","central"]}})
    recent=pd.DataFrame({"timestamp":["2016-04-04T01:00:00+08:00"]*5,"region":["north","south","east","west","central"],"psi_twenty_four_hourly":[50,55,60,65,70]})
    out=psi_daily(historical,recent)
    assert out.hours_reported.tolist()==[2]
    assert out.hours_all_regions.tolist()==[2]
    assert out.psi_daily_max.iloc[0]==70
    conflict=recent.assign(timestamp="2016-04-04T00:00:00+08:00")
    with pytest.raises(ValueError,match="disagree"):
        psi_daily(historical,conflict)
    with pytest.warns(UserWarning,match="historical bulk"):
        revised=psi_daily(historical,conflict,prefer_historical=True)
    assert revised.psi_daily_max.iloc[0]==40
    assert revised.attrs["quality_notes"]


def test_weather_missing_rainfall_is_not_zero():
    data=pd.DataFrame({"year":[2026],"month":[1],"day":[1],"daily_rainfall_total_mm":["—"],"mean_temperature_c":["28"],"maximum_temperature_c":["30"],"minimum_temperature_c":["25"]})
    assert pd.isna(weather_daily(data).rainfall_mm.iloc[0])


def flu_rows(count,offset=0):
    return [dict(COUNTRY_CODE="SGP",COUNTRY_AREA_TERRITORY="Singapore",MMWR_WEEKSTARTDATE="2026-01-04",ORIGIN_SOURCE="SENTINEL",SPEC_PROCESSED_NB=0,INF_A=0,AH1N12009=0,AH3=0,INF_B=0,row=i) for i in range(offset,offset+count)]


def test_who_manual_skip_paging_without_nextlink(tmp_path):
    requests=[]
    class Response:
        def __init__(self,rows): self.rows=rows
        def json(self): return {"value":self.rows}
    def getter(url,params):
        requests.append(params)
        return Response(flu_rows(1000) if len(requests)==1 else flu_rows(7,1000))
    target=tmp_path / "who.csv"
    download_flunet(["SGP"],target,getter=getter)
    assert len(pd.read_csv(target))==1007
    assert requests[1]["$skip"]==1000


def test_flu_zero_denominator_and_sources_remain_separate():
    frame=pd.DataFrame(flu_rows(1))
    frame=pd.concat([frame,frame.assign(ORIGIN_SOURCE="NONSENTINEL",INF_A=5,SPEC_PROCESSED_NB=10)])
    out=flu_weekly(frame)
    assert len(out)==2
    assert out.loc[out.origin_source.eq("SENTINEL"),"pct_positive_a"].isna().all()
    assert out.loc[out.origin_source.eq("NONSENTINEL"),"pct_positive_a"].iloc[0]==50


def test_weekly_unknown_future_school_calendar_is_not_assumed_open():
    psi=pd.DataFrame({"date":pd.to_datetime(["2027-01-10"]),"psi_daily_mean":[40],"psi_daily_max":[50]})
    weather=pd.DataFrame({"date":pd.to_datetime(["2027-01-10"]),"rainfall_mm":[float("nan")],"mean_temperature_c":[28]})
    holidays=pd.DataFrame({"date":pd.to_datetime(["2027-01-01"])})
    school=pd.DataFrame({"year":[2026],"start_date":pd.to_datetime(["2026-12-01"]),"end_date":pd.to_datetime(["2026-12-31"]),"type":["vacation"]})
    humidity=pd.DataFrame({"month":["2027-01"],"mean_rh":[80]})
    out=weekly_covariates(psi,weather,holidays,school,humidity)
    future=out[out.week_start.ge("2027-01-03")]
    assert future.school_holiday_week.isna().all()
    assert future.rainfall_mm.isna().all()
