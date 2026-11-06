import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pipeline as p


def _series(values):
    return pd.Series(values, index=pd.date_range("2026-01-01", periods=len(values)), dtype=float)


def test_clean_fills_missing_and_drops_duplicates():
    raw = pd.DataFrame({
        "date": ["2026-01-01", "2026-01-02", "2026-01-02", "2026-01-04"],
        "shipment_volume": ["100", "N/A", "110", "130"],
    })
    df, meta = p.clean(raw)
    assert len(df) == 4  # Jan 3 is a missing day and gets reinstated
    assert not df["shipment_volume"].isna().any()
    assert meta["log"]["duplicate_rows_dropped"] == 1


def test_dual_threshold_needs_both_rules():
    # Stable metric: a tiny move is a big z-score but a small % change.
    s = _series([100, 100.2, 99.8, 100.1, 99.9, 100.0, 100.1, 101.5])
    r = p.detect(s.to_frame("shipment_volume")).iloc[-1]
    assert r["z_flag"] and not r["pct_flag"] and not r["is_anomaly"]


def test_large_move_in_noisy_metric_is_flagged():
    s = _series([100, 104, 96, 101, 99, 102, 98, 52])
    r = p.detect(s.to_frame("shipment_volume")).iloc[-1]
    assert r["is_anomaly"] and r["pct"] < -40


def test_current_day_not_in_own_baseline():
    s = _series([10, 10, 10, 10, 10, 10, 10, 1000])
    assert p.compute_baseline(s)["baseline"].iloc[-1] == 10


def test_alert_log_is_deduplicated(tmp_path):
    first = p.run(str(ROOT / "data/raw_metrics.csv"), str(tmp_path))
    second = p.run(str(ROOT / "data/raw_metrics.csv"), str(tmp_path))
    assert first["new_alerts"] == 3 and second["new_alerts"] == 0
    assert len(second["log"]) == 3


def test_known_incidents_detected(tmp_path):
    out = p.run(str(ROOT / "data/raw_metrics.csv"), str(tmp_path))
    a = out["alerts"].set_index("metric")
    assert round(a.loc["shipment_volume", "pct_change"]) == -48
    assert round(a.loc["distribution_delay_hrs", "pct_change"]) == 129
    assert round(a.loc["customer_complaints", "pct_change"]) == 230
    assert len(a) == 3
