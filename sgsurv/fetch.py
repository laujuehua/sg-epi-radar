"""Download datasets from data.gov.sg into data/raw/.

Two routes are tried for each dataset:
1. The bulk-download API (initiate-download, then poll-download for a CSV URL).
2. Fallback: page through the datastore_search API.

An API key is optional. If you have one, set the environment variable
DATA_GOV_SG_API_KEY (e.g. in a .env file or your VS Code launch config)
for higher rate limits.
"""

from __future__ import annotations

import io
import os
import time
from pathlib import Path

import pandas as pd
import requests

from .config import DATASETS, RAW_DIR

DOWNLOAD_API = "https://api-open.data.gov.sg/v1/public/api/datasets/{id}"
SEARCH_API = "https://data.gov.sg/api/action/datastore_search"
TIMEOUT = 60


def _headers() -> dict:
    key = os.environ.get("DATA_GOV_SG_API_KEY")
    return {"x-api-key": key} if key else {}


def _get(url: str, params: dict | None = None, retries: int = 5) -> requests.Response:
    """GET with simple exponential backoff on rate limits / server errors."""
    for attempt in range(retries):
        resp = requests.get(url, params=params, headers=_headers(), timeout=TIMEOUT)
        if resp.status_code == 429 or resp.status_code >= 500:
            wait = 2 ** attempt * 5
            print(f"  HTTP {resp.status_code}; retrying in {wait}s ...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp
    resp.raise_for_status()
    return resp


def fetch_bulk(dataset_id: str, max_polls: int = 10) -> pd.DataFrame:
    """Bulk CSV download via initiate-download / poll-download."""
    base = DOWNLOAD_API.format(id=dataset_id)
    _get(f"{base}/initiate-download")
    for _ in range(max_polls):
        payload = _get(f"{base}/poll-download").json()
        url = (payload.get("data") or {}).get("url")
        if url:
            csv = requests.get(url, timeout=TIMEOUT)
            csv.raise_for_status()
            return pd.read_csv(io.StringIO(csv.text), dtype=str)
        time.sleep(3)
    raise TimeoutError(f"Bulk download for {dataset_id} not ready")


def fetch_paged(dataset_id: str, page_size: int = 1000) -> pd.DataFrame:
    """Page through datastore_search until all records are retrieved."""
    records, offset, total = [], 0, None
    while total is None or offset < total:
        params = {"resource_id": dataset_id, "limit": page_size, "offset": offset}
        result = _get(SEARCH_API, params=params).json()["result"]
        total = result["total"]
        batch = result["records"]
        if not batch:
            break
        records.extend(batch)
        offset += len(batch)
        print(f"  {offset}/{total} rows")
        time.sleep(0.5)  # be polite to the public API
    df = pd.DataFrame(records).astype(str)
    return df.drop(columns=["_id"], errors="ignore")


def fetch_dataset(name: str, out_dir: Path = RAW_DIR) -> Path:
    """Download one dataset by its short name (see config.DATASETS)."""
    dataset_id = DATASETS[name]
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{name}.csv"
    print(f"Fetching {name} ({dataset_id})")
    try:
        df = fetch_bulk(dataset_id)
    except Exception as err:  # noqa: BLE001 - any failure -> use fallback
        print(f"  bulk download failed ({err}); paging instead")
        df = fetch_paged(dataset_id)
    df.to_csv(out_path, index=False, encoding="utf-8")
    print(f"  saved {len(df):,} rows -> {out_path}")
    return out_path


def fetch_all() -> None:
    """Fetch every dataset; a failed download keeps any previous copy."""
    for name in DATASETS:
        try:
            fetch_dataset(name)
        except requests.RequestException as err:
            print(f"  {name}: download failed ({err}); using existing file if there is one")


if __name__ == "__main__":
    fetch_all()
