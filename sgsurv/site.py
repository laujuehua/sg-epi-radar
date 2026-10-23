"""Collect the rendered dashboard into a portable static site and ZIP."""
import shutil
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from .config import ROOT


def collect(root=ROOT):
    root=Path(root)
    dashboard=root / "dashboard"
    if not (dashboard / "index.html").is_file():
        raise FileNotFoundError("Render dashboard/index.qmd before collecting the site")
    site=root / "_site"
    site.mkdir(exist_ok=True)
    for name in ["index.html","app.js","styles.css"]:
        shutil.copyfile(dashboard / name,site / name)
    for name in ["index_files","chart-assets"]:
        source=dashboard / name
        if source.exists():
            shutil.copytree(source,site / name,dirs_exist_ok=True)
    archive=root / "sg-epi-radar-site.zip"
    with ZipFile(archive,"w",ZIP_DEFLATED) as output:
        for path in sorted(site.rglob("*")):
            if path.is_file():
                output.write(path,path.relative_to(site).as_posix())
    return site


if __name__=="__main__":
    print(f"Static site ready: {collect()}")
