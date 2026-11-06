"""Builds a self-contained interactive dashboard (output/dashboard.html)."""
import json
from pathlib import Path

import pandas as pd

from pipeline import METRICS, Z_THRESHOLD, PCT_THRESHOLD, WINDOW_DAYS

TEMPLATE = Path(__file__).with_name("dashboard_template.html")


def _num(x):
    return None if pd.isna(x) else round(float(x), 2)


def build_dashboard(result: dict, out_path) -> None:
    res, mask = result["results"], result["meta"]["filled_mask"]
    metrics = {}
    for key, meta in METRICS.items():
        d = res[res["metric"] == key].reset_index(drop=True)
        std = d["std"]
        metrics[key] = {
            "label": meta["label"], "unit": meta["unit"],
            "dates": d["date"].dt.strftime("%Y-%m-%d").tolist(),
            "values": [_num(v) for v in d["value"]],
            "baseline": [_num(v) for v in d["baseline"]],
            "upper": [_num(m + Z_THRESHOLD * s) for m, s in zip(d["baseline"], std)],
            "lower": [_num(m - Z_THRESHOLD * s) for m, s in zip(d["baseline"], std)],
            "anomaly": d.index[d["is_anomaly"]].tolist(),
            "filled": [int(i) for i, v in enumerate(mask[key].tolist()) if v],
        }
    payload = {
        "metrics": metrics,
        "log": result["log"].fillna("").to_dict(orient="records"),
        "stats": result["stats"],
        "rule": {"z": Z_THRESHOLD, "pct": PCT_THRESHOLD, "window": WINDOW_DAYS},
        "cleaning": result["meta"]["log"],
    }
    html = TEMPLATE.read_text().replace("__DATA__", json.dumps(payload))
    Path(out_path).write_text(html)
