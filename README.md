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
