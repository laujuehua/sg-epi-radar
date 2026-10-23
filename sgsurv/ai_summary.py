"""Optional: draft a short situation summary with an LLM (Claude API).

The model only sees numbers this pipeline has already computed (recent
alerts and PSI), and is told to use nothing else. The output is labelled as
AI-drafted in the dashboard so readers know a human should check it.

Skipped automatically when ANTHROPIC_API_KEY is not set, so the rest of the
pipeline never depends on it.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .config import PROCESSED_DIR

DEFAULT_MODEL = "claude-sonnet-5-5"
OUT_PATH = PROCESSED_DIR / "ai_summary.md"


def prune_stale_summary(snapshot_id: str, out_path: Path = OUT_PATH) -> None:
    """Keep commentary only when its recorded snapshot matches the current data."""
    sidecar = out_path.with_suffix(".json")
    try:
        saved = json.loads(sidecar.read_text(encoding="utf-8"))
        matches = isinstance(saved, dict) and saved.get("snapshot_id") == snapshot_id
    except (OSError, ValueError):
        matches = False
    if not matches:
        out_path.unlink(missing_ok=True)
        sidecar.unlink(missing_ok=True)

SYSTEM_PROMPT = """You are an infectious disease surveillance analyst in Singapore writing \
the weekly situation summary for a public dashboard.

Rules:
- Use ONLY the figures in the JSON provided. Do not add outside facts, \
case counts, or explanations of cause.
- Statistical alerts are signals for follow-up, not confirmed outbreaks. Say so.
- Mention data limitations if relevant (e.g. data end date).
- If PSI and respiratory data are given, describe them side by side without \
claiming one caused the other.
- Plain English, under 200 words, 3 short paragraphs, no headings, no bullet points."""


def build_context(alerts: pd.DataFrame, psi_recent: pd.DataFrame, data_through: str) -> dict:
    return {
        "data_through_week_starting": data_through,
        "alerts_last_8_weeks": alerts.assign(
            week_start=alerts["week_start"].astype(str)
        ).to_dict(orient="records"),
        "psi_last_8_weeks": psi_recent.assign(
            week_start=psi_recent["week_start"].astype(str)
        ).to_dict(orient="records"),
        "method_note": "c2 = EARS C2 (recent 7-week baseline); hl = historical limits "
                       "(same season in previous years).",
    }


def write_summary(context: dict, out_path: Path = OUT_PATH) -> Path | None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("AI summary skipped: ANTHROPIC_API_KEY not set")
        return None
    try:
        import anthropic
    except ImportError:
        print("AI summary skipped: `pip install anthropic` to enable")
        return None

    client = anthropic.Anthropic()
    model = os.environ.get("SGSURV_MODEL", DEFAULT_MODEL)
    message = client.messages.create(
        model=model,
        max_tokens=600,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(context, default=str)}],
    )
    text = "".join(block.text for block in message.content if block.type == "text").strip()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out_path.write_text(
        f"{text}\n\n*AI-drafted by {model} on {stamp} from the figures on this dashboard. "
        f"Check against the charts before quoting.*\n",
        encoding="utf-8",
    )
    print(f"AI summary -> {out_path}")
    return out_path
