"""
Runs the full pipeline and renders all three outputs:
  - dashboard.html   (visual dashboard)
  - report.txt       (plain text business report)
  - alert_email.txt  (draft email body, only written if new anomalies found)
  - alerts_log.csv   (persistent log, appended to by anomaly_pipeline.py)

Usage:
  python3 generate_outputs.py sample_metrics.csv date revenue,signups,churn_rate,active_users
"""

import csv
import json
import sys
from datetime import datetime

from anomaly_pipeline import run_pipeline


def render_dashboard(result: dict, template_path: str, out_path: str):
    rows = result["clean_rows"]
    metric_cols = result["metric_cols"]

    series = {
        c: {
            "dates": [r["__date"].strftime("%Y-%m-%d") for r in rows],
            "values": [r[c] for r in rows],
        }
        for c in metric_cols
    }

    anomalies_payload = [
        {**{k: v for k, v in a.__dict__.items()}, "summary": s}
        for a, s in zip(result["anomalies"], result["summaries"])
    ]

    data_payload = {
        "series": series,
        "anomalies": anomalies_payload,
        "clean_report": result["clean_report"].__dict__,
        "new_alert_count": result["new_alert_count"],
    }

    # full log for the log table
    log_rows = []
    try:
        with open("alerts_log.csv", newline="", encoding="utf-8") as f:
            log_rows = list(csv.DictReader(f))
    except FileNotFoundError:
        pass

    with open(template_path, encoding="utf-8") as f:
        template = f.read()

    html = template.replace("__DATA_JSON__", json.dumps(data_payload)).replace(
        "__LOG_JSON__", json.dumps(log_rows)
    )

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)


def render_text_report(result: dict, out_path: str):
    lines = []
    lines.append("=" * 60)
    lines.append("METRIC WATCH — ANOMALY REPORT")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 60)
    lines.append("")

    cr = result["clean_report"]
    lines.append("DATA QUALITY")
    lines.append(f"  Rows in / out:        {cr.rows_in} -> {cr.rows_out}")
    lines.append(f"  Duplicate rows removed: {cr.duplicates_removed}")
    lines.append(f"  Unparseable dates dropped: {cr.dropped_unparseable_dates}")
    for col, n in cr.missing_filled.items():
        if n:
            lines.append(f"  Missing values filled in '{col}': {n}")
    lines.append("")

    anomalies = result["anomalies"]
    summaries = result["summaries"]
    lines.append(f"ANOMALIES FLAGGED: {len(anomalies)}")
    lines.append("-" * 60)
    if not anomalies:
        lines.append("  None. All metrics within normal baseline range.")
    for a, s in zip(anomalies, summaries):
        lines.append(f"\n[{a.severity.upper()}] {a.date} — {a.metric}")
        lines.append(f"  {s['headline']}")
        lines.append(f"  {s['confidence']}")
        lines.append(f"  Impact: {s['impact']}")
    lines.append("")
    lines.append("-" * 60)
    lines.append(f"New alerts logged this run: {result['new_alert_count']}")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def render_alert_email(result: dict, out_path: str) -> bool:
    """Only writes a file if there are severe anomalies from THIS run's fresh alerts."""
    anomalies = result["anomalies"]
    summaries = result["summaries"]
    severe = [(a, s) for a, s in zip(anomalies, summaries) if a.severity == "severe"]

    if not severe or result["new_alert_count"] == 0:
        return False

    lines = []
    lines.append(f"Subject: [Anomaly Alert] {len(severe)} severe metric deviation(s) detected\n")
    lines.append("Hi team,\n")
    lines.append("The metric monitor flagged the following severe anomalies:\n")
    for a, s in severe:
        lines.append(f"• {a.date} — {a.metric}: {s['headline']}")
        lines.append(f"  {s['impact']}\n")
    lines.append("Full dashboard attached / linked. Log of all past alerts is in alerts_log.csv.\n")
    lines.append("— Automated Metric Watch")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return True


if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "sample_metrics.csv"
    date_col = sys.argv[2] if len(sys.argv) > 2 else "date"
    metric_cols = (
        sys.argv[3].split(",")
        if len(sys.argv) > 3
        else ["revenue", "signups", "churn_rate", "active_users"]
    )

    result = run_pipeline(
        csv_path=csv_path,
        date_col=date_col,
        metric_cols=metric_cols,
        window=7,
        z_threshold=2.0,
        pct_threshold=0.20,
        alert_log_path="alerts_log.csv",
    )

    render_dashboard(result, "dashboard_template.html", "dashboard.html")
    render_text_report(result, "report.txt")
    emailed = render_alert_email(result, "alert_email.txt")

    print(f"Anomalies flagged: {len(result['anomalies'])}")
    print(f"New alerts logged: {result['new_alert_count']}")
    print(f"Email draft written: {emailed}")
    print("Outputs: dashboard.html, report.txt, alerts_log.csv" + (", alert_email.txt" if emailed else ""))
