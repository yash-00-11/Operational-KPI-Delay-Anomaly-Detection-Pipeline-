"""Generates a synthetic 45-day business metrics CSV with a few injected
anomalies, missing values, and messy formatting -- so the pipeline has
something realistic to chew on. Replace this with your own CSV in practice."""

import csv
import random
from datetime import datetime, timedelta

random.seed(7)

start = datetime(2026, 7, 20)
n_days = 45

rows = []
revenue_base = 12000
signups_base = 240
churn_base = 3.2  # percent
active_users_base = 8600

for i in range(n_days):
    date = start + timedelta(days=i)

    # gentle upward trend + weekly seasonality + noise
    trend = i * 25
    weekday_factor = 1.15 if date.weekday() in (5, 6) else 1.0

    revenue = revenue_base + trend + random.gauss(0, 400)
    revenue *= weekday_factor
    signups = signups_base + i * 1.2 + random.gauss(0, 15)
    churn = churn_base + random.gauss(0, 0.3)
    active_users = active_users_base + i * 18 + random.gauss(0, 120)

    # Inject anomalies
    if i == 20:
        revenue *= 0.45          # revenue crash (e.g. payment outage)
    if i == 28:
        signups *= 2.3           # signups spike (viral post / campaign)
    if i == 35:
        churn *= 3.0             # churn spike (bad release)

    row = {
        "date": date.strftime("%Y-%m-%d"),
        "revenue": round(revenue, 2),
        "signups": round(signups),
        "churn_rate": round(churn, 2),
        "active_users": round(active_users),
    }
    rows.append(row)

# Mess up the data a bit: missing values, duplicate row, odd formatting
rows[5]["revenue"] = ""
rows[12]["churn_rate"] = "N/A"
rows[18]["signups"] = None
rows.append(dict(rows[10]))  # duplicate date
rows[22]["active_users"] = "8,912"  # comma-formatted number

random.shuffle(rows)  # out of order, like a real export might be

with open("sample_metrics.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["date", "revenue", "signups", "churn_rate", "active_users"])
    writer.writeheader()
    for r in rows:
        writer.writerow(r)

print(f"Wrote sample_metrics.csv with {len(rows)} rows (includes messy data + 3 injected anomalies)")
