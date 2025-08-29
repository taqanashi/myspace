import asyncio
import datetime as dt
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile
from dotenv import load_dotenv

from bot.config import Settings
from bot.db import Database
from bot.daily import DailyMetrics, format_daily_comparison
from bot.charts import render_daily_comparison_png

USER_ID = 601146329  # target Telegram user id


def _row_to_metrics(row: dict) -> DailyMetrics:
    return DailyMetrics(
        date_str=row["date"],
        sms_namings_total=int(row.get("sms_namings_total", 0)),
        active_clients=int(row.get("active_clients", 0)),
        mts=int(row.get("mts", 0)),
        megafon=int(row.get("megafon", 0)),
        beeline=int(row.get("beeline", 0)),
        tele2_rostelecom=int(row.get("tele2_rostelecom", 0)),
        other_operators=int(row.get("other_operators", 0)),
        alt_channels_total=int(row.get("alt_channels_total", 0)),
        teleads_views=int(row.get("teleads_views", 0)),
    )


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
            text = "Недостаточно данных для сравнения: нет ежедневных сводок за последние два дня."
            bot = Bot(token=settings.telegram_bot_token)
            try:
                await bot.send_message(chat_id=USER_ID, text=text)
            finally:
                await bot.session.close()
            return

    prev = _row_to_metrics(prev_row)
    curr = _row_to_metrics(curr_row)

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
        await bot.send_message(chat_id=USER_ID, text=text)
        await bot.send_photo(chat_id=USER_ID, photo=FSInputFile(str(img_path)))
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(run())