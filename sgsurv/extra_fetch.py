"""Refresh the extracted public-data recipes into this project's own raw cache."""
import io
import json
import os
import shutil
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import pandas as pd
import numpy as np
import requests

from . import clean, fetch_cda
from .extra_sources import EXTRA, IMPORTED, REFERENCE, DATA_GOV, CURATED, WEATHER_COLUMNS
from .import_data import sha256


def seed_cache(base=EXTRA, imported=IMPORTED, reference=REFERENCE):
    raw = base / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    reference.mkdir(parents=True, exist_ok=True)
    initial = {f"{key}.csv": old for key, (_, old) in DATA_GOV.items()}
    initial.update({"weather_daily_raw.csv":"mss_daily_weather_changi_2012_2026.csv",
                    "flunet_singapore.csv":"who_flunet_singapore_all.csv",
                    "flunet_neighbours.csv":"who_flunet_southeast_asia.csv"})
    initial.update({f"contact_{name}.rdata":f"contact_{name}.rdata" for name in ["all","home","school","work","others"]})
    for name, old in initial.items():
        source = imported / "raw" / old
        if source.exists() and not (raw / name).exists():
            shutil.copyfile(source, raw / name)
    for name, old in CURATED.items():
        if not (reference / name).exists() and (imported / "raw" / old).exists():
            shutil.copyfile(imported / "raw" / old, reference / name)
    recent = sorted((imported / "raw").glob("datagovsg_psi_hourly_*.csv"))
    if recent and not (raw / "psi_recent.csv").exists():
        pd.concat([pd.read_csv(p) for p in recent], ignore_index=True).drop_duplicates(["timestamp","region"]).to_csv(raw / "psi_recent.csv",index=False)
    cda = raw / "cda"
    cda.mkdir(exist_ok=True)
    for source in (imported / "raw").glob("cda_weekly_bulletin_*.xls*"):
        target=cda / source.name
        if not target.exists():
            shutil.copyfile(source, target)


_last_api_call = {}


def get(url, params=None, attempts=3):
    headers={"User-Agent":"sg-id-surveillance/0.2 public-data-refresh"}
    provider = urlparse(url).hostname == "api-open.data.gov.sg"
    category = "realtime" if "/real-time/" in url else "download"
    if provider and os.environ.get("DATA_GOV_SG_API_KEY"):
        headers["X-Api-Key"] = os.environ["DATA_GOV_SG_API_KEY"]
    for attempt in range(attempts):
        try:
            if provider:
                spacing = 2.1 if category == "realtime" else 13
                time.sleep(max(0, spacing - (time.monotonic() - _last_api_call.get(category, 0))))
                _last_api_call[category] = time.monotonic()
            response=requests.get(url,params=params,headers=headers,timeout=(15,60))
            if response.status_code==429 or response.status_code>=500:
                response.raise_for_status()
            response.raise_for_status()
            return response
        except requests.RequestException as err:
            if attempt+1==attempts:
                raise
            retry = getattr(err, "response", None)
            delay = retry.headers.get("Retry-After", "15") if retry is not None and retry.status_code == 429 else str(2**attempt)
            time.sleep(min(60, float(delay) if delay.isdigit() else 15))


def save_bytes(path, content, csv=False):
    """Validate before replacing a cache; retain old bytes by content hash."""
    path.parent.mkdir(parents=True,exist_ok=True)
    if csv:
        data=pd.read_csv(io.BytesIO(content))
        if data.empty or len(data.columns)<2:
            raise ValueError(f"Empty or invalid CSV: {path.name}")
    temporary=path.with_suffix(path.suffix+".part")
    temporary.write_bytes(content)
    if path.exists() and sha256(path)!=sha256(temporary):
        archive=path.parent / "versions" / sha256(path)
        archive.parent.mkdir(exist_ok=True)
        if not archive.exists():
            shutil.copyfile(path,archive)
    temporary.replace(path)


def download_contact(url, target):
    """Reject invalid downloads before replacing the last good contact cache."""
    try:
        import rdata
    except ImportError:
        sys.path.insert(0,str(Path(__file__).resolve().parents[1] / ".vendor"))
        import rdata
    content=get(url).content
    temporary=target.with_suffix(".validation.rdata")
    try:
        temporary.write_bytes(content)
        parsed=rdata.read_rda(temporary)
        values=np.asarray(next(iter(parsed.values()))["SGP"],dtype=float)
        if values.shape!=(16,16) or not np.isfinite(values).all() or (values<0).any():
            raise ValueError("Invalid Singapore contact matrix")
        save_bytes(target,content)
    finally:
        temporary.unlink(missing_ok=True)


def download_data_gov(dataset_id, target):
    api=f"https://api-open.data.gov.sg/v1/public/api/datasets/{dataset_id}"
    initiated=False
    for _ in range(10):
        payload=get(api+"/poll-download").json()
        url=(payload.get("data") or {}).get("url")
        if url:
            save_bytes(target,get(url).content,csv=True)
            return
        if not initiated:
            get(api+"/initiate-download")
            initiated=True
        time.sleep(2)
    raise TimeoutError(f"Bulk download not ready: {dataset_id}")


