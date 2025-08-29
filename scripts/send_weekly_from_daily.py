import asyncio
import datetime as dt

from aiogram import Bot
from dotenv import load_dotenv

from bot.config import Settings
from bot.db import Database
from bot.daily import weekly_from_daily, format_weekly_from_daily


async def run() -> None:
    load_dotenv()
    settings = Settings.from_env()
    db = Database(settings.database_path)
    await db.ensure_schema()

    bot = Bot(token=settings.telegram_bot_token)
    try:
        now = dt.datetime.now(dt.timezone.utc)
        data = await weekly_from_daily(db, settings.channel_id, settings, now)
        text = format_weekly_from_daily(
            "Еженедельная сводка OmniChannel (прошлая неделя, по ежедневным отчётам)",
            data,
        )
        await bot.send_message(chat_id=settings.channel_id, text=text)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(run())