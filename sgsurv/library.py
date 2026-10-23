"""Package the optional data library for the static dashboard."""
import json
import shutil
from html import escape
from pathlib import Path

import pandas as pd


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
        preview=pd.read_csv(base / item["path"],nrows=8)
        parts.append(f'<details class="library-dataset"><summary>{escape(item["title"])} · {item["rows"]:,} rows</summary>'
                     f'<p><strong>Units:</strong> {escape(item["units"])}<br>{escape(item["note"])}</p>'
                     + ''.join(f'<p><strong>Quality note:</strong> {escape(note)}</p>' for note in item.get("quality_notes",[]))
                     +
                     f'<a class="download-link" href="chart-assets/data-library/{key}.csv" download>Download complete CSV</a>'
                     '<p>Preview: first eight rows. Empty cells represent missing values.</p><div class="library-table">'
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