def download_flunet(countries, target, getter=get):
    base="https://xmart-api-public.who.int/FLUMART/VIW_FNT"
    expression=" or ".join(f"COUNTRY_CODE eq '{country}'" for country in countries)
    url=base
    query={"$filter":expression,"$top":1000,"$orderby":"COUNTRY_CODE,MMWR_WEEKSTARTDATE,ORIGIN_SOURCE"}
    params=query.copy()
    rows,seen,signatures=[],set(),set()
    for _ in range(100):
        response=getter(url,params=params)
        payload=response.json()
        values=payload.get("value")
        if not isinstance(values,list):
            raise ValueError("WHO response does not contain an OData value list")
        signature=json.dumps(values,sort_keys=True)
        if values and signature in signatures:
            raise ValueError("WHO pagination repeated a page")
        signatures.add(signature)
        rows.extend(values)
        next_link=payload.get("@odata.nextLink") or payload.get("odata.nextLink")
        if not next_link:
            if len(values)<1000:
                break
            # WHO honours $top as a total limit and may omit nextLink. Explicit
            # skip paging is essential; Singapore alone already exceeds 1,000 rows.
            url=base
            params={**query,"$skip":len(rows)}
            continue
        url=urljoin(base,next_link)
        if urlparse(url).scheme!="https" or urlparse(url).hostname!=urlparse(base).hostname or url in seen:
            raise ValueError("Unexpected or repeated WHO pagination URL")
        seen.add(url)
        params=None
    else:
        raise ValueError("WHO pagination exceeded 100 pages")
    frame=pd.DataFrame(rows)
    required={"COUNTRY_CODE","MMWR_WEEKSTARTDATE","ORIGIN_SOURCE","SPEC_PROCESSED_NB","INF_A"}
    if not required.issubset(frame) or not set(frame.COUNTRY_CODE).issubset(countries):
        raise ValueError("Unexpected FluNet schema or country filter")
    save_bytes(target,frame.to_csv(index=False).encode(),csv=True)


def refresh_weather(raw, today):
    existing=pd.read_csv(raw / "weather_daily_raw.csv",dtype=str) if (raw / "weather_daily_raw.csv").exists() else pd.DataFrame()
    cache=raw / "weather_months"
    cache.mkdir(exist_ok=True)
    if not existing.empty:
        for (year,month),group in existing.groupby(["year","month"]):
            file=cache / f"{int(year):04d}{int(month):02d}.csv"
            if not file.exists():
                group.to_csv(file,index=False)
    missing=[]
    for month in pd.date_range("2012-01-01",today,freq="MS"):
        file=cache / (month.strftime("%Y%m")+".csv")
        if file.exists() and month < pd.Timestamp(today).replace(day=1)-pd.DateOffset(months=1):
            continue
        url=f"https://www.weather.gov.sg/files/dailydata/DAILYDATA_S24_{month:%Y%m}.csv"
        try:
            response=get(url)
            content=response.content.decode("utf-8-sig",errors="replace")
            data=pd.read_csv(io.StringIO(content),dtype=str)
            if len(data.columns)!=len(WEATHER_COLUMNS):
                raise ValueError("MSS daily schema changed")
            data.columns=WEATHER_COLUMNS
            data.insert(0,"source_file",f"DAILYDATA_S24_{month:%Y%m}.csv")
            if data.empty:
                raise ValueError("MSS month has no records")
            save_bytes(file,data.to_csv(index=False).encode(),csv=True)
        except requests.HTTPError as err:
            if err.response.status_code not in (404,403):
                raise
            missing.append(f"{month:%Y-%m}: HTTP {err.response.status_code}")
    frames=[pd.read_csv(p,dtype=str) for p in sorted(cache.glob("*.csv"))]
    if not frames:
        raise ValueError("No weather months available")
    save_bytes(raw / "weather_daily_raw.csv",pd.concat(frames,ignore_index=True).to_csv(index=False).encode(),csv=True)
    return missing


