"""Operational KPI & delay anomaly detection pipeline.

Stages: ingest -> clean -> rolling baseline -> dual-threshold detection
        -> plain-English summaries -> de-duplicated alert log -> report.

Detection rule (both must hold):
    |z-score vs trailing 7-day baseline| >= 2.0
    |percent change vs that baseline|    >= 20%

Usage:  python pipeline.py --input data/raw_metrics.csv
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

WINDOW_DAYS = 7
MIN_PERIODS = 5
Z_THRESHOLD = 2.0
PCT_THRESHOLD = 20.0
MAX_INTERPOLATION_GAP = 3

METRICS = {
    "shipment_volume": {
        "label": "Shipment volume",
        "unit": "orders/day",
        "down": "Fewer orders left the warehouse than normal. This usually points to a dock or "
                "labor shortfall, a warehouse system problem, or a gap in inbound stock. If it "
                "persists, expect an order backlog and late deliveries.",
        "up": "Order volume surged past normal. Pick, pack and carrier capacity may be strained, "
              "so watch for delays and overtime costs.",
    },
    "distribution_delay_hrs": {
        "label": "Distribution delay",
        "unit": "hrs",
        "down": "Delivery delays fell well below normal, which is favorable. Confirm it is not a "
                "reporting gap before treating it as a real improvement.",
        "up": "Shipments are taking much longer to clear the distribution network. Likely causes "
              "are carrier capacity limits, sorting backlogs or weather. Expect missed delivery "
              "promises and more customer contacts.",
    },
    "customer_complaints": {
        "label": "Customer complaints",
        "unit": "tickets/day",
        "down": "Complaints fell sharply. Check that ticket intake is working before treating "
                "this as a real improvement.",
        "up": "Customers are reporting problems at a much higher rate. This typically follows "
              "late, damaged or missing deliveries and puts refund and retention at risk.",
    },
    "on_time_delivery_pct": {
        "label": "On-time delivery",
        "unit": "%",
        "down": "Fewer orders arrived by their promised date, which hurts service-level targets.",
        "up": "More orders arrived on time than normal, which is favorable.",
    },
}


# ---------------------------------------------------------------- ingest/clean
def load_raw(path: str | Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str)


def clean(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Return a gap-free daily frame plus a log of what was fixed."""
    log = {"rows_in": len(raw)}
    df = raw.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    log["bad_dates_dropped"] = int(df["date"].isna().sum())
    df = df.dropna(subset=["date"])

    before = len(df)
    df = df.drop_duplicates(subset="date", keep="last")
    log["duplicate_rows_dropped"] = before - len(df)

    cols = [c for c in METRICS if c in df.columns]
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")  # "N/A" / blanks -> NaN
    df = df.set_index("date").sort_index()[cols]
    df = df.reindex(pd.date_range(df.index.min(), df.index.max(), freq="D"))
    df.index.name = "date"

    log["missing_filled"] = {c: int(df[c].isna().sum()) for c in cols}
    missing_mask = df.isna()
    df = df.interpolate(method="linear", limit=MAX_INTERPOLATION_GAP).ffill().bfill()
    log["rows_out"] = len(df)
    return df, {"log": log, "filled_mask": missing_mask}


# ------------------------------------------------------------------- detection
def compute_baseline(series: pd.Series) -> pd.DataFrame:
    """Trailing 7-day mean/std. shift(1) keeps today's value out of its own baseline."""
    past = series.shift(1).rolling(WINDOW_DAYS, min_periods=MIN_PERIODS)
    mean, std = past.mean(), past.std(ddof=1)
    z = (series - mean) / std.replace(0, np.nan)
    pct = (series - mean) / mean * 100
    return pd.DataFrame({"value": series, "baseline": mean, "std": std, "z": z, "pct": pct})


