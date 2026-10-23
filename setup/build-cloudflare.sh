#!/usr/bin/env bash
# Cloudflare Workers Builds: render the committed data snapshot without refetching.
set -euo pipefail
cd "$(dirname "$0")/.."

build_dir="$PWD/.cloudflare-build"
mkdir -p "$build_dir"
python3 -m venv "$build_dir/venv"
export QUARTO_PYTHON="$build_dir/venv/bin/python"
"$QUARTO_PYTHON" -m pip install -r requirements.txt

quarto_version="1.10.18"
quarto_dir="$build_dir/quarto-$quarto_version"
if [[ ! -x "$quarto_dir/bin/quarto" ]]; then
  archive="$build_dir/quarto.tar.gz"
  curl --fail --location --retry 3 \
    "https://github.com/quarto-dev/quarto-cli/releases/download/v${quarto_version}/quarto-${quarto_version}-linux-amd64.tar.gz" \
    --output "$archive"
  "$QUARTO_PYTHON" - "$archive" <<'PY'
import hashlib, sys
from pathlib import Path
actual=hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest()
expected="afad071b5bd22c02f2d300695743189d3650e0537a53073e654b630cff2b0c73"
if actual != expected:
    raise SystemExit("Quarto download checksum mismatch")
PY
  tar -xzf "$archive" -C "$build_dir"
fi

"$QUARTO_PYTHON" -m sgsurv.assets
"$quarto_dir/bin/quarto" render dashboard/index.qmd
"$QUARTO_PYTHON" -m sgsurv.site