def refresh_psi(raw, today):
    historical=pd.read_csv(raw / "psi_historical.csv",dtype=str)
    times=historical.iloc[:,0].replace({"2016-04-04 010:00:00":"2016-04-04 00:00:00"})
    last=clean.parse_timestamps(times).max().normalize()
    path=raw / "psi_recent.csv"
    recent=pd.read_csv(path) if path.exists() else pd.DataFrame(columns=["timestamp","region","psi_twenty_four_hourly"])
    if len(recent):
        recent["_day"]=clean.parse_timestamps(recent.timestamp).dt.strftime("%Y-%m-%d")
    issues=[]
    for day in pd.date_range(last+pd.Timedelta(days=1),today):
        label=f"{day:%Y-%m-%d}"
        cached=recent[recent.get("_day",pd.Series(index=recent.index,dtype=str)).eq(label)]
        if len(cached) and cached.timestamp.nunique()>=24 and day<pd.Timestamp(today)-pd.Timedelta(days=2):
            continue
        try:
            payload=get("https://api-open.data.gov.sg/v2/real-time/api/psi",params={"date":label}).json()
            items=(payload.get("data") or {}).get("items") or []
            if not items:
                raise ValueError("No PSI observations returned")
            rows=[]
            for item in items:
                for region in clean.REGIONS:
                    row=dict(timestamp=item["timestamp"],date=item.get("date"),region=region,_day=label)
                    for metric in ["psi_twenty_four_hourly","pm25_twenty_four_hourly","pm25_sub_index","pm10_twenty_four_hourly"]:
                        row[metric]=(item["readings"].get(metric) or {}).get(region)
                    rows.append(row)
            part=pd.DataFrame(rows)
            if part.psi_twenty_four_hourly.isna().all():
                raise ValueError("PSI readings missing")
            if len(recent):
                recent=recent[~recent._day.eq(label)]
            recent=pd.concat([recent,part],ignore_index=True)
            # Save each successful day so an interrupted backfill resumes from cache.
            save_bytes(path,recent.drop(columns="_day").drop_duplicates(["timestamp","region"]).to_csv(index=False).encode(),csv=True)
            time.sleep(.2)
        except (requests.RequestException,ValueError,KeyError) as err:
            issues.append(f"{label}: {type(err).__name__}")
    return issues


def refresh(base=EXTRA, groups=None, today=None):
    seed_cache(base=base)
    raw=base / "raw"
    today=today or datetime.now(ZoneInfo("Asia/Singapore")).date()
    status_file=base / "refresh_status.json"
    previous=json.loads(status_file.read_text(encoding="utf-8")) if status_file.exists() else {}
    for record in previous.get("sources",[]):
        record.setdefault("checked_at",previous.get("run_at"))
    report={"run_at":datetime.now(timezone.utc).isoformat(timespec="seconds"),"sources":previous.get("sources",[])}
    chosen=set(groups or ["data_gov","flunet","psi","weather","contacts","cda"])
    def step(name,url,target,action):
        record=dict(name=name,source=url,path=target.relative_to(base).as_posix(),checked_at=report["run_at"])
        try:
            notes=action() or []
            if isinstance(notes,Path):
                target=notes
                record["path"]=target.relative_to(base).as_posix()
                notes=[]
            record.update(status="partial" if notes else "refreshed",notes=notes)
            record["last_success_at"]=report["run_at"]
        except Exception as err:
            record.update(status="cached_after_failure" if target.exists() else "unavailable",error=type(err).__name__)
            old=next((r for r in report["sources"] if r["name"]==name),{})
            if old.get("last_success_at"):
                record["last_success_at"]=old["last_success_at"]
        if target.is_file():
            record["sha256"]=sha256(target)
        report["sources"]=[r for r in report["sources"] if r["name"]!=name]+[record]
        (base / "refresh_status.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        print(f"{name}: {record['status']}",flush=True)
    if "data_gov" in chosen:
        for name,(dataset_id,_) in DATA_GOV.items():
            target=raw / f"{name}.csv"
            step(name,f"https://data.gov.sg/datasets/{dataset_id}/view",target,lambda d=dataset_id,t=target:download_data_gov(d,t))
    if "flunet" in chosen:
        for name,countries in [("singapore",["SGP"]),("neighbours",["MYS","IDN","THA","PHL","VNM","KHM","LAO"])]:
            target=raw / f"flunet_{name}.csv"
            step(f"flunet_{name}","https://xmart-api-public.who.int/FLUMART/VIW_FNT",target,lambda c=countries,t=target:download_flunet(c,t))
    if "psi" in chosen:
        step("psi_recent","https://api-open.data.gov.sg/v2/real-time/api/psi",raw / "psi_recent.csv",lambda:refresh_psi(raw,today))
    if "weather" in chosen:
        step("weather","https://www.weather.gov.sg/climate-historical-daily/",raw / "weather_daily_raw.csv",lambda:refresh_weather(raw,today))
    if "contacts" in chosen:
        for setting in ["all","home","school","work","others"]:
            target=raw / f"contact_{setting}.rdata"
            url=f"https://raw.githubusercontent.com/kieshaprem/synthetic-contact-matrices/master/output/syntheticmatrices/contact_{setting}.rdata"
            step(f"contact_{setting}",url,target,lambda t=target,u=url:download_contact(u,t))
    if "cda" in chosen:
        for year in range(2023,today.year+1):
            target=next(iter((raw / "cda").glob(f"bulletin_{year}.xls*")),raw / "cda" / f"bulletin_{year}.xlsx")
            def download(year=year):
                saved=fetch_cda.fetch_year(year,raw / "cda" / ".incoming")
                if saved is None:
                    raise ValueError("No bulletin workbook published")
                clean.read_cda_excel(saved)
                destination=raw / "cda" / saved.name
                save_bytes(destination,saved.read_bytes())
                return destination
            step(f"cda_{year}",fetch_cda.PAGE_URL.format(year=year),target,download)
    return report
