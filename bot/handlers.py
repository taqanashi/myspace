import datetime as dt
import re
from typing import Optional

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.types.message import ContentType

from .db import Database, MessageRecord, to_unix


URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def _extract_text(message: Message) -> str:
    if message.text:
        return message.text
    if message.caption:
        return message.caption
    return ""


def _has_link(message: Message, text: str) -> bool:
    entities = message.entities or message.caption_entities or []
    for ent in entities:
        if ent.type in {"url", "text_link"}:
            return True
    return bool(URL_RE.search(text))


def _media_kind(message: Message) -> Optional[str]:
    ct = message.content_type
    if ct == ContentType.PHOTO:
        return "photo"
    if ct == ContentType.VIDEO:
        return "video"
    if ct == ContentType.DOCUMENT:
        return "document"
    if ct == ContentType.AUDIO:
        return "audio"
    if ct == ContentType.VOICE:
        return "voice"
    return None


def register(router: Router, db: Database, channel_id: int) -> None:
    @router.channel_post()
    async def on_channel_post(message: Message) -> None:
        if message.chat.id != channel_id:
            return
        text = _extract_text(message)
        words = len(text.split()) if text else 0
        record = MessageRecord(
            channel_id=message.chat.id,
            message_id=message.message_id,
            date_ts=to_unix(message.date if message.date.tzinfo else message.date.replace(tzinfo=dt.timezone.utc)),
            content_type=str(message.content_type),
            text_length=len(text),
            word_count=words,
            has_link=_has_link(message, text),
            media_kind=_media_kind(message),
            is_forwarded=bool(message.forward_origin),
        )
        await db.insert_message(record)

    @router.edited_channel_post()
    async def on_edited_channel_post(message: Message) -> None:
        await on_channel_post(message)

    @router.message(Command("stats"))
    async def on_stats(message: Message) -> None:
        await message.answer("Бот активен и собирает статистику по каналу.")