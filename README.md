# SG Epi Radar

The **Illness explorer** provides a standalone weekly chart with illness, respiratory/all-illness, data-source and date filters. School vacation and closure shading can be toggled; hover and CSV exports include calendar context. Polyclinic average daily attendances and notified weekly cases remain separate, with explicit units. Singapore school-calendar coverage is curated for 2012–2026; future unshaded dates are unknown, not assumed school days. Primary-school-only special days are excluded from the default shading, and overlaps are descriptive rather than causal evidence.

The regional tab supports country selection, Singapore comparison and common influenza periods; TB charts omit empty historical years. Secondary charts load when their tab opens. The library supports search and family/coverage filters, with recent stored-row previews. The homepage distinguishes observation coverage, source-check times, processing time and site-build time, and collapses detailed signal tables.

**Briefing** combines WHO Disease Outbreak News with health-keyword-filtered CNA RSS headline links and clearly identified curated links. Only linked titles, attribution and publication dates are retained, not article text. Feeds refresh with the data workflow; failures retain cached items and remain visible. Geographic/topic labels are approximate, and feed coverage is incomplete. The **Pathogen reference** starts with eight sourced cards (influenza, measles, pertussis, HFMD, chickenpox, mumps, dengue and salmonellosis), checked 23 October 2026. Syndrome labels are explicitly distinguished from aetiological diagnoses; other illnesses show a link to WHO topics instead of invented clinical fields. Related WHO notices are the latest matching records in the retained feed, not a claim to list every current advisory.

## To do and future development

Initial briefing and reference features are implemented; remaining work includes broader publisher coverage, additional clinician-reviewed pathogen cards and better regional outbreak classification.

- **Singapore and regional news:** include relevant news articles about infectious diseases in Singapore and Southeast Asia, with publication dates, source links and country/pathogen tags.
- **Important global outbreaks:** highlight significant outbreaks worldwide, with clear geographic scope, event dates and links to official reporting such as WHO Disease Outbreak News. Distinguish official advisories from media coverage.
- **Pathogen wiki:** add a quick reference for the selected virus, bacterium or other pathogen, covering the disease overview, symptoms, incubation period, infectious period, transmission routes and the latest relevant WHO advisories. Cite authoritative sources, show when information was checked, and distinguish established reference facts from evolving outbreak guidance.

The **Southeast Asia** tab covers all 11 geographic Southeast Asian countries. Weekly influenza charts use WHO FluNet sentinel reporting only, with A+B positivity and explicit missing weeks. A separate annual TB chart uses WHO estimates distributed through World Bank WDI (`SH.TBS.INCD`, CC BY 4.0). Country coverage dates differ; neither dataset is a comprehensive regional outbreak feed. Regional sources refresh with `python -m sgsurv.extra_data --groups flunet regional` and the scheduled workflow.

### Publish with Cloudflare Workers and GitHub

The current Cloudflare **Create an app** screen offers **Continue with GitHub** and **Upload your static files**. Pages appears separately as a legacy workflow. This project uses a GitHub-linked **Worker with static assets**, named `sg-epi-radar`. The agreed public address is `https://sg-epi-radar.laujuehua.workers.dev`; the account subdomain is intentionally retained.

For the existing linked Worker, open **Settings → Build** and configure:

| Setting | Value |
|---|---|
| Repository | `laujuehua/sg-epi-radar` |
| Production branch | `main` |
| Root directory | Repository root (`/`) |
| Build command | `bash setup/build-cloudflare.sh` |
| Deploy command | `npx wrangler deploy` |

Save the settings and retry the latest deployment. No ZIP upload is needed for this GitHub integration. `wrangler.jsonc` names the Worker and publishes only `_site`. The build script installs Python dependencies and a pinned, checksum-verified Quarto release, renders the committed data snapshot and assembles the static site. It does not fetch new observations during a Cloudflare build or access the original OneDrive project. Cloudflare's GitHub integration supplies deployment authentication; the earlier Pages API-token/variable instructions do not apply.

GitHub Actions handles scheduled public-data refreshes, tests and validation. It commits refreshed tables to `main`; Cloudflare builds the repository snapshot for hosting. Each successful Actions build also retains `sg-epi-radar-site.zip` as a portable artifact. GitHub Pages stays optional and disabled unless `ENABLE_GITHUB_PAGES=true` is explicitly set.

