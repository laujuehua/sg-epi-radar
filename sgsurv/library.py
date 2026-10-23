"""Package the optional data library for the static dashboard."""
import json
import shutil
from html import escape
from pathlib import Path

import pandas as pd
from .extra_sources import SEA_COUNTRIES


def labels(key):
    frequency="Weekly" if key.startswith(("weekly_","flunet_")) or key=="polyclinic_attendances" else "Daily" if "daily" in key else "Monthly" if "monthly" in key else "Fixed estimate" if "contact" in key else "Dated periods" if "holidays" in key else "Annual"
    publisher="WHO" if key.startswith("flunet") else "WHO / World Bank" if key=="southeast_asia_tb_annual" else "Prem et al." if "contact" in key else "CDA / MOH" if key in ["weekly_notifications","polyclinic_attendances","vaccination_coverage"] else "NEA" if key=="psi_daily" else "MSS / NEA" if key in ["weather_daily","relative_humidity_monthly"] else "MOE / curated references" if key=="school_holidays" else "MOM / curated references" if key=="public_holidays" else "STB" if key=="visitor_arrivals_monthly" else "Multiple Singapore agencies" if key=="weekly_covariates" else "SingStat"
    return frequency,publisher


def render_library(base: Path, destination: Path) -> str:
    catalog_file = base / "catalog.json"
    if not catalog_file.exists():
        return "<p>The supplementary data library has not been built yet.</p>"
    catalog = json.loads(catalog_file.read_text(encoding="utf-8"))
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(catalog_file, destination / "catalog.json")
    parts = [f'<p><strong>{len(catalog["datasets"])} datasets available for review</strong> · '
             f'{catalog.get("imported_file_count", 0)} original files retained locally. '
             'Existing analytical charts keep their current inputs. Expand a dataset to preview or download it.</p>',
             f'<p>Library built: {escape(catalog["generated_at"])}. Coverage dates below describe observations, '
             'not download dates. Curated references require manual review for new releases.</p>']
    rows=[]
    parts.append('<div class="radar-controls"><label>Search datasets <input id="library-search" type="search" placeholder="Disease, dataset or keyword"></label>'
                 '<label>Family <select id="library-family"><option value="">All families</option>'
                 + ''.join(f'<option>{escape(f)}</option>' for f in sorted({i["family"] for i in catalog["datasets"]}))
                 + '</select></label><label>Coverage <select id="library-region"><option value="">All countries</option><option>Singapore</option><option>Regional</option></select></label>'
                 '<label>Frequency <select id="library-frequency"><option value="">All frequencies</option>'
                 + ''.join(f'<option>{escape(f)}</option>' for f in sorted({labels(i["id"])[0] for i in catalog["datasets"]}))
                 + '</select></label><label>Publisher <select id="library-publisher"><option value="">All publishers</option>'
                 + ''.join(f'<option>{escape(p)}</option>' for p in sorted({labels(i["id"])[1] for i in catalog["datasets"]}))
                 + '</select></label></div><p id="library-count" role="status"></p>')
    for item in catalog["datasets"]:
        key=item["id"]
        source=base / item["path"]
        if source.resolve().parent != (base / "processed").resolve():
            raise ValueError("Library file must be a processed table")
        shutil.copyfile(source, destination / f"{key}.csv")
        rows.append({"Dataset":item["title"],"Family":item["family"],"Rows":f'{item["rows"]:,}',
                     "From":item["coverage_start"] or "—","Through":item["coverage_through"] or "—",
                     "Reference": "Curated" if item["curated"] else "Refreshable"})
    parts.append('<div class="library-table">'+pd.DataFrame(rows).to_html(index=False,classes="table table-striped",border=0)+'</div>')
    for item in catalog["datasets"]:
        key=item["id"]
        frame=pd.read_csv(base / item["path"])
        preview=frame.tail(8)
        region="Regional" if key.startswith(("flunet_weekly","flunet_southeast","southeast_asia")) else "Singapore"
        frequency,publisher=labels(key)
        terms=' '.join(str(v) for c in ["country","disease"] if c in frame for v in frame[c].dropna().unique())
        if "country_code" in frame:
            terms+=' '+' '.join(SEA_COUNTRIES.get(c,c) for c in frame.country_code.dropna().unique())
        search=escape(' '.join([item["title"],item["family"],item["units"],item["note"],key,publisher,terms]),quote=True)
        parts.append(f'<details class="library-dataset" data-family="{escape(item["family"])}" data-region="{region}" data-frequency="{frequency}" data-publisher="{escape(publisher)}" data-search="{search}"><summary>{escape(item["title"])} · {item["rows"]:,} rows</summary>'
                     f'<p><strong>Units:</strong> {escape(item["units"])}<br>{escape(item["note"])}</p>'
                     + ''.join(f'<p><strong>Quality note:</strong> {escape(note)}</p>' for note in item.get("quality_notes",[]))
                     +
                     f'<a class="download-link" href="chart-assets/data-library/{key}.csv" download>Download complete CSV</a>'
                     '<p>Preview: last eight stored rows (series may be grouped by country or category). Empty cells represent missing values.</p><div class="library-table">'
                     +preview.fillna("").to_html(index=False,classes="table table-striped",border=0)+'</div></details>')
    status=(catalog.get("refresh") or {}).get("sources",[])
    if status:
        health=[]
        for record in status:
            health.append({"Source":record["name"],"Refresh result":record["status"],
                           "Checked":record.get("checked_at",(catalog.get("refresh") or {}).get("run_at","")),
                           "Details":"; ".join(record.get("notes",[])) or record.get("error", "")})
        parts.append('<h3>Source refresh results</h3><p>Partial refreshes and failures retain available cached observations; '
                     'they do not mean every source is current.</p><div class="library-table">'
                     +pd.DataFrame(health).to_html(index=False,classes="table table-striped",border=0)+'</div>')
    parts.append('<p>Contact matrices: Prem et al., '
                 '<a href="https://github.com/kieshaprem/synthetic-contact-matrices">synthetic-contact-matrices</a> '
                 '(upstream GPL-3.0). Provider links, column definitions and SHA-256 hashes are included in '
                 '<a href="chart-assets/data-library/catalog.json" download>the data catalogue</a>.</p>')
    return "\n".join(parts)
