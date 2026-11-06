"""
Anomaly Detection Pipeline
===========================
A small, explainable pipeline for business-metric monitoring:

  1. Read       - load a CSV of daily/periodic metrics
  2. Clean      - handle missing values, bad types, duplicate dates
  3. Baseline   - compute rolling mean/std per metric (the "normal" range)
  4. Flag       - z-score + percent-change based anomaly detection
  5. Summarize  - turn flagged anomalies into plain-English business summaries
  6. Output     - HTML dashboard, text report, and a persistent alert log (CSV)

Design choices (worth mentioning in an interview):
  - Uses a rolling baseline (not a single global mean) so seasonality/drift
    doesn't cause false positives.
  - Z-score AND percent-change are both checked, because a metric with tiny
    natural variance can produce huge z-scores from trivial moves, and a
    metric with huge variance can hide real percent swings.
  - The alert log is append-only and de-duplicated by (date, metric), so
    re-running the pipeline on the same data doesn't spam duplicate alerts.
"""

from __future__ import annotations
import csv
import json
import os
import statistics
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


# ----------------------------------------------------------------------
# 1. READ
# ----------------------------------------------------------------------

def read_csv(path: str) -> tuple[list[str], list[dict]]:
    """Read a CSV file into a list of dict rows. Returns (columns, rows)."""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        rows = list(reader)
    return columns, rows


# ----------------------------------------------------------------------
# 2. CLEAN
# ----------------------------------------------------------------------

@dataclass
class CleanReport:
    rows_in: int = 0
    rows_out: int = 0
    duplicates_removed: int = 0
    missing_filled: dict = field(default_factory=dict)   # column -> count
    coercion_failures: dict = field(default_factory=dict)  # column -> count
    dropped_unparseable_dates: int = 0


def clean_data(
    rows: list[dict],
    date_col: str,
    metric_cols: list[str],
) -> tuple[list[dict], CleanReport]:
    """
    - Parses the date column; drops rows where the date can't be parsed.
    - Coerces metric columns to float; missing/unparseable -> None (then filled).
    - Fills missing metric values via forward-fill, falling back to the
      column's overall median for any that remain (e.g. a leading gap).
    - Removes duplicate dates, keeping the last occurrence.
    """
    report = CleanReport(rows_in=len(rows))
    missing_filled = {c: 0 for c in metric_cols}
    coercion_failures = {c: 0 for c in metric_cols}

    parsed: list[dict] = []
    for row in rows:
        raw_date = (row.get(date_col) or "").strip()
        dt = _try_parse_date(raw_date)
        if dt is None:
            report.dropped_unparseable_dates += 1
            continue

        clean_row = {"__date": dt, date_col: raw_date}
        for col in metric_cols:
            val = row.get(col)
            num = _try_parse_float(val)
            if num is None:
                coercion_failures[col] += (1 if val not in (None, "") else 0)
            clean_row[col] = num
        parsed.append(clean_row)

    # Sort by date, drop duplicate dates (keep last)
    parsed.sort(key=lambda r: r["__date"])
    dedup: dict = {}
    for row in parsed:
        key = row["__date"]
        if key in dedup:
            report.duplicates_removed += 1
        dedup[key] = row  # keep last
    parsed = list(dedup.values())
    parsed.sort(key=lambda r: r["__date"])

    # Fill missing values: forward-fill, then median fallback
    for col in metric_cols:
        last_val = None
        for row in parsed:
            if row[col] is None:
                if last_val is not None:
                    row[col] = last_val
                    missing_filled[col] += 1
                # else: leave None for now, fix with median pass below
            else:
                last_val = row[col]

        col_values = [r[col] for r in parsed if r[col] is not None]
        median = statistics.median(col_values) if col_values else 0.0
        for row in parsed:
            if row[col] is None:
                row[col] = median
                missing_filled[col] += 1

    report.missing_filled = missing_filled
    report.coercion_failures = coercion_failures
    report.rows_out = len(parsed)
    return parsed, report


