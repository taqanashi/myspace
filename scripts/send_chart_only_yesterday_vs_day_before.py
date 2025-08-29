import asyncio
import datetime as dt
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile
from dotenv import load_dotenv

from bot.config import Settings
from bot.db import Database
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

    rows = await db.fetch_daily_metrics_between(settings.channel_id, day_before.isoformat(), yesterday.isoformat())
    by_date = {r["date"]: r for r in rows}

    prev_row = by_date.get(day_before.isoformat())
    curr_row = by_date.get(yesterday.isoformat())

    if not prev_row or not curr_row:
        rows_all = await db.fetch_daily_metrics_between(settings.channel_id, "0001-01-01", "9999-12-31")
        if len(rows_all) >= 2:
            prev_row, curr_row = rows_all[-2], rows_all[-1]
        else:
            print("No data to render chart.")
            return

    img_path = render_daily_comparison_png(
        output_dir=Path("data/charts"),
        title="Вчера vs позавчера",
        prev_label=prev_row["date"],
        curr_label=curr_row["date"],
        prev={
            "mts": int(prev_row.get("mts", 0)),
            "megafon": int(prev_row.get("megafon", 0)),
            "beeline": int(prev_row.get("beeline", 0)),
            "tele2_rostelecom": int(prev_row.get("tele2_rostelecom", 0)),
            "other_operators": int(prev_row.get("other_operators", 0)),
            "alt_channels_total": int(prev_row.get("alt_channels_total", 0)),
            "teleads_views": int(prev_row.get("teleads_views", 0)),
        },
        curr={
            "mts": int(curr_row.get("mts", 0)),
            "megafon": int(curr_row.get("megafon", 0)),
            "beeline": int(curr_row.get("beeline", 0)),
            "tele2_rostelecom": int(curr_row.get("tele2_rostelecom", 0)),
            "other_operators": int(curr_row.get("other_operators", 0)),
            "alt_channels_total": int(curr_row.get("alt_channels_total", 0)),
            "teleads_views": int(curr_row.get("teleads_views", 0)),
        },
    )

    bot = Bot(token=settings.telegram_bot_token)
    try:
        await bot.send_photo(chat_id=settings.channel_id, photo=FSInputFile(str(img_path)))
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(run())