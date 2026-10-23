"""Rebuild the extracted context tables from this project's copied raw inputs."""
import re
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from . import clean
from .extra_sources import EXTRA, REFERENCE


def number(values):
    return pd.to_numeric(values.astype(str).str.replace(",", "", regex=False).str.strip(), errors="coerce")


def repair_polyclinic(frame):
    frame=frame.copy()
    mask=frame.disease.astype(str).str.strip().eq("Chickenpox") & frame.epi_week.eq("2014-W52")
    indices=frame.index[mask]
    if len(indices)==2:
        if number(frame.loc[indices,"no._of_cases"]).tolist()!=[14,19] or (frame.disease.eq("Chickenpox") & frame.epi_week.eq("2014-W53")).any():
            raise ValueError("Unexpected duplicate Chickenpox weeks; review instead of applying the known correction")
        frame.loc[indices[1],"epi_week"]="2014-W53"
    return frame


def psi_daily(historical, recent, prefer_historical=False):
    historical=historical.copy()
    historical.iloc[:,0]=historical.iloc[:,0].replace({"2016-04-04 010:00:00":"2016-04-04 00:00:00"})
    times=clean.parse_timestamps(historical.iloc[:,0])
    if times.isna().any():
        raise ValueError("Unrecognised historical PSI timestamps")
    historical["time"]=times
    old=historical.melt(id_vars="time",value_vars=clean.REGIONS,var_name="region",value_name="psi")
    old["psi"]=number(old.psi)
    if recent.empty:
        new=pd.DataFrame(columns=["time","region","psi"])
    else:
        new=recent.assign(time=clean.parse_timestamps(recent.timestamp),psi=number(recent.psi_twenty_four_hourly))[["time","region","psi"]]
        if new.time.isna().any() or not new.region.isin(clean.REGIONS).all():
            raise ValueError("Unrecognised real-time PSI timestamps or regions")
    overlap=old.merge(new,on=["time","region"],suffixes=("_old","_new"))
    conflicts=int((overlap.psi_old.notna() & overlap.psi_new.notna() & overlap.psi_old.ne(overlap.psi_new)).sum())
    if conflicts:
        if not prefer_historical:
            raise ValueError("Overlapping historical and real-time PSI readings disagree")
        warnings.warn(f"{conflicts} overlapping PSI readings differ; historical bulk observations take priority. Both raw sources are retained.")
    hourly=pd.concat([old,new],ignore_index=True).drop_duplicates(["time","region"],keep="first").dropna(subset=["psi"])
    national=hourly.groupby("time").agg(psi_national=("psi","max"),psi_mean_regions=("psi","mean"),regions_reported=("region","nunique")).reset_index()
    national["date"]=national.time.dt.normalize()
    daily=national.groupby("date").agg(psi_daily_max=("psi_national","max"),psi_daily_mean=("psi_mean_regions","mean"),
        hours_unhealthy=("psi_national",lambda s:int(s.gt(100).sum())),hours_reported=("time","count"),
        hours_all_regions=("regions_reported",lambda s:int(s.eq(5).sum()))).reset_index()
    daily.psi_daily_mean=daily.psi_daily_mean.round(1)
    daily.attrs["quality_notes"]=[f"{conflicts} conflicting overlapping PSI region-hours: historical bulk observations take priority; both raw sources retained."] if conflicts else []
    return daily


def weather_daily(frame):
    out=pd.DataFrame({"date":pd.to_datetime(frame[["year","month","day"]].apply(pd.to_numeric,errors="coerce"),errors="coerce")})
    if out.date.isna().any():
        raise ValueError("Invalid weather dates")
    for source,target in [("daily_rainfall_total_mm","rainfall_mm"),("mean_temperature_c","mean_temperature_c"),
                          ("maximum_temperature_c","max_temperature_c"),("minimum_temperature_c","min_temperature_c")]:
        out[target]=number(frame[source])
    if out.date.duplicated().any():
        raise ValueError("Duplicate weather days")
    return out.sort_values("date",ignore_index=True)


def school_calendar(frame):
    out=frame.copy()
    for col in ["start_date","end_date"]:
        out[col]=pd.to_datetime(out[col],errors="raise")
    out["days"]=(out.end_date-out.start_date).dt.days+1
    if out.days.le(0).any():
        raise ValueError("Invalid school holiday interval")
    blocks=out[out.type.isin(["vacation","closure"])].sort_values("start_date")
    if (blocks.start_date.iloc[1:].reset_index(drop=True)<=blocks.end_date.iloc[:-1].reset_index(drop=True)).any():
        raise ValueError("Overlapping school vacation/closure periods")
    return out


