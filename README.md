<<<<<<< HEAD
# Operational KPI & Delay Anomaly Detection Pipeline

An end-to-end Python pipeline that ingests raw daily supply chain metrics, cleans them,
flags unusual days against a rolling 7-day baseline, and explains each anomaly in plain
English. It also builds an interactive dashboard and keeps a de-duplicated alert log.

> **Data note:** the 45-day dataset is synthetic (`generate_data.py`). Three incidents are
> injected so the pipeline has known ground truth to find. Swap in your own CSV with the
> same columns to run it on real data.

## Results on the 45-day dataset

| Date | Metric | Change vs 7-day baseline | z-score | Severity |
|---|---|---|---|---|
| Oct 17 | Shipment volume | -48% | -8.4 | High |
| Oct 25 | Distribution delay | +129% | 18.3 | Critical |
| Nov 2 | Customer complaints | +230% | 24.1 | Critical |

On the same data, a z-score-only rule raises 18 alerts and a percent-change-only rule raises 6.
The dual-threshold rule raises exactly 3, with no manual review.

## How it works

1. **Ingest and clean** (`pipeline.clean`): parses dates, drops duplicate days, converts
   `N/A`/blank cells to numbers, rebuilds a gap-free daily calendar and interpolates short gaps.
2. **Baseline**: trailing 7-day mean and standard deviation per metric. The current day is
   excluded from its own baseline (`shift(1)`), so a spike cannot hide itself.
3. **Dual-threshold rule**: flag only if `|z| >= 2.0` **and** `|% change| >= 20%`.
   Z-score alone over-flags tiny moves in very steady metrics (on-time delivery); percent
   change alone over-flags ordinary swings in noisy ones.
4. **Summaries**: each alert gets direction, severity (Critical / High / Medium) and the likely
   operational impact, written for warehouse stakeholders.
5. **Alert log** (`output/alert_log.csv`): alerts are keyed by `sha1(date|metric)`, so re-running
   the pipeline never creates duplicates and history accumulates.
6. **Dashboard** (`output/dashboard.html`): self-contained, no server. Metric tabs, trend chart with
   baseline band, hover tooltips, clickable anomalies, filterable alert log.

## Run it

```bash
pip install -r requirements.txt
python generate_data.py        # creates data/raw_metrics.csv
python pipeline.py             # prints alerts, writes output/ (log, report, dashboard)
pytest                         # 6 tests
```

Open `output/dashboard.html` in a browser.

## Layout

```
generate_data.py          synthetic dataset with injected incidents
pipeline.py               clean, baseline, detect, summarize, alert log, report
dashboard.py              builds the dashboard from pipeline results
dashboard_template.html   dashboard markup, styles and charts
tests/test_pipeline.py    unit and end-to-end tests
```

## Tuning

Thresholds live at the top of `pipeline.py` (`Z_THRESHOLD`, `PCT_THRESHOLD`, `WINDOW_DAYS`).
Metric labels and impact text are in the `METRICS` dict.
=======
# Metric Watch — Anomaly Detection Pipeline

A small, explainable pipeline for monitoring business metrics day-to-day:
**Read → Clean → Baseline compare → Flag → Summarize → Output.**

## Files

| File | Purpose |
|---|---|
| `anomaly_pipeline.py` | Core library — all pipeline logic, no dependencies outside the standard library |
| `generate_outputs.py` | Runs the pipeline and renders the dashboard, text report, and alert email |
| `dashboard_template.html` | The dashboard's HTML/CSS/JS shell (data gets injected into it) |
| `make_sample_data.py` | Generates the synthetic demo dataset (`sample_metrics.csv`) |
| `sample_metrics.csv` | 45 days of demo data with 3 injected anomalies + messy formatting |
| `dashboard.html` | **Generated** — open this in a browser |
| `report.txt` | **Generated** — plain-text summary, good for logs/Slack |
| `alert_email.txt` | **Generated** — only appears when a *new* severe anomaly is found |
| `alerts_log.csv` | **Generated & persistent** — append-only history of every alert ever raised |

## Run it on your own data

```bash
python3 generate_outputs.py your_metrics.csv date_column_name metric1,metric2,metric3
```

- `your_metrics.csv` — any CSV with a date column and one or more numeric metric columns.
- `date_column_name` — the header name of your date column (e.g. `date`, `day`, `report_date`).
- The metric list is comma-separated, no spaces, matching your CSV headers exactly.

Example:
```bash
python3 generate_outputs.py your_metrics.csv date "revenue,orders,refunds"
```

Then open `dashboard.html` in a browser.

## How it works

1. **Read** — loads the CSV as-is.
2. **Clean** — parses dates (several formats tolerated), coerces numbers (strips `$`, `,`, `%`),
   forward-fills missing values, falls back to median for leading gaps, and drops duplicate dates
   (keeping the latest).
3. **Baseline** — for each metric, computes a rolling mean/std over the trailing 7 data points
   (configurable via `window=`). This adapts to trend/seasonality instead of comparing against one
   fixed historical average.
4. **Flag** — an anomaly requires **both** a z-score beyond threshold (default 2.0) **and** a percent
   change beyond threshold (default 20%). This avoids two failure modes: tiny moves in low-variance
   metrics producing huge z-scores, and noisy high-variance metrics producing false percent-change
   alarms.
5. **Summarize** — each anomaly is turned into a plain-English headline, a confidence note, and a
   business-impact note. Metrics like churn/cost/error rate are treated as "down is good," everything
   else defaults to "up is good" (see `INVERTED_METRICS_HINTS` in `anomaly_pipeline.py` — extend this
   list for your own metric names).
6. **Output** — an HTML dashboard, a plain-text report, an alert-email draft (only generated when a
   *new* severe anomaly appears), and an append-only CSV log that de-duplicates by `(date, metric)` so
   re-running the pipeline never double-logs the same alert.

## Tuning

All thresholds are parameters to `run_pipeline()` / arguments to `compare_and_flag()`:
- `window` — how many prior points form the baseline (default 7)
- `z_threshold` — minimum standard-deviations-from-baseline to flag (default 2.0)
- `pct_threshold` — minimum percent change from baseline to flag (default 0.20 = 20%)
- `severe_z` — z-score above which an anomaly is marked "severe" instead of "moderate" (default 3.5)

## What's stubbed vs. real

- **Email alert**: this generates the alert email *content* (`alert_email.txt`) but doesn't send it —
  wiring it to actual SMTP/SendGrid/etc. is a small addition once you have credentials.
- **Business summaries**: rule-based/templated, not LLM-generated — deterministic, fast, and free to
  run on every batch. Swapping in an LLM call for richer prose is a natural next step if you want it.
>>>>>>> 871df7f0f406c9c7c83081c04cc0d1f77892fe02
