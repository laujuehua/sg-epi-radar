"""Prepare versioned UI assets before Quarto resolves its include files."""
import hashlib
import re
from pathlib import Path


def prepare():
    dashboard = Path(__file__).resolve().parents[1] / "dashboard"
    assets = dashboard / "chart-assets"
    assets.mkdir(exist_ok=True)
    for source, include, kind in [("styles.css", "ui-styles.html", "style"), ("app.js", "ui-script.html", "script")]:
        content = (dashboard / source).read_bytes()
        digest = hashlib.sha256(content).hexdigest()[:12]
        name = f"{Path(source).stem}-{digest}{Path(source).suffix}"
        (assets / name).write_bytes(content)
        tag = f'<link rel="stylesheet" href="chart-assets/{name}">' if kind == "style" else f'<script src="chart-assets/{name}"></script>'
        (assets / include).write_text(tag, encoding="utf-8")
        # A UI-only edit can refresh an existing local build without rerunning data cells.
        index = dashboard / "index.html"
        if index.exists():
            html = index.read_text(encoding="utf-8")
            pattern = rf"chart-assets/{re.escape(Path(source).stem)}-[0-9a-f]{{12}}{re.escape(Path(source).suffix)}"
            updated = re.sub(pattern, f"chart-assets/{name}", html)
            if updated != html:
                index.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    prepare()