def public_holidays(mom, legacy):
    old=legacy.assign(source="Python holidays package, curated legacy snapshot")
    current=mom[["date","holiday"]].assign(source="MOM via data.gov.sg")
    extra=pd.DataFrame({"date":["2022-05-16","2022-07-11"],"holiday":["Vesak Day (observed)","Hari Raya Haji (observed)"],
                        "source":"Legacy holidays reconciliation, preserved from group recipe"})
    out=pd.concat([current,old,extra],ignore_index=True)
    out.date=pd.to_datetime(out.date,errors="raise")
    return out.drop_duplicates("date",keep="first").sort_values("date",ignore_index=True)


def weekly_covariates(psi, weather, holidays, school, humidity):
    stop=max(psi.date.max(),weather.date.max())
    days=pd.DataFrame({"date":pd.date_range("2012-01-01",stop)})
    days=days.merge(psi,on="date",how="left").merge(weather,on="date",how="left")
    weekday=days.date.dt.dayofweek.lt(5)
    closed=pd.Series(False,index=days.index)
    closures=pd.Series(False,index=days.index)
    for row in school.itertuples():
        within=days.date.between(row.start_date,row.end_date)
        closed |= within
        if row.type=="closure":
            closures |= within
    holiday=days.date.isin(holidays.date)
    days["public_holiday_weekdays"]=(holiday & weekday).astype(int)
    days["school_closed_weekdays"]=((closed | holiday) & weekday).astype(int)
    days["school_closure"]=closures
    days["week_start"]=clean.to_week_start(days.date)
    out=days.groupby("week_start").agg(psi_mean=("psi_daily_mean","mean"),psi_max=("psi_daily_max","max"),
        psi_days_unhealthy=("psi_daily_max",lambda s:int(s.gt(100).sum())),psi_days_reported=("psi_daily_max","count"),
        rainfall_mm=("rainfall_mm",lambda s:s.sum(min_count=1)),rain_days_reported=("rainfall_mm","count"),
        mean_temperature_c=("mean_temperature_c","mean"),public_holiday_weekdays=("public_holiday_weekdays","sum"),
        school_closed_weekdays=("school_closed_weekdays","sum"),school_closure=("school_closure","any")).reset_index()
    out["week_end"]=out.week_start+pd.Timedelta(days=6)
    out["epi_week"]=[f"{y}-W{w:02d}" for y,w in out.week_start.map(clean._date_to_epi_week)]
    out["school_holiday_week"]=out.school_closed_weekdays.ge(3)
    known_school=out.week_start.dt.year.isin(school.year)
    out["school_calendar_available"]=known_school
    for col in ["school_closed_weekdays","school_closure","school_holiday_week"]:
        out[col]=out[col].where(known_school)
    known_public=out.week_start.dt.year.isin(holidays.date.dt.year)
    out["public_holiday_weekdays"]=out.public_holiday_weekdays.where(known_public)
    month=(out.week_start+pd.Timedelta(days=3)).dt.to_period("M").astype(str)
    humidity=humidity.copy()
    humidity["month"]=humidity.month.astype(str).str[:7]
    humidity["relative_humidity_pct"]=number(humidity.mean_rh)
    out["month"]=month
    out=out.merge(humidity[["month","relative_humidity_pct"]],on="month",how="left").drop(columns="month")
    out["psi_mean"]=out.psi_mean.round(1)
    out["mean_temperature_c"]=out.mean_temperature_c.round(2)
    return out


def annual_long(frame):
    frame=frame.copy()
    frame["series"]=frame.DataSeries.str.strip().str.replace(r"\s+"," ",regex=True)
    frame["row"]=np.arange(len(frame))
    years=[c for c in frame if re.fullmatch(r"\d{4}",str(c))]
    out=frame.melt(id_vars=["series","row"],value_vars=years,var_name="year",value_name="value")
    out.year=out.year.astype(int)
    out.value=number(out.value)
    return out


def population(residents, total):
    data=annual_long(residents)
    markers=data.loc[data.series.eq("Total Male Residents"),"row"]
    if markers.empty:
        raise ValueError("Resident population block marker not found")
    first=data[data.row.lt(markers.min()) & data.year.ge(2012)]
    groups=[f"{a} - {a+4} Years" for a in range(0,90,5)]+["90 Years & Over"]
    res=first[first.series.isin(groups)][["year","series","value"]].rename(columns={"value":"residents"})
    res["age_group"]=res.series.str.replace(" Years","",regex=False).str.replace(" & Over","+",regex=False).str.replace(" ","",regex=False)
    sums=res.groupby("year").residents.sum(min_count=1)
    expected=first[first.series.eq("Total Residents")].set_index("year").value
    if not (sums-expected).dropna().abs().lt(1).all():
        raise ValueError("Resident age groups do not add up to the published total")
    res["resident_share"]=res.residents/res.year.map(sums)
    total=annual_long(total)
    mapping={"Total Population":"total_population","0 - 14 Years":"total_0_14","15 - 64 Years":"total_15_64","65 Years & Over":"total_65_plus"}
    total=total[total.year.ge(2012)&total.series.isin(mapping)].drop_duplicates(["series","year"])
    total["group"]=total.series.map(mapping)
    wide=total.pivot(index="year",columns="group",values="value").reset_index()
    return res.drop(columns="series").merge(wide,on="year",how="left").sort_values(["year","age_group"],ignore_index=True)


