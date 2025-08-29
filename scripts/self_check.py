import asyncio
import datetime as dt
import traceback

from aiogram import Bot
from dotenv import load_dotenv

from bot.config import Settings


async def run() -> None:
    load_dotenv()
    s = Settings.from_env()
    bot = Bot(token=s.telegram_bot_token)
    try:
        me = await bot.get_me()
        print(f"getMe: id={me.id}, username=@{me.username}")
        # Test send to channel
        try:
            msg = await bot.send_message(chat_id=s.channel_id, text=f"[self-check] {dt.datetime.utcnow().isoformat()} UTC")
            print(f"channel send: ok (message_id={msg.message_id})")
        except Exception as e:
            print("channel send: ERROR:")
            traceback.print_exc()
        # Test send to user if provided via env (allowed_user_ids)
        target_user = None
        if s.allowed_user_ids:
            target_user = s.allowed_user_ids[0]
        if target_user:
            try:
                msg = await bot.send_message(chat_id=target_user, text="[self-check] ping")
                print(f"dm send to {target_user}: ok (message_id={msg.message_id})")
            except Exception:
                print(f"dm send to {target_user}: ERROR (maybe user didn't press Start)")
                traceback.print_exc()
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(run())