"""Build independent illness/calendar and regional explorer payloads."""
import json
from pathlib import Path
import pandas as pd
from .config import ROOT
from .extra_sources import SEA_COUNTRIES
from . import regional


def prepare(destination):
    destination=Path(destination)
    destination.mkdir(exist_ok=True,parents=True)
    series=[]
    for filename,label,units in [("polyclinic_weekly.csv","Polyclinic","Average daily attendances"),("bulletin_detection.csv","Notifications","Notified cases per week")]:
        frame=pd.read_csv(ROOT / "data" / "processed" / filename)
        for disease,rows in frame.groupby("disease",sort=True):
            rows=rows.sort_values("week_start")
            # Retain calendar gaps as missing observations rather than joining lines.
            indexed=rows.assign(week_start=pd.to_datetime(rows.week_start)).set_index("week_start")
            indexed=indexed.reindex(pd.date_range(indexed.index.min(),indexed.index.max(),freq="W-SUN"))
            respiratory=any(t in disease.lower() for t in ["respiratory","influenza","pertussis","pneumococcal","measles","sars","diphtheria"])
            series.append(dict(id=f"{label}:{disease}",name=disease,source=label,units=units,respiratory=respiratory,
                               dates=indexed.index.strftime("%Y-%m-%d").tolist(),values=json.loads(indexed.cases.to_json(orient="values"))))
    school=pd.read_csv(ROOT / "data" / "extra" / "processed" / "school_holidays.csv")
    flu=regional.influenza(pd.read_csv(ROOT / "data" / "extra" / "processed" / "flunet_weekly_by_source.csv"))
    flu=flu[flu.origin_source.eq("SENTINEL")]
    tb=pd.read_csv(ROOT / "data" / "extra" / "processed" / "southeast_asia_tb_annual.csv").dropna(subset="incidence_per_100000")
    path=ROOT / "data" / "reference" / "briefing.json"
    news=json.loads(path.read_text(encoding="utf-8")) if path.exists() else dict(items=[],sources=[])
    result=dict(series=series,school=json.loads(school.to_json(orient="records")),school_years=sorted(school.year.unique().tolist()),
                countries=SEA_COUNTRIES,flu=json.loads(flu.to_json(orient="records",date_format="iso")),tb=json.loads(tb.to_json(orient="records")),
                pathogens=json.loads((ROOT / "data" / "reference" / "pathogens.json").read_text(encoding="utf-8")),briefing=news)
    (destination / "enhancements.json").write_text(json.dumps(result,allow_nan=False),encoding="utf-8")
    return result