def monthly_long(frame):
    columns=[c for c in frame if re.fullmatch(r"\d{4}[A-Za-z]{3}",str(c))]
    if not columns:
        raise ValueError("No SingStat monthly columns found")
    out=frame.melt(id_vars=[c for c in frame if c not in columns],value_vars=columns,var_name="month",value_name="value")
    out.month=pd.to_datetime(out.month,format="%Y%b",errors="raise")
    out.value=number(out.value)
    return out


def visitors(frame):
    frame=frame.copy()
    indentation=frame.DataSeries.str.len()-frame.DataSeries.str.lstrip().str.len()
    frame["level"]=indentation.rank(method="dense").astype(int)-1
    frame["place"]=frame.DataSeries.str.strip().str.replace(r"\s+"," ",regex=True)
    frame["region"]=frame.place.where(frame.level.eq(1)).ffill().where(frame.level.ne(0))
    out=monthly_long(frame)
    return out.dropna(subset=["value"])[["month","level","region","place","value"]].rename(columns={"value":"arrivals"}).sort_values(["month","level"],ignore_index=True)


def deaths(cause, age, monthly):
    mapping={"Influenza(J09-J11)":"Influenza","Pneumonia(J12-J18)":"Pneumonia"}
    cause=cause.copy()
    age=age.copy()
    cause["cause"]=cause.icd_detail_category.str.replace(r"^\d+-\d+-","",regex=True).map(mapping)
    cause["deaths"]=number(cause.death_count)
    age["cause"]=age.ICD_DETAILED_CATEGORY.str.replace(r"^\d+-\d+-","",regex=True).map(mapping)
    age["deaths"]=number(age.DEATH_COUNT)
    strict_sum=lambda s:s.sum() if s.notna().all() else np.nan
    all_ages=cause.dropna(subset="cause").groupby(["year","cause"]).deaths.agg(strict_sum).reset_index().assign(age_group="All ages")
    age=age.rename(columns={"YEAR":"year","DEATH_AGE":"age_group"})
    age.age_group=age.age_group.str.replace(" ","",regex=False)
    by_age=age.dropna(subset="cause").groupby(["year","cause","age_group"]).deaths.agg(strict_sum).reset_index()
    resp=pd.concat([all_ages,by_age],ignore_index=True).sort_values(["cause","year","age_group"],ignore_index=True)
    total=monthly[monthly.DataSeries.str.strip().eq("Total Deaths By Ethnic Group")]
    if len(total)!=1:
        raise ValueError("Expected one total-deaths series")
    total=monthly_long(total).dropna(subset="value")[["month","value"]].rename(columns={"value":"deaths"}).sort_values("month",ignore_index=True)
    return resp,total


def flu_weekly(frame, aggregate_sources=False):
    frame=frame.copy()
    frame["week_start"]=pd.to_datetime(frame.MMWR_WEEKSTARTDATE,errors="raise")
    mapping={"COUNTRY_AREA_TERRITORY":"country","COUNTRY_CODE":"country_code","ORIGIN_SOURCE":"origin_source",
             "SPEC_PROCESSED_NB":"tested","INF_A":"inf_a","AH1N12009":"a_h1n1pdm09","AH3":"a_h3","INF_B":"inf_b"}
    frame=frame.rename(columns=mapping)
    for col in ["tested","inf_a","a_h1n1pdm09","a_h3","inf_b"]:
        frame[col]=number(frame[col])
    keys=["country","country_code","week_start"]+([] if aggregate_sources else ["origin_source"])
    out=frame.groupby(keys,dropna=False)[["tested","inf_a","a_h1n1pdm09","a_h3","inf_b"]].sum(min_count=1).reset_index()
    if aggregate_sources:
        sources=frame.groupby(keys,dropna=False).origin_source.agg(lambda s:"+".join(sorted(set(s.dropna().astype(str)))))
        out=out.merge(sources.rename("sources").reset_index(),on=keys)
    out["pct_positive_a"]=(100*out.inf_a/out.tested.where(out.tested.gt(0))).round(1)
    out["epi_week"]=[f"{y}-W{w:02d}" for y,w in out.week_start.map(clean._date_to_epi_week)]
    return out.sort_values(keys,ignore_index=True)


