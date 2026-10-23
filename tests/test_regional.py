import pandas as pd

from sgsurv.extra_fetch import download_tb
from sgsurv.regional import influenza,coverage,flu_chart


def test_regional_positivity_invalid_denominators_and_missing_subtypes():
    frame=pd.DataFrame(dict(country_code=["SGP"]*4,week_start=["2026-01-04","2026-01-11","2026-01-18","2026-01-25"],
                            origin_source=["SENTINEL"]*4,tested=[100,0,10,100],inf_a=[10,0,20,10],inf_b=[5,0,1,None]))
    out=influenza(frame)
    assert out.positivity_pct.iloc[0]==15
    assert out.positivity_pct.iloc[1:].isna().all()


def test_regional_coverage_lists_all_countries_without_source_substitution():
    frame=pd.DataFrame(dict(country_code=["SGP"],week_start=["2026-01-04"],origin_source=["NONSENTINEL"],tested=[100],inf_a=[10],inf_b=[5]))
    data=influenza(frame)
    tb=pd.DataFrame(columns=["country_code","year","incidence_per_100000"])
    out=coverage(data,tb)
    assert len(out)==11
    singapore=out[out.Country.eq("Singapore")].iloc[0]
    assert singapore["Latest sentinel week"]=="Unavailable"
    assert singapore["Reporting sources available"]=="NONSENTINEL"


def test_world_bank_pagination_retains_missing_years(tmp_path):
    calls=[]
    class Response:
        def json(self):
            page=calls[-1]
            return [{"pages":2},[{"countryiso3code":"SGP","date":str(2025-page),"value":None if page==2 else 25,
                                  "indicator":{"id":"SH.TBS.INCD"}}]]
    def getter(url,params):
        calls.append(params["page"])
        return Response()
    target=tmp_path / "tb.csv"
    download_tb(target,getter=getter)
    out=pd.read_csv(target)
    assert calls==[1,2]
    assert len(out)==2 and out.incidence_per_100000.isna().sum()==1