def detect(df: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for col in df.columns:
        b = compute_baseline(df[col])
        b["metric"] = col
        b["z_flag"] = b["z"].abs() >= Z_THRESHOLD
        b["pct_flag"] = b["pct"].abs() >= PCT_THRESHOLD
        b["is_anomaly"] = b["z_flag"] & b["pct_flag"]
        frames.append(b.reset_index())
    return pd.concat(frames, ignore_index=True)


def severity(pct: float, z: float) -> str:
    if abs(pct) >= 100 or abs(z) >= 10:
        return "Critical"
    if abs(pct) >= 40 or abs(z) >= 4:
        return "High"
    return "Medium"


def summarize(row: pd.Series) -> str:
    meta = METRICS[row["metric"]]
    direction = "down" if row["pct"] < 0 else "up"
    verb = "dropped" if direction == "down" else "spiked"
    side = "below" if direction == "down" else "above"
    return (
        f"{meta['label']} {verb} {abs(row['pct']):.0f}% {side} its 7-day baseline on "
        f"{row['date']:%b %d} ({row['value']:,.1f} vs. a typical {row['baseline']:,.1f} "
        f"{meta['unit']}, {abs(row['z']):.1f} standard deviations from normal). "
        f"Severity: {severity(row['pct'], row['z'])}. {meta[direction]}"
    )


def build_alerts(results: pd.DataFrame) -> pd.DataFrame:
    a = results[results["is_anomaly"]].copy()
    if a.empty:
        return pd.DataFrame(columns=["alert_id", "date", "metric", "direction", "value",
                                     "baseline", "z_score", "pct_change", "severity", "summary"])
    a["direction"] = np.where(a["pct"] < 0, "down", "up")
    a["severity"] = [severity(p, z) for p, z in zip(a["pct"], a["z"])]
    a["summary"] = a.apply(summarize, axis=1)
    a["alert_id"] = [hashlib.sha1(f"{d:%Y-%m-%d}|{m}".encode()).hexdigest()[:10]
                     for d, m in zip(a["date"], a["metric"])]
    a = a.rename(columns={"z": "z_score", "pct": "pct_change"})
    a["date"] = a["date"].dt.strftime("%Y-%m-%d")
    cols = ["alert_id", "date", "metric", "direction", "value", "baseline",
            "z_score", "pct_change", "severity", "summary"]
    return a[cols].round({"value": 2, "baseline": 2, "z_score": 2, "pct_change": 1})


# ------------------------------------------------------------------- alert log
def update_alert_log(alerts: pd.DataFrame, path: str | Path) -> tuple[pd.DataFrame, int]:
    """Append only unseen alerts. Re-running the pipeline never duplicates history."""
    path = Path(path)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    if path.exists():
        existing = pd.read_csv(path, dtype={"alert_id": str})
    else:
        existing = pd.DataFrame(columns=list(alerts.columns) + ["first_seen_utc"])
    new = alerts[~alerts["alert_id"].isin(existing["alert_id"])].copy()
    new["first_seen_utc"] = now
    log = pd.concat([existing, new], ignore_index=True).sort_values("date")
    log.to_csv(path, index=False)
    return log, len(new)


# ---------------------------------------------------------------------- report
def write_report(alerts: pd.DataFrame, stats: dict, path: str | Path) -> None:
    lines = ["# Operations anomaly report", "",
             f"Rule: |z| >= {Z_THRESHOLD} and |change| >= {PCT_THRESHOLD:.0f}% "
             f"vs trailing {WINDOW_DAYS}-day baseline.", ""]
    if alerts.empty:
        lines.append("No anomalies detected.")
    for _, r in alerts.sort_values("date").iterrows():
        lines += [f"## {r['date']}: {METRICS[r['metric']]['label']} ({r['severity']})", "", r["summary"], ""]
    lines += ["## Rule comparison", "",
              f"- z-score alone would raise {stats['z_only']} alerts",
              f"- percent change alone would raise {stats['pct_only']} alerts",
              f"- dual threshold raises {stats['dual']} alerts", ""]
    Path(path).write_text("\n".join(lines))


def rule_comparison(results: pd.DataFrame) -> dict:
    return {"z_only": int(results["z_flag"].sum()),
            "pct_only": int(results["pct_flag"].sum()),
            "dual": int(results["is_anomaly"].sum())}


def run(input_path: str, out_dir: str = "output") -> dict:
    out = Path(out_dir)
    out.mkdir(exist_ok=True)
    cleaned, meta = clean(load_raw(input_path))
    results = detect(cleaned)
    alerts = build_alerts(results)
    log, n_new = update_alert_log(alerts, out / "alert_log.csv")
    stats = rule_comparison(results)
    write_report(alerts, stats, out / "report.md")
    return {"cleaned": cleaned, "meta": meta, "results": results, "alerts": alerts,
            "log": log, "new_alerts": n_new, "stats": stats}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", default="data/raw_metrics.csv")
    p.add_argument("--out", default="output")
    args = p.parse_args()

    r = run(args.input, args.out)
    m = r["meta"]["log"]
    print(f"Cleaned {m['rows_in']} raw rows -> {m['rows_out']} days "
          f"({m['duplicate_rows_dropped']} duplicate dropped, filled {m['missing_filled']})")
    print(f"Detected {len(r['alerts'])} anomalies ({r['new_alerts']} new in alert log)")
    print(f"Single-metric rules would have raised: z-only={r['stats']['z_only']}, "
          f"pct-only={r['stats']['pct_only']}; dual={r['stats']['dual']}\n")
    for _, a in r["alerts"].iterrows():
        print(f"[{a['severity']}] {a['summary']}\n")

    from dashboard import build_dashboard
    build_dashboard(r, Path(args.out) / "dashboard.html")
    print(f"Dashboard: {Path(args.out) / 'dashboard.html'}")


if __name__ == "__main__":
    main()
