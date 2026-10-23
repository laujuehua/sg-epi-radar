"""Copy the VS Code settings and GitHub Actions workflow into place.

Run once from the project folder:
    python setup/install_config.py

Creates .vscode/ (run/debug configs, tasks, recommended extensions) and
.github/workflows/update-dashboard.yml. Existing files are left alone.
"""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "setup"
COPIES = [(SETUP / "vscode", ROOT / ".vscode"),
          (SETUP / "github-workflows", ROOT / ".github" / "workflows")]

for src_dir, dest_dir in COPIES:
    dest_dir.mkdir(parents=True, exist_ok=True)
    for src in src_dir.iterdir():
        dest = dest_dir / src.name
        if dest.exists():
            print(f"skip   {dest.relative_to(ROOT)} (already exists)")
        else:
            shutil.copy2(src, dest)
            print(f"create {dest.relative_to(ROOT)}")
print("Done. Reload VS Code (Ctrl+Shift+P > Developer: Reload Window) to pick up the settings.")

