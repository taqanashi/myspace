import asyncio
import datetime as dt
from dataclasses import dataclass
from typing import Any, Dict, Optional

import aiosqlite


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    date_ts INTEGER NOT NULL,
    content_type TEXT NOT NULL,
    text_length INTEGER NOT NULL,
    word_count INTEGER NOT NULL,
    has_link INTEGER NOT NULL,
    media_kind TEXT,
    is_forwarded INTEGER NOT NULL DEFAULT 0,
    UNIQUE(channel_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_date ON messages(date_ts);
"""


@dataclass
class MessageRecord:
    channel_id: int
    message_id: int
    date_ts: int
    content_type: str
    text_length: int
    word_count: int
    has_link: bool
    media_kind: Optional[str]
    is_forwarded: bool


class Database:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def ensure_schema(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(SCHEMA_SQL)
            await db.commit()

    async def insert_message(self, record: MessageRecord) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT OR IGNORE INTO messages (
                    channel_id, message_id, date_ts, content_type, text_length, word_count,
                    has_link, media_kind, is_forwarded
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.channel_id,
                    record.message_id,
                    record.date_ts,
                    record.content_type,
                    record.text_length,
                    record.word_count,
                    1 if record.has_link else 0,
                    record.media_kind,
                    1 if record.is_forwarded else 0,
                ),
            )
            await db.commit()

    async def aggregate_between(self, channel_id: int, start_ts: int, end_ts: int) -> Dict[str, Any]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT
                    COUNT(*) AS messages_count,
                    AVG(text_length) AS avg_text_length,
                    AVG(word_count) AS avg_word_count,
                    SUM(has_link) AS links_count,
                    SUM(CASE WHEN media_kind = 'photo' THEN 1 ELSE 0 END) AS photos,
                    SUM(CASE WHEN media_kind = 'video' THEN 1 ELSE 0 END) AS videos,
                    SUM(CASE WHEN media_kind = 'document' THEN 1 ELSE 0 END) AS documents,
                    SUM(CASE WHEN media_kind = 'audio' THEN 1 ELSE 0 END) AS audios,
                    SUM(CASE WHEN media_kind = 'voice' THEN 1 ELSE 0 END) AS voices
                FROM messages
                WHERE channel_id = ? AND date_ts >= ? AND date_ts < ?
                """,
                (channel_id, start_ts, end_ts),
            )
            row = await cur.fetchone()
            return dict(row) if row else {}


def to_unix(dt_obj: dt.datetime) -> int:
    return int(dt_obj.timestamp())


async def _demo(db_path: str) -> None:
    db = Database(db_path)
    await db.ensure_schema()
    await db.insert_message(
        MessageRecord(
            channel_id=123,
            message_id=1,
            date_ts=to_unix(dt.datetime.now(dt.timezone.utc)),
            content_type="text",
            text_length=10,
            word_count=2,
            has_link=False,
            media_kind=None,
            is_forwarded=False,
        )
    )
    stats = await db.aggregate_between(123, 0, 4102444800)
    print(stats)


if __name__ == "__main__":
    asyncio.run(_demo("data/bot.db"))