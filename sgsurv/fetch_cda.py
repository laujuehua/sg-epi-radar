"""Download CDA's yearly Weekly Infectious Disease Bulletin Excel files.

Since 2025 the bulletin is published by the Communicable Diseases Agency (CDA).
Each year has a page listing the weekly PDFs plus one Excel file for the whole
year. The Excel link changes whenever CDA re-uploads it, so this script reads
each year's page and picks up the current link.

Usage (from the project folder):
    python -m sgsurv.fetch_cda                 # 2023 to this year
    python -m sgsurv.fetch_cda --years 2024 2026
"""

from __future__ import annotations

import argparse
import html
import re
from datetime import date
from pathlib import Path
from urllib.parse import unquote, urljoin

import requests

from .config import RAW_DIR

PAGE_URL = "https://www.cda.gov.sg/resources/weekly-infectious-diseases-bulletin-{year}/"
OUT_DIR = RAW_DIR / "cda"
HEADERS = {"User-Agent": "sg-id-surveillance/0.1 (student portfolio project)"}
TIMEOUT = 60

_HREF_RE = re.compile(r"""href\s*=\s*["']([^"']+?\.xlsx?)(?:\?[^"']*)?["']""", re.IGNORECASE)


def find_excel_links(page_html: str, base_url: str) -> list[str]:
    """All .xls/.xlsx links on a page, absolute and de-duplicated, in page order."""
    links = []
    for raw in _HREF_RE.findall(page_html):
        url = urljoin(base_url, html.unescape(raw))
        if url not in links:
            links.append(url)
    return links


def fetch_year(year: int, out_dir: Path = OUT_DIR) -> Path | None:
    page_url = PAGE_URL.format(year=year)
    resp = requests.get(page_url, headers=HEADERS, timeout=TIMEOUT)
    if resp.status_code == 404:
        print(f"{year}: no bulletin page")
        return None
    resp.raise_for_status()

    links = find_excel_links(resp.text, page_url)
    if not links:
        print(f"{year}: no Excel link found on {page_url}")
        return None
    if len(links) > 1:
        print(f"{year}: {len(links)} Excel links found, using the first")
    url = links[0]

    file = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    file.raise_for_status()
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(unquote(url)).suffix.lower()
    out_path = out_dir / f"bulletin_{year}{suffix}"
    out_path.write_bytes(file.content)
    print(f"{year}: saved {len(file.content) / 1024:,.0f} KB -> {out_path}")
    return out_path


def fetch_all(years: list[int]) -> list[Path]:
    saved = []
    for year in years:
        try:
            path = fetch_year(year)
        except requests.RequestException as err:
            print(f"{year}: download failed ({err})")
            continue
        if path:
            saved.append(path)
    return saved


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--years", type=int, nargs="+",
                        default=list(range(2023, date.today().year + 1)),
                        help="years to download (default: 2023 to this year)")
    args = parser.parse_args()
    saved = fetch_all(args.years)
    print(f"Done: {len(saved)} file(s) in {OUT_DIR}")


if __name__ == "__main__":
    main()
