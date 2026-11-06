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
