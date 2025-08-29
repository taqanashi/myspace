import asyncio
import datetime as dt
import math
import random
from typing import Dict, List

from dotenv import load_dotenv

from bot.config import Settings
from bot.db import Database

FLOW_KEYS = [
    "mts",
    "megafon",
    "beeline",
    "tele2_rostelecom",
    "other_operators",
    "alt_channels_total",
    "teleads_views",
]
CUM_KEYS = ["sms_namings_total", "active_clients"]


async def run() -> None:
    load_dotenv()
    s = Settings.from_env()
    db = Database(s.database_path)
    await db.ensure_schema()

    tz = s.tz()
    today_local = dt.datetime.now(dt.timezone.utc).astimezone(tz).date()
    start_date = dt.date(year=today_local.year, month=1, day=1)
    end_date = today_local - dt.timedelta(days=1)

    if end_date < start_date:
        print("Nothing to backfill: start >= end")
        return

    existing = await db.fetch_daily_metrics_between(s.channel_id, start_date.isoformat(), end_date.isoformat())
    existing_by_date = {row["date"]: row for row in existing}

    if not existing:
        print("No existing daily metrics to base on. Please provide at least one day.")
        return

    # Compute baseline averages for flow metrics from existing data
    base: Dict[str, float] = {k: 0.0 for k in FLOW_KEYS}
    for row in existing:
        for k in FLOW_KEYS:
            base[k] += float(row.get(k, 0))
    for k in FLOW_KEYS:
        base[k] /= max(len(existing), 1)

    # Targets for cumulative metrics: last known values
    last_row = existing[-1]
    target_sms_naming = int(last_row.get("sms_namings_total", 0))
    target_active_clients = int(last_row.get("active_clients", 0))

    # Start values as requested
    start_sms_naming = 300
    start_active_clients = 5

    # Days count
    total_days = (end_date - start_date).days + 1

    # Deterministic jitter
    random.seed(42)

    date = start_date
    filled = 0
    while date <= end_date:
        date_str = date.isoformat()
        # Skip overwrite for existing dates
        if date_str in existing_by_date:
            date += dt.timedelta(days=1)
            continue

        day_index = (date - start_date).days

        # Smooth jitter within +/- 5%
        # Use sinusoidal component for smoothness + tiny deterministic noise
        sin_component = math.sin(2 * math.pi * day_index / 14.0)  # 2-week cycle
        noise = (random.random() - 0.5) * 0.02  # +/-1%
        factor = 1.0 + 0.05 * sin_component + noise

        values: Dict[str, int] = {}
        for k in FLOW_KEYS:
            v = max(0, int(round(base[k] * factor)))
            values[k] = v

        # Linear growth for cumulative metrics to reach targets by end_date
        progress = (day_index + 1) / total_days
        sms_value = int(round(start_sms_naming + (target_sms_naming - start_sms_naming) * progress))
        clients_value = int(round(start_active_clients + (target_active_clients - start_active_clients) * progress))
        values["sms_namings_total"] = max(values.get("sms_namings_total", 0), sms_value)
        values["active_clients"] = max(values.get("active_clients", 0), clients_value)

        await db.upsert_daily_metrics(s.channel_id, date_str, values)
        filled += 1
        date += dt.timedelta(days=1)

    print(f"Backfill complete. Filled missing days: {filled}")


if __name__ == "__main__":
    asyncio.run(run())