def _try_parse_date(s: str) -> Optional[datetime]:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _try_parse_float(v) -> Optional[float]:
    if v is None:
        return None
    s = str(v).strip().replace(",", "").replace("$", "").replace("%", "")
    if s == "" or s.lower() in ("nan", "none", "null", "n/a", "na"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ----------------------------------------------------------------------
# 3 & 4. BASELINE + FLAG
# ----------------------------------------------------------------------

@dataclass
class Anomaly:
    date: str
    metric: str
    value: float
    baseline_mean: float
    baseline_std: float
    z_score: float
    pct_change: float
    direction: str       # "up" or "down"
    severity: str         # "moderate" or "severe"


def compare_and_flag(
    rows: list[dict],
    metric_cols: list[str],
    window: int = 7,
    z_threshold: float = 2.0,
    pct_threshold: float = 0.20,
    severe_z: float = 3.5,
) -> list[Anomaly]:
    """
    Rolling-baseline anomaly detection.

    For each point (after the first `window` points warm up a baseline),
    compute the mean/std of the preceding `window` values, then flag if:
      - |z-score| >= z_threshold, AND
      - |percent change from baseline mean| >= pct_threshold

    Both conditions must hold, which avoids flagging trivial moves in
    low-variance metrics (huge z, tiny pct) and noisy moves in high-variance
    metrics (huge pct, tiny z).
    """
    anomalies: list[Anomaly] = []

    for col in metric_cols:
        series = [r[col] for r in rows]
        dates = [r["__date"] for r in rows]

        for i in range(window, len(series)):
            baseline_window = series[i - window:i]
            mean = statistics.mean(baseline_window)
            std = statistics.pstdev(baseline_window)
            value = series[i]

            if std == 0:
                # No variance in baseline; treat any change as a pct-based flag only
                z = float("inf") if value != mean else 0.0
            else:
                z = (value - mean) / std

            pct_change = (value - mean) / mean if mean != 0 else (0.0 if value == 0 else float("inf"))

            if abs(z) >= z_threshold and abs(pct_change) >= pct_threshold:
                severity = "severe" if abs(z) >= severe_z or abs(pct_change) >= pct_threshold * 2 else "moderate"
                anomalies.append(Anomaly(
                    date=dates[i].strftime("%Y-%m-%d"),
                    metric=col,
                    value=round(value, 4),
                    baseline_mean=round(mean, 4),
                    baseline_std=round(std, 4),
                    z_score=round(z, 3) if z != float("inf") else 999.0,
                    pct_change=round(pct_change * 100, 2) if pct_change != float("inf") else 999.0,
                    direction="up" if value > mean else "down",
                    severity=severity,
                ))

    anomalies.sort(key=lambda a: a.date)
    return anomalies


# ----------------------------------------------------------------------
# 5. INTELLIGENCE LAYER: business summaries
# ----------------------------------------------------------------------

# Metrics where an "up" move is bad news (costs, churn, error rates, etc.)
# Anything not listed here defaults to "up is good" (revenue, signups, etc.)
INVERTED_METRICS_HINTS = ("churn", "error", "cost", "refund", "complaint", "latency", "bounce", "cancel")


def _is_inverted(metric: str) -> bool:
    m = metric.lower()
    return any(hint in m for hint in INVERTED_METRICS_HINTS)


def generate_summary(anomaly: Anomaly) -> dict:
    """Turn one Anomaly into a plain-English business summary + impact note."""
    inverted = _is_inverted(anomaly.metric)
    good_move = (anomaly.direction == "up") != inverted  # XOR
    sentiment = "positive" if good_move else "concerning"

    metric_label = anomaly.metric.replace("_", " ")
    pct = abs(anomaly.pct_change)
    pct_str = f"{pct:.0f}%" if pct < 900 else "a very large amount"

    headline = (
        f"{metric_label.capitalize()} moved {anomaly.direction} {pct_str} on {anomaly.date}, "
        f"{'above' if anomaly.direction == 'up' else 'below'} its recent {7}-period baseline "
        f"of {anomaly.baseline_mean:g}."
    )

    if anomaly.severity == "severe":
        confidence = "This is a large, high-confidence deviation, unlikely to be normal noise."
    else:
        confidence = "This is a moderate deviation — worth a look, but could still be normal variation."

    impact_templates = {
        "positive": (
            f"If sustained, this could reflect a genuine improvement in {metric_label} "
            f"(e.g. a successful campaign, product change, or seasonal tailwind). "
            f"Consider identifying the driver so it can be repeated or scaled."
        ),
        "concerning": (
            f"If sustained, this could signal a problem worth investigating — "
            f"a broken funnel, a bad deploy, a pricing/billing issue, or an external shock. "
            f"Recommend checking recent changes (deploys, campaigns, pricing) around {anomaly.date}."
        ),
    }

    return {
        "headline": headline,
        "confidence": confidence,
        "impact": impact_templates[sentiment],
        "sentiment": sentiment,
    }


# ----------------------------------------------------------------------
# 6. OUTPUT: alert log
# ----------------------------------------------------------------------

def update_alert_log(anomalies: list[Anomaly], summaries: list[dict], log_path: str) -> int:
    """
    Append new anomalies to a persistent CSV log, de-duplicated by (date, metric).
    Returns the number of NEW alerts written (i.e. new anomalies found this run).
    """
    existing_keys = set()
    if os.path.exists(log_path):
        with open(log_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                existing_keys.add((row["date"], row["metric"]))

    new_rows = []
    for a, s in zip(anomalies, summaries):
        key = (a.date, a.metric)
        if key not in existing_keys:
            new_rows.append({
                "logged_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "date": a.date,
                "metric": a.metric,
                "value": a.value,
                "baseline_mean": a.baseline_mean,
                "pct_change": a.pct_change,
                "z_score": a.z_score,
                "direction": a.direction,
                "severity": a.severity,
                "sentiment": s["sentiment"],
                "headline": s["headline"],
            })
            existing_keys.add(key)

    if not new_rows:
        return 0

    file_exists = os.path.exists(log_path)
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        fieldnames = list(new_rows[0].keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerows(new_rows)

    return len(new_rows)


# ----------------------------------------------------------------------
# ORCHESTRATION
# ----------------------------------------------------------------------

def run_pipeline(
    csv_path: str,
    date_col: str,
    metric_cols: list[str],
    window: int = 7,
    z_threshold: float = 2.0,
    pct_threshold: float = 0.20,
    alert_log_path: str = "alerts_log.csv",
) -> dict:
    """Run the full pipeline and return everything needed to render outputs."""
    _, raw_rows = read_csv(csv_path)
    clean_rows, clean_report = clean_data(raw_rows, date_col, metric_cols)
    anomalies = compare_and_flag(clean_rows, metric_cols, window, z_threshold, pct_threshold)
    summaries = [generate_summary(a) for a in anomalies]
    new_alert_count = update_alert_log(anomalies, summaries, alert_log_path)

    return {
        "clean_rows": clean_rows,
        "clean_report": clean_report,
        "anomalies": anomalies,
        "summaries": summaries,
        "new_alert_count": new_alert_count,
        "metric_cols": metric_cols,
        "date_col": date_col,
    }
