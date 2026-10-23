import pandas as pd
import pytest
import json

from sgsurv import ai_summary


def test_build_context_is_json_ready():
    alerts = pd.DataFrame({"disease": ["HFMD"], "week_start": pd.to_datetime(["2022-12-11"]),
                           "cases": [1047.0]})
    psi = pd.DataFrame({"week_start": pd.to_datetime(["2022-12-11"]), "psi_max": [55]})
    ctx = ai_summary.build_context(alerts, psi, "2022-12-25")
    assert ctx["alerts_last_8_weeks"][0]["week_start"] == "2022-12-11"
    assert ctx["data_through_week_starting"] == "2022-12-25"


def test_skips_without_api_key(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = tmp_path / "summary.md"
    assert ai_summary.write_summary({}, out_path=out) is None
    assert not out.exists()


@pytest.mark.parametrize("saved", [None, "invalid json", json.dumps({"snapshot_id":"old"}), "[]"])
def test_stale_or_untracked_summary_is_removed(tmp_path, saved):
    out = tmp_path / "ai_summary.md"
    out.write_text("Older commentary")
    if saved is not None:
        out.with_suffix(".json").write_text(saved)
    ai_summary.prune_stale_summary("current", out)
    assert not out.exists()
    assert not out.with_suffix(".json").exists()


def test_matching_summary_is_preserved(tmp_path):
    out = tmp_path / "ai_summary.md"
    out.write_text("Current commentary")
    out.with_suffix(".json").write_text(json.dumps({"snapshot_id":"current"}))
    ai_summary.prune_stale_summary("current", out)
    assert out.read_text() == "Current commentary"
