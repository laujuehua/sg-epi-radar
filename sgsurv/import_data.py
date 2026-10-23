"""Copy public-data inputs read-only from another project into this workspace."""
import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def import_project(source, destination=None):
    source = Path(source).resolve(strict=True)
    destination = Path(destination or ROOT / "data" / "imported" / "ide5011").resolve()
    if destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError("Import destination must be separate from the source project")
    if not destination.is_relative_to(ROOT.resolve()):
        raise ValueError("Imports must stay inside this dashboard workspace")
    # Hash the source tree before and after: no original file is opened for writing.
    originals = sorted(p for p in source.rglob("*") if p.is_file())
    before = {str(p.relative_to(source)): sha256(p) for p in originals}
    selected = []
    for folder, category in [("raw data", "raw"), ("processed data", "processed")]:
        selected.extend((p, category / Path(p.name)) for p in (source / folder).iterdir() if p.is_file())
    selected.extend((source / "scripts" / name, Path("recipes") / name) for name in
                    ["download_extra_data.R", "process_extra_data.R", "combine_surveillance_data.R"])
    selected.append((source / "README.txt", Path("recipes") / "SOURCE_README.txt"))
    files = []
    for original, relative in selected:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        original_hash = before[str(original.relative_to(source))]
        if target.exists() and sha256(target) != original_hash:
            raise ValueError(f"Immutable imported snapshot differs: {target}")
        if not target.exists():
            shutil.copyfile(original, target)
        if sha256(target) != original_hash:
            raise ValueError(f"Copy checksum mismatch: {relative}")
        files.append(dict(path=relative.as_posix(), source_path=str(original.relative_to(source)),
                          sha256=original_hash, bytes=original.stat().st_size))
    after = {str(p.relative_to(source)): sha256(p) for p in source.rglob("*") if p.is_file()}
    if before != after:
        raise RuntimeError("Source tree changed during import; inspect concurrent changes before using the snapshot")
    manifest = dict(imported_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    original_project=str(source), source_tree_unchanged=True,
                    source_tree_sha256=before, files=files)
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    result = import_project(args.source)
    print(f"Copied and verified {len(result['files'])} files; source tree unchanged.")


if __name__ == "__main__":
    main()
