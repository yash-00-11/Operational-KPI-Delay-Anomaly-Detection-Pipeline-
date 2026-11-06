"""Generate a 45-day synthetic operational dataset for a distribution network.

The data is SYNTHETIC. Three incidents are injected so the pipeline has known
ground truth to find:

    day 24  shipment_volume          -48%  vs its trailing 7-day baseline
    day 32  distribution_delay_hrs  +129%
    day 40  customer_complaints     +230%

The raw file is deliberately messy (blank cells, "N/A" strings, a duplicated
row) so the cleaning stage has real work to do.

Usage:  python generate_data.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 7
DAYS = 45
START = "2026-09-23"
OUT = Path("data/raw_metrics.csv")

# (day index, column, signed change vs the trailing 7-day mean)
INCIDENTS = [
    (24, "shipment_volume", -0.48),
    (32, "distribution_delay_hrs", +1.29),
    (40, "customer_complaints", +2.30),
]
# Missing values live outside every incident's 7-day baseline window.
MISSING = {
    "shipment_volume": [3, 13],
    "distribution_delay_hrs": [8, 16],
    "customer_complaints": [13],
    "on_time_delivery_pct": [3, 43],
}


def build() -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    dates = pd.date_range(START, periods=DAYS, freq="D")
    weekend = (dates.dayofweek >= 5).astype(float)

    df = pd.DataFrame({"date": dates})
    df["shipment_volume"] = (1250 * (1 - 0.08 * weekend) * rng.normal(1, 0.04, DAYS)).round()
    df["distribution_delay_hrs"] = (6.0 * (1 + 0.05 * weekend) * rng.normal(1, 0.06, DAYS)).round(2)
    df["customer_complaints"] = rng.normal(38, 2.6, DAYS).round(1)
    df["on_time_delivery_pct"] = (94.5 + rng.normal(0, 1.1, DAYS)).round(2)

    # Inject incidents relative to the clean trailing-7-day mean, in time order.
    for day, col, change in sorted(INCIDENTS):
        baseline = df[col].iloc[day - 7 : day].mean()
        df.loc[day, col] = round(baseline * (1 + change), 0 if col == "shipment_volume" else 2)
        # knock-on effect: a delay spike drags on-time delivery down a little
        if col == "distribution_delay_hrs":
            df.loc[day, "on_time_delivery_pct"] = 88.4

    # Make it messy.
    for col, idx in MISSING.items():
        df[col] = df[col].astype(object)
        for i in idx:
            df.loc[i, col] = np.nan if i % 2 else "N/A"
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    df = pd.concat([df, df.iloc[[20]]], ignore_index=True)  # duplicated row
    return df


if __name__ == "__main__":
    OUT.parent.mkdir(exist_ok=True)
    build().to_csv(OUT, index=False)
    print(f"Wrote {OUT}")