Workers addresses use `<worker-name>.<account-subdomain>.workers.dev`. The account subdomain can be changed from **Workers & Pages → Your subdomain → Change**, but this affects all Workers in the account. The standard Worker URL cannot be shortened to `sg-epi-radar.workers.dev`. See [Workers Builds configuration](https://developers.cloudflare.com/workers/ci-cd/builds/configuration/), [static assets](https://developers.cloudflare.com/workers/static-assets/binding/) and [workers.dev addresses](https://developers.cloudflare.com/workers/configuration/routing/workers-dev/).

An automated surveillance pipeline and dashboard built on Singapore open data:

- **Outbreak signal detection** on MOH's weekly notifiable disease counts, using seasonal *historical limits* and the CDC's *EARS C2* method, written out in plain pandas so each step is visible.
- **Haze and respiratory illness**: NEA's 24-hour PSI next to MOH polyclinic attendances for acute upper respiratory tract infections (URTI), covering the 2015 and 2019 haze episodes.
- **Optional AI situation summary**: a short weekly write-up drafted by Claude from the computed figures only, labelled as AI-drafted.
- **Automation**: GitHub Actions refreshes and validates data every Monday; the GitHub-linked Cloudflare Worker builds and hosts the dashboard.

> Public app address: `https://sg-epi-radar.laujuehua.workers.dev` (deployment must complete before the dashboard is available).

## Data

| Dataset | Publisher | Coverage | Used for |
|---|---|---|---|
| [Weekly Infectious Disease Bulletin Cases](https://data.gov.sg/datasets/d_ca168b2cb763640d72c4600a68f9909e/view) | MOH | 2012 to 2022, weekly | Signal detection (history) |
| [Average Daily Polyclinic Attendances for Selected Diseases](https://data.gov.sg/datasets/d_5d5508f1c954f5630d7b3aa7875d01f9/view) | MOH | 2012 to 2022, weekly | URTI vs haze |
| [CDA Weekly Infectious Diseases Bulletin](https://www.cda.gov.sg/resources/weekly-infectious-diseases-bulletin-2026/) (yearly Excel) | CDA | 2023 onwards, weekly; current year updated weekly | Signal detection + polyclinic URTI |
| [Historical 24-hr PSI](https://data.gov.sg/datasets/d_b4cf557f8750260d229c49fd768e11ed/view) | NEA | Apr 2014 onwards, hourly by region | Haze |

All are under the Singapore Open Data Licence.

## Project structure

```
sg-epi-radar/
├── sgsurv/                 # Python package
│   ├── config.py           # dataset IDs, paths, detection settings
│   ├── fetch.py            # download from data.gov.sg (bulk API, falls back to paging)
│   ├── fetch_cda.py        # download CDA yearly bulletin Excel files (2023 onwards)
│   ├── clean.py            # epi weeks, tidy tables, PSI hourly -> weekly
│   ├── detect.py           # EARS C2 + historical limits
│   ├── ai_summary.py       # optional Claude-drafted summary
│   └── pipeline.py         # runs everything: python -m sgsurv.pipeline
├── dashboard/index.qmd     # Quarto dashboard (3 pages)
├── tests/                  # pytest unit tests
├── data/raw/               # downloads (git-ignored)
├── data/processed/         # outputs the dashboard reads (committed)
├── setup/                  # copied into place by setup/install_config.py:
│   ├── vscode/             #   -> .vscode/ (run/debug configs, tasks, extensions)
│   └── github-workflows/   #   -> .github/workflows/ (weekly refresh + static build)
```

## Run it in VS Code (Windows)

You need **Python 3.10+**, **Quarto** (https://quarto.org/docs/get-started/) and **Git**.

1. Open this folder in VS Code (*File → Open Folder*).
2. Open a terminal (*Terminal → New Terminal*) and create a virtual environment:

   ```powershell
   py -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

   If PowerShell blocks the activate script, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then try again.
   When VS Code asks, select `.venv` as the interpreter (or *Ctrl+Shift+P → Python: Select Interpreter*).

   Then install the VS Code settings and GitHub workflow (one-off; creates `.vscode/` and `.github/workflows/` from the `setup/` folder):

   ```powershell
   python setup/install_config.py
   ```

   Reload the window and accept the recommended extensions (Python, Jupyter, Quarto).

3. Run the pipeline. Either press **F5** and pick *Pipeline: download data + process*, or in the terminal:

   ```powershell
   python -m sgsurv.pipeline
   ```

   This downloads the three datasets into `data/raw/` and writes the processed tables to `data/processed/`. Later runs can skip the download with `--skip-fetch`.

   Bulletin data comes from two places: data.gov.sg for 2012–2022 and the Communicable Diseases Agency's yearly Excel files for 2023 onwards (saved in `data/raw/cda/`). The pipeline downloads both; to fetch only the CDA files, run `python -m sgsurv.fetch_cda`. Excel files you download by hand can go in `data/raw/` or `data/raw/cda/`.

4. Preview the dashboard: *Terminal → Run Task → Preview dashboard*, or

   ```powershell
   python -m sgsurv.assets
   quarto preview dashboard/index.qmd
   ```

   If Quarto picks up the wrong Python, set it for the session: `$env:QUARTO_PYTHON = ".venv\Scripts\python.exe"`.

5. Run the tests from the Testing panel (flask icon) or `python -m pytest`.

### Optional keys

Copy `.env.example` to `.env` and fill in either key. VS Code's run configurations load `.env` automatically.

- `DATA_GOV_SG_API_KEY`: higher rate limits on data.gov.sg. Works without one.
- `ANTHROPIC_API_KEY`: turns on the AI summary (`python -m sgsurv.pipeline --skip-fetch --ai`). Without it the step is skipped.

## Publish on GitHub

```powershell
git init
git add .
git commit -m "Initial surveillance pipeline and dashboard"
git branch -M main
git remote add origin https://github.com/laujuehua/sg-epi-radar.git
git push -u origin main
```

Then on GitHub:

1. Connect `laujuehua/sg-epi-radar` to the Cloudflare Worker and apply the build settings above.
2. Optional: *Settings → Secrets and variables → Actions* → add `DATA_GOV_SG_API_KEY` and/or `ANTHROPIC_API_KEY`.
3. *Actions → Update dashboard → Run workflow* for the first build. After that it runs every Monday at 09:00 SGT and on every push to `main`.
4. Retry the latest Cloudflare build after saving its build command and deploy command.

## Methods

**Epi weeks.** MOH weeks run Sunday to Saturday. Weeks are numbered with the MMWR convention (week 1 is the first Sunday–Saturday week with at least 4 days in the new year) and dated by their Sunday. Weeks missing for a disease inside its reporting period remain unavailable (`missing_observation`), distinct from reported zeros. Missing values are excluded from seasonal baselines; EARS C2 requires seven observed baseline weeks.

**Historical limits (primary signal).** For each week, the expected count is the mean of the same week ±1 week in each of the previous 5 years (up to 15 values, at least 9 required). A signal is raised when cases exceed mean + 2 SD. 2020 and 2021 are left out of baselines because COVID-19 measures changed both transmission and reporting (configurable in `config.py`).

**EARS C2.** Compares each week with the mean and SD of 7 weeks ending 3 weeks earlier; threshold mean + 3 SD. It reacts quickly but rises with every seasonal upswing of common diseases, so it only raises signals where there is not yet a seasonal baseline. Its threshold is still drawn on the chart.

No signal is raised below 5 cases a week. A signal is a prompt to look closer, not a confirmed outbreak.

**PSI.** The national value for each hour is the highest of the five regional 24-hr PSI readings. Weekly figures use each day's peak; a *haze week* has a daily peak above 100 (NEA's "unhealthy" band).

**PSI vs URTI.** Shown side by side with Spearman correlations at 0 to 3 calendar-week lags. Incomplete PSI weeks are excluded and calendar gaps are preserved. This is descriptive: both series are seasonal and influenza drives most URTI variation.

## Limitations and next steps

- Disease names differ between data.gov.sg and CDA; they are matched in `clean.py` (`_ALIASES`). After each run, `data/processed/disease_names.csv` lists which source(s) each disease comes from, so unmatched names are easy to spot. HFMD notifications stop after 2022 because CDA's table no longer includes them (polyclinic HFMD attendances continue).
- Recent weeks in the current year's CDA file are provisional and can be revised.
- Signal thresholds have not been tuned against known outbreaks. A next step is to evaluate sensitivity and timeliness against documented events (e.g. the 2020 dengue season).
- A distributed-lag time-series regression (adjusting for seasonality and influenza) would give a proper estimate of the haze–respiratory association.
- Epi-week dates should be spot-checked against a few MOH PDF bulletins.

## About

SG Epi Radar brings together public infectious disease surveillance and contextual data for Singapore.

## Dashboard improvements

The overview separates latest-week signals from eight-week disease-week signals, shows exact source coverage and processing time, and distinguishes currently reported diseases from historical series. Disease charts start with one year of data and provide date controls, expected values, signal links, and missing-observation markers. The haze page includes 2015/2019 shortcuts, period-specific correlations, coverage dates, and accessible data tables.

The weekly situation summary always comes from computed figures. Optional AI commentary is displayed only when its snapshot identifier matches the current bulletin and PSI data. AI failures do not block the dashboard.

CDA file precedence is explicit: downloaded `data/raw/cda/` files precede manual files in `data/raw/`; newer modification times win within each folder, with filename as a tie-breaker. Conflicting disease-week values raise warnings. `metadata.json` records the ordered source files and snapshot identifier. File timestamps represent local copies, not independently verified publisher revision dates.

Run `python -m sgsurv.validate` to check processed data. Publication rejects duplicates, negative cases, invalid PSI coverage, backwards coverage dates, and a drop exceeding 10% in latest-week disease coverage versus the previous snapshot. Incomplete PSI weeks are recorded in quality notes. CI renders and validates before committing refreshed data and deploying.

Freshness uses a transparent 14-day allowance after each reporting week ends. It highlights older coverage without claiming the source publisher has missed a release.

## Disease explorer, saved views and retrospective evaluation

The selected disease now includes its latest count, previous-week change, expected value, applicable threshold, reporting coverage, and an explanation of its signal state. Signal episodes count consecutive above-threshold weeks and reset on a non-signal, missing observation, or missing calendar week. The seasonal view overlays epidemiological weeks for the most recent six or three reporting years, or all available years, retaining gaps and marking 2020–2021 with dotted lines.

Date controls filter the disease chart and CSV export together. View links preserve the disease, dates, seasonal year range, haze/scatter periods and evaluation selection in URL parameters; the fragment preserves the page. Named saved views use local browser storage. A localhost link is usable only on the machine hosting the app.

`data/processed/revision_history.json` retains comparisons between distinct processing snapshots, including changed counts, missing-to-observed transitions, and added/removed rows. This begins with the first locally retained comparison and cannot reconstruct earlier publisher revisions. Identical snapshots do not create duplicate history entries.

The evaluation page compares current rules with two independently sourced historical anchors: NEA's account of the rise in dengue since early May 2020, and the reported recognition of local Zika transmission on 27 August 2016. `data/reference/outbreak_events.json` records source URLs, anchor precision and the analyst-defined eight-week windows. Metrics include evaluable weeks, first signal within the window and weeks after the anchor, and unclassified signal-weeks outside the window in that disease/year. These are retrospective selected-event comparisons, not estimates of general sensitivity, false-positive rate or real-time detection delay. No threshold tuning is performed.

Theme and browser interactions live in `dashboard/styles.css` and `dashboard/app.js`. The publication workflow includes both files and generated `chart-assets/`.

Desktop cards use content-sized rows, with the disease chart beside its details and export/save controls collapsed by default. UI assets use content hashes to avoid stale browser caches. Run `python -m sgsurv.assets` before a fresh Quarto preview/render; CI does this automatically.

## Supplementary data library

The IDE5011 public-data acquisition and cleaning recipes have been extracted into this project's Python pipeline. The one-time import retained 46 files (28 raw inputs, 14 processed snapshots, three acquisition/cleaning recipes and their README), with SHA-256 verification. The original project was opened read-only and its whole-tree checksums matched before and after copying. Its files are never needed for routine refreshes.

Run from this project folder:

```powershell
& "$env:LOCALAPPDATA\Python\bin\python.exe" -m sgsurv.extra_data
```

This downloads public sources into `data/extra/raw`, rebuilds 19 tables in `data/extra/processed`, and writes `data/extra/catalog.json` with coverage, units, missing values, hashes and refresh results. Use `--skip-fetch` to rebuild offline, or `--groups data_gov flunet` to refresh selected families. Set the optional `DATA_GOV_SG_API_KEY` environment variable for authenticated data.gov.sg access; it is sent only to that API host. Requests are paced and retried. Last good cache files are retained when a source fails, with an explicit failure/partial status. Publication fails if required data cannot be rebuilt.

The library includes notifications, polyclinic attendances, daily PSI and weather, monthly humidity, population by age, contact matrices, school/public holidays, vaccination survey coverage, visitors, mortality, Singapore sentinel influenza and regional FluNet. The **Data library** dashboard tab provides previews and complete CSV downloads. All tables are retained for review; existing charts retain their current inputs until datasets are selected for them.

The school calendar, historical public holidays and vaccination survey observations are dated curated references in `data/reference/ide5011`. They are not automatically invented or interpolated when a new year appears. Missing observations remain missing. FluNet reporting sources stay separate in the source table; specimen positives are not population infections. Visitor totals overlap with country/region rows, and population totals must not be summed across ages. Contact matrices are synthetic estimates from [Prem et al.'s upstream repository](https://github.com/kieshaprem/synthetic-contact-matrices), distributed under GPL-3.0; retain that attribution and follow source licences when redistributing.

When PSI bulk history overlaps the real-time cache, the bulk observations take priority. Disagreements are counted in the catalogue and shown beside the PSI preview; both raw versions remain available locally. The imported Chickenpox 2014-W52 duplicate (14, 19) is reconciled to weeks 52 and 53 in derived data only, and the known malformed historical PSI midnight timestamp is repaired during parsing.

Original copies and working raw downloads are ignored by Git. The verified local snapshot lives at `data/imported/ide5011`, including its manifest and the source recipes. Refreshes archive changed raw files by hash. The GitHub repository is configured for a Monday refresh of supplementary sources, rebuilding the library and its downloads. Cloudflare hosting uses the GitHub-linked Worker and the build settings above.
