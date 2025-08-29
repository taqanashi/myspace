import asyncio
from dotenv import load_dotenv
from bot.config import Settings
from bot.db import Database


async def run():
    load_dotenv()
    s = Settings.from_env()
    db = Database(s.database_path)
    await db.ensure_schema()
    rows = await db.fetch_daily_metrics_between(s.channel_id, "0001-01-01", "9999-12-31")
    print(f"daily_metrics rows: {len(rows)}")
    for r in rows[-10:]:
        print(r)


if __name__ == "__main__":
    asyncio.run(run())