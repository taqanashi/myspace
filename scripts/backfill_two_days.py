import asyncio
import datetime as dt
from pathlib import Path

from aiogram import Bot
from dotenv import load_dotenv

from bot.config import Settings
from bot.db import Database
from bot.daily import DailyMetrics, format_daily_comparison
from bot.charts import render_daily_comparison_png


async def run() -> None:
    load_dotenv()
    settings = Settings.from_env()
    db = Database(settings.database_path)
    await db.ensure_schema()

    tz = settings.tz()
    today_local = dt.datetime.now(dt.timezone.utc).astimezone(tz).date()
    yesterday = today_local - dt.timedelta(days=1)
    day_before = today_local - dt.timedelta(days=2)

    # Provided values from user
    day_before_vals = {
        "sms_namings_total": 468,
        "active_clients": 9,
        "mts": 31853,
        "megafon": 789,
        "beeline": 788,
        "tele2_rostelecom": 913,
        "other_operators": 447,
        "alt_channels_total": 1,
        "teleads_views": 0,
    }
    yesterday_vals = {
        "sms_namings_total": 468,
        "active_clients": 10,
        "mts": 33100,
        "megafon": 1574,
        "beeline": 1653,
        "tele2_rostelecom": 923,
        "other_operators": 303,
        "alt_channels_total": 6,
        "teleads_views": 0,
    }

    # Upsert to DB
    await db.upsert_daily_metrics(settings.channel_id, day_before.isoformat(), day_before_vals)
    await db.upsert_daily_metrics(settings.channel_id, yesterday.isoformat(), yesterday_vals)

    # Prepare messages
    prev = DailyMetrics(date_str=day_before.isoformat(), **day_before_vals)
    curr = DailyMetrics(date_str=yesterday.isoformat(), **yesterday_vals)
    text = format_daily_comparison(curr=curr, prev=prev)

    img_path = render_daily_comparison_png(
        output_dir=Path("data/charts"),
        title="Вчера vs позавчера",
        prev_label=prev.date_str,
        curr_label=curr.date_str,
        prev={
            "mts": prev.mts,
            "megafon": prev.megafon,
            "beeline": prev.beeline,
            "tele2_rostelecom": prev.tele2_rostelecom,
            "other_operators": prev.other_operators,
            "alt_channels_total": prev.alt_channels_total,
            "teleads_views": prev.teleads_views,
        },
        curr={
            "mts": curr.mts,
            "megafon": curr.megafon,
            "beeline": curr.beeline,
            "tele2_rostelecom": curr.tele2_rostelecom,
            "other_operators": curr.other_operators,
            "alt_channels_total": curr.alt_channels_total,
            "teleads_views": curr.teleads_views,
        },
    )

    bot = Bot(token=settings.telegram_bot_token)
    try:
        await bot.send_message(chat_id=settings.channel_id, text=text)
        await bot.send_photo(chat_id=settings.channel_id, photo=img_path.open("rb"))
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(run())