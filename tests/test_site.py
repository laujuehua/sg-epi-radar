from zipfile import ZipFile

from sgsurv.site import collect


def test_site_package_has_root_index_and_excludes_project_private_files(tmp_path):
    dashboard=tmp_path / "dashboard"
    dashboard.mkdir()
    for name in ["index.html","app.js","styles.css"]:
        (dashboard / name).write_text("public asset")
    (dashboard / "chart-assets").mkdir()
    (dashboard / "chart-assets" / "dataset.csv").write_text("date,value\n2026-01-01,1\n")
    (tmp_path / ".env").write_text("SECRET=private")
    (dashboard / "index.qmd").write_text("private source notes")
    collect(tmp_path)
    with ZipFile(tmp_path / "sg-epi-radar-site.zip") as archive:
        assert set(archive.namelist())=={"index.html","app.js","styles.css","chart-assets/dataset.csv"}