def contact_matrices(raw):
    try:
        import rdata
    except ImportError:
        vendor=Path(__file__).resolve().parents[1] / ".vendor"
        if vendor.exists():
            sys.path.insert(0,str(vendor))
        import rdata
    groups=[f"{a}-{a+4}" for a in range(0,75,5)]+["75+"]
    rows=[]
    matrices={}
    for setting in ["all","home","school","work","others"]:
        parsed=rdata.read_rda(raw / f"contact_{setting}.rdata")
        values=np.asarray(next(iter(parsed.values()))["SGP"],dtype=float)
        if values.shape!=(16,16) or not np.isfinite(values).all() or (values<0).any():
            raise ValueError("Invalid Singapore contact matrix")
        matrices[setting]=values
        rows.extend(dict(setting=setting,age_group=groups[i],contact_age_group=groups[j],contacts_per_day=float(values[i,j])) for i in range(16) for j in range(16))
    if not np.allclose(sum(matrices[s] for s in ["home","school","work","others"]),matrices["all"],rtol=1e-6,atol=1e-6):
        raise ValueError("Contact setting matrices do not sum to all settings")
    return pd.DataFrame(rows)


def process(base=EXTRA, reference=REFERENCE):
    raw=base / "raw"
    output=base / "processed"
    output.mkdir(parents=True,exist_ok=True)
    read=lambda name:pd.read_csv(raw / f"{name}.csv",dtype=str)
    tables={}
    cda={"bulletin":[],"polyclinic":[]}
    for path in clean.find_cda_files(raw / "cda"):
        match=re.search(r"(\d{4})",path.name)
        if path.name.startswith("cda_weekly_") and match and list((raw / "cda").glob(f"bulletin_{match[1]}.xls*")):
            continue
        for key,frame in clean.read_cda_excel(path).items():
            cda[key].append(frame)
    notifications=clean.combine_sources(read("notifications"),cda["bulletin"])
    polyclinic=clean.combine_sources(repair_polyclinic(read("polyclinic")),cda["polyclinic"])
    tables["weekly_notifications"]=clean.clean_weekly_disease(notifications)
    tables["polyclinic_attendances"]=clean.clean_weekly_disease(polyclinic).rename(columns={"cases":"avg_daily_attendances"})
    tables["psi_daily"]=psi_daily(read("psi_historical"),read("psi_recent"),prefer_historical=True)
    tables["weather_daily"]=weather_daily(read("weather_daily_raw"))
    tables["school_holidays"]=school_calendar(pd.read_csv(reference / "school_calendar.csv"))
    tables["public_holidays"]=public_holidays(read("public_holidays"),pd.read_csv(reference / "public_holidays_legacy.csv"))
    tables["weekly_covariates"]=weekly_covariates(tables["psi_daily"],tables["weather_daily"],tables["public_holidays"],tables["school_holidays"],read("humidity"))
    tables["population_by_age"]=population(read("residents"),read("total_population"))
    tables["contact_matrix_singapore"]=contact_matrices(raw)
    tables["vaccination_coverage"]=pd.read_csv(reference / "vaccination_coverage.csv")
    tables["visitor_arrivals_monthly"]=visitors(read("visitors"))
    tables["deaths_respiratory"],tables["deaths_monthly"]=deaths(read("deaths_cause"),read("deaths_age"),read("deaths_monthly"))
    flunet_sg=read("flunet_singapore")
    flunet_neighbours=read("flunet_neighbours")
    tables["flunet_weekly_by_source"]=flu_weekly(pd.concat([flunet_sg,flunet_neighbours],ignore_index=True))
    tables["flunet_singapore_sentinel"]=flu_weekly(flunet_sg[flunet_sg.ORIGIN_SOURCE.eq("SENTINEL")])
    tables["flunet_southeast_asia_weekly"]=flu_weekly(flunet_neighbours,aggregate_sources=True)
    if (raw / "sea_tb.csv").exists():
        tables["southeast_asia_tb_annual"]=read("sea_tb")
    tables["relative_humidity_monthly"]=read("humidity").rename(columns={"mean_rh":"relative_humidity_pct"})
    tables["deaths_rates_annual"]=annual_long(read("deaths_rates")).drop(columns="row")
    # Compute and validate every table before replacing any published derived table.
    for name,frame in tables.items():
        if frame.empty:
            raise ValueError(f"No derived rows: {name}")
        if frame.select_dtypes(include="number").isin([np.inf,-np.inf]).any().any():
            raise ValueError(f"Non-finite values: {name}")
    for name,frame in tables.items():
        target=output / f"{name}.csv"
        temporary=target.with_suffix(".csv.part")
        frame.to_csv(temporary,index=False,date_format="%Y-%m-%d")
        temporary.replace(target)
    return tables
