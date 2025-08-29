import asyncio
import datetime as dt
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, FSInputFile
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

from .config import Paths, Settings
from .db import Database
from .handlers import register as register_handlers
from .reporting import format_comparison, monthly_report, weekly_report
from .daily import weekly_from_daily, format_weekly_from_daily
from .charts import render_weekly_sums_png


async def set_commands(bot: Bot) -> None:
    await bot.set_my_commands([BotCommand(command="stats", description="Проверка состояния")])


async def send_weekly_daily_report(bot: Bot, db: Database, settings: Settings) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    data = await weekly_from_daily(db, settings.channel_id, settings, now)
    text = format_weekly_from_daily("Еженедельная сводка OmniChannel (по ежедневным отчётам)", data)
    await bot.send_message(chat_id=settings.channel_id, text=text)
    # Attach chart
    img_path = render_weekly_sums_png(
        output_dir=Path("data/charts"),
        title="Итоги недели",
        period_label_prev="пред. неделя",
        period_label_curr=str(data.get("period", "текущая неделя")),
        prev=data.get("prev", {}),  # type: ignore[arg-type]
        curr=data.get("curr", {}),  # type: ignore[arg-type]
    )
    await bot.send_photo(chat_id=settings.channel_id, photo=FSInputFile(str(img_path)))


async def send_monthly_report(bot: Bot, db: Database, channel_id: int, tz: str) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    data = await monthly_report(db, channel_id, now)
    text = format_comparison("Ежемесячный отчёт", data.get("prev", {}), data.get("curr", {}))
    await bot.send_message(chat_id=channel_id, text=text)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    load_dotenv()

    project_root = Path(__file__).resolve().parent.parent
    paths = Paths.ensure(project_root)
    settings = Settings.from_env()

    db = Database(settings.database_path)
    await db.ensure_schema()

    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    register_handlers(dp, db, settings.channel_id, settings)
    await set_commands(bot)

    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    # Weekly report based on daily metrics (every Monday at configured hour)
    scheduler.add_job(
        send_weekly_daily_report,
        trigger=CronTrigger(day_of_week="mon", hour=settings.weekly_report_hour, minute=0),
        args=[bot, db, settings],
        id="weekly_daily_report",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    # Monthly report based on channel message stats (optional)
    scheduler.add_job(
        send_monthly_report,
        trigger=CronTrigger(day=1, hour=settings.monthly_report_hour, minute=0),
        args=[bot, db, settings.channel_id, settings.timezone],
        id="monthly_report",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())