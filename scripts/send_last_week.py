import asyncio
import datetime as dt
from pathlib import Path

from aiogram import Bot
from dotenv import load_dotenv

from bot.config import Settings
from bot.db import Database
from bot.reporting import format_comparison, weekly_report


async def run() -> None:
    load_dotenv()
    settings = Settings.from_env()
    db = Database(settings.database_path)
    await db.ensure_schema()

    bot = Bot(token=settings.telegram_bot_token)
    try:
        now = dt.datetime.now(dt.timezone.utc)
        data = await weekly_report(db, settings.channel_id, now)
        text = format_comparison("Еженедельный отчёт (прошлая неделя)", data.get("prev", {}), data.get("curr", {}))
        await bot.send_message(chat_id=settings.channel_id, text=text)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(run())