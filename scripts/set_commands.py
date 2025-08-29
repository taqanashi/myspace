import asyncio
from aiogram import Bot
from aiogram.types import BotCommand
from dotenv import load_dotenv
from bot.config import Settings


async def run() -> None:
    load_dotenv()
    settings = Settings.from_env()
    bot = Bot(token=settings.telegram_bot_token)
    try:
        await bot.set_my_commands([
            BotCommand(command="start", description="Начать"),
            BotCommand(command="daily", description="Сравнение: вчера vs позавчера"),
            BotCommand(command="weekly", description="Еженедельный отчёт"),
            BotCommand(command="month", description="Ежемесячная сводка (MTD)"),
            BotCommand(command="year", description="Годовая сводка (YTD)"),
            BotCommand(command="stats", description="Проверка состояния"),
        ])
        me = await bot.get_me()
        print(f"Commands updated for @{me.username}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(run())