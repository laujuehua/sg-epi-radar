"""Fetch attributed headline links and official WHO outbreak notices; no article bodies."""
import json
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET

from .config import ROOT
from .extra_fetch import get

OUTPUT=ROOT / "data" / "reference" / "briefing.json"
TERMS={"Influenza":["influenza","flu ","bird flu"],"Dengue":["dengue"],"Measles":["measles"],
       "Pertussis":["pertussis","whooping cough"],"HFMD":["hand, foot","hand foot","hfmd"],
       "COVID-19":["covid","sars-cov-2"],"MERS":["middle east respiratory","mers"],"Mpox":["mpox","monkeypox"],"Tuberculosis":["tuberculosis"],
       "Other":["outbreak","cholera","marburg","ebola","nipah","infection","infectious","vaccine","respiratory","malaria"]}
REGION=["singapore","malaysia","indonesia","thailand","vietnam","viet nam","philippines","cambodia","laos","lao ","myanmar","brunei","timor"]


def tags(title):
    lower=title.lower()
    return [name for name,terms in TERMS.items() if any(t in lower for t in terms)]


def normalise(title,url,date,source,scope,kind):
    title=unescape(re.sub(r"<[^>]*>","",title)).strip()
    parsed=urlparse(url)
    if parsed.scheme!="https" or parsed.hostname not in {"www.who.int","www.channelnewsasia.com"}:
        raise ValueError("Unexpected headline URL")
    topic=tags(title)
    if not topic and kind=="Media headline":
        return None
    return dict(title=title,url=url.split("#")[0],published=date,source=source,scope=scope,kind=kind,topics=topic or ["Other"])


def refresh():
    previous=json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {"items":[]}
    stamp=datetime.now(timezone.utc).isoformat(timespec="seconds")
    items=[]; statuses=[]
    sources=[("WHO Disease Outbreak News","WHO",None),
             ("CNA Singapore","Singapore",10416),("CNA Asia","Southeast Asia / Asia",6511),("CNA World","Global",6311)]
    for name,scope,category in sources:
        try:
            found=[]
            if category is None:
                payload=get("https://www.who.int/api/default/diseaseoutbreaknews",params={"$orderby":"PublicationDate desc","$top":100,"$select":"Title,PublicationDate,ItemDefaultUrl"}).json()
                for row in payload["value"]:
                    title=row["Title"]
                    region="Singapore" if "singapore" in title.lower() else "Southeast Asia / Asia" if any(c in title.lower() for c in REGION) else "Global"
                    url=urljoin("https://www.who.int/emergencies/disease-outbreak-news/",row["ItemDefaultUrl"])
                    if "/emergencies/" not in url:
                        url="https://www.who.int/emergencies/disease-outbreak-news"+row["ItemDefaultUrl"]
                    found.append(normalise(title,url,row["PublicationDate"][:10],name,region,"Official outbreak notice"))
            else:
                xml=ET.fromstring(get("https://www.channelnewsasia.com/api/v1/rss-outbound-feed",params={"_format":"xml","category":category}).content)
                for row in xml.findall(".//item"):
                    date=parsedate_to_datetime(row.findtext("pubDate")).date().isoformat()
                    found.append(normalise(row.findtext("title",""),row.findtext("link",""),date,name,scope,"Media headline"))
            items.extend(i for i in found if i)
            statuses.append(dict(source=name,status="refreshed",checked_at=stamp))
        except Exception as err:
            items.extend(i for i in previous["items"] if i["source"]==name)
            statuses.append(dict(source=name,status="cached_after_failure",checked_at=stamp,error=type(err).__name__))
    curated=OUTPUT.with_name("news_links.json")
    if curated.exists():
        items.extend(json.loads(curated.read_text(encoding="utf-8")))
    unique={i["url"]:i for i in items}
    result=dict(checked_at=stamp,sources=statuses,items=sorted(unique.values(),key=lambda i:i["published"],reverse=True)[:150],
                note="Keyword-filtered headline links; geographic labels follow feed categories or title matching. Not a comprehensive outbreak feed.")
    OUTPUT.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(f"Briefing: {len(result['items'])} links; {statuses}")
    return result


if __name__=="__main__":
    refresh()
