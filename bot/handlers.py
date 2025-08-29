import datetime as dt
import re
from typing import Optional

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from aiogram.types.message import ContentType
from aiogram.types import FSInputFile

from .config import Settings
from .db import Database, MessageRecord, to_unix
from .daily import parse_daily_summary, DailyMetrics, format_daily_comparison, weekly_from_daily, format_weekly_from_daily, period_from_daily, format_period_from_daily
from .charts import render_daily_comparison_png, render_weekly_sums_png, render_period_totals_png
from pathlib import Path


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


def _message_datetime_utc(message: Message) -> dt.datetime:
    # Prefer original date for forwarded messages
    orig_dt = None
    try:
        if message.forward_origin and getattr(message.forward_origin, "date", None):
            orig_dt = message.forward_origin.date
    except Exception:
        orig_dt = None
    base_dt = orig_dt or message.date
    return base_dt if base_dt.tzinfo else base_dt.replace(tzinfo=dt.timezone.utc)


def _is_allowed(message: Message, settings: Settings) -> bool:
    chat = message.chat
    if chat.type == "private":
        user = message.from_user
        return bool(user and user.id in set(settings.allowed_user_ids))
    return chat.id in set(settings.allowed_chat_ids)


async def _send_dm_to_allowed(message: Message, settings: Settings, text: str, img_path: Path | None = None) -> None:
    for uid in settings.allowed_user_ids:
        await message.bot.send_message(chat_id=uid, text=text)
        if img_path is not None:
            await message.bot.send_photo(chat_id=uid, photo=FSInputFile(str(img_path)))


async def _maybe_send_daily_comparison_with_chart(db: Database, channel_id: int, date_str: str, message: Message, settings: Settings) -> None:
    # Fetch current date and previous date metrics
    date = dt.date.fromisoformat(date_str)
    prev_date = date - dt.timedelta(days=1)
    rows = await db.fetch_daily_metrics_between(channel_id, prev_date.isoformat(), date.isoformat())
    if len(rows) < 2:
        return
    prev_row, curr_row = rows[0], rows[1]

    def to_dm(row: dict) -> DailyMetrics:
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

    prev = to_dm(prev_row)
    curr = to_dm(curr_row)

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

    # Send only via DM to allowed users
    await _send_dm_to_allowed(message, settings, text, img_path)


def register(router: Router, db: Database, channel_id: int, settings: Settings) -> None:
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

        # Try to parse daily summary and store it
        try:
            msg_dt_utc = _message_datetime_utc(message)
            daily = parse_daily_summary(text, msg_dt_utc, settings)
            if daily:
                await db.upsert_daily_metrics(
                    channel_id=message.chat.id,
                    date_str=daily.date_str,
                    values={
                        "sms_namings_total": daily.sms_namings_total,
                        "active_clients": daily.active_clients,
                        "mts": daily.mts,
                        "megafon": daily.megafon,
                        "beeline": daily.beeline,
                        "tele2_rostelecom": daily.tele2_rostelecom,
                        "other_operators": daily.other_operators,
                        "alt_channels_total": daily.alt_channels_total,
                        "teleads_views": daily.teleads_views,
                    },
                )
                # After upsert, send comparison (yesterday vs day-before) with chart only in DMs
                await _maybe_send_daily_comparison_with_chart(db, message.chat.id, daily.date_str, message, settings)
        except Exception:
            # Fail-safe: ignore parse errors
            pass

    @router.edited_channel_post()
    async def on_edited_channel_post(message: Message) -> None:
        await on_channel_post(message)

    # DM: /start -> greet and show commands
    @router.message(CommandStart())
    async def on_start(message: Message) -> None:
        if not _is_allowed(message, settings):
            return
        await message.answer(
            "Привет! Я буду присылать сравнения. Команды:\n"
            "/daily — вчера vs позавчера (с графиком)\n"
            "/lastday — за вчера и прирост (с графиком)\n"
            "/weekly — прошлая неделя vs предыдущая (с графиком)\n"
            "/month — сводка за месяц (MTD) с графиком\n"
            "/year — сводка за год (YTD) с графиком\n"
            "/stats — статус бота"
        )

    # DM: /daily -> send yesterday vs day-before to current chat
    @router.message(Command("daily"))
    async def on_daily(message: Message) -> None:
        if not _is_allowed(message, settings):
            return
        tz = settings.tz()
        today_local = dt.datetime.now(dt.timezone.utc).astimezone(tz).date()
        yesterday = today_local - dt.timedelta(days=1)
        day_before = today_local - dt.timedelta(days=2)
        rows = await db.fetch_daily_metrics_between(channel_id, day_before.isoformat(), yesterday.isoformat())
        if len(rows) < 2:
            rows_all = await db.fetch_daily_metrics_between(channel_id, "0001-01-01", "9999-12-31")
            if len(rows_all) >= 2:
                rows = rows_all[-2:]
        if len(rows) >= 2:
            prev_row, curr_row = rows[0], rows[1]
            prev = DailyMetrics(
                date_str=prev_row["date"],
                sms_namings_total=int(prev_row.get("sms_namings_total", 0)),
                active_clients=int(prev_row.get("active_clients", 0)),
                mts=int(prev_row.get("mts", 0)),
                megafon=int(prev_row.get("megafon", 0)),
                beeline=int(prev_row.get("beeline", 0)),
                tele2_rostelecom=int(prev_row.get("tele2_rostelecom", 0)),
                other_operators=int(prev_row.get("other_operators", 0)),
                alt_channels_total=int(prev_row.get("alt_channels_total", 0)),
                teleads_views=int(prev_row.get("teleads_views", 0)),
            )
            curr = DailyMetrics(
                date_str=curr_row["date"],
                sms_namings_total=int(curr_row.get("sms_namings_total", 0)),
                active_clients=int(curr_row.get("active_clients", 0)),
                mts=int(curr_row.get("mts", 0)),
                megafon=int(curr_row.get("megafon", 0)),
                beeline=int(curr_row.get("beeline", 0)),
                tele2_rostelecom=int(curr_row.get("tele2_rostelecom", 0)),
                other_operators=int(curr_row.get("other_operators", 0)),
                alt_channels_total=int(curr_row.get("alt_channels_total", 0)),
                teleads_views=int(curr_row.get("teleads_views", 0)),
            )
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
            await message.answer(text)
            await message.answer_photo(FSInputFile(str(img_path)))
        else:
            await message.answer("Недостаточно данных для сравнения: нет ежедневных сводок за последние два дня.")

    # DM: /lastday (alias /last) -> yesterday totals and deltas
    @router.message(Command(("lastday", "last")))
    async def on_lastday(message: Message) -> None:
        if not _is_allowed(message, settings):
            return
        tz = settings.tz()
        today_local = dt.datetime.now(dt.timezone.utc).astimezone(tz).date()
        yesterday = today_local - dt.timedelta(days=1)
        day_before = today_local - dt.timedelta(days=2)
        rows = await db.fetch_daily_metrics_between(channel_id, day_before.isoformat(), yesterday.isoformat())
        if len(rows) < 2:
            rows_all = await db.fetch_daily_metrics_between(channel_id, "0001-01-01", "9999-12-31")
            if len(rows_all) >= 2:
                rows = rows_all[-2:]
        if len(rows) >= 2:
            prev_row, curr_row = rows[0], rows[1]
            prev = DailyMetrics(
                date_str=prev_row["date"],
                sms_namings_total=int(prev_row.get("sms_namings_total", 0)),
                active_clients=int(prev_row.get("active_clients", 0)),
                mts=int(prev_row.get("mts", 0)),
                megafon=int(prev_row.get("megafon", 0)),
                beeline=int(prev_row.get("beeline", 0)),
                tele2_rostelecom=int(prev_row.get("tele2_rostelecom", 0)),
                other_operators=int(prev_row.get("other_operators", 0)),
                alt_channels_total=int(prev_row.get("alt_channels_total", 0)),
                teleads_views=int(prev_row.get("teleads_views", 0)),
            )
            curr = DailyMetrics(
                date_str=curr_row["date"],
                sms_namings_total=int(curr_row.get("sms_namings_total", 0)),
                active_clients=int(curr_row.get("active_clients", 0)),
                mts=int(curr_row.get("mts", 0)),
                megafon=int(curr_row.get("megafon", 0)),
                beeline=int(curr_row.get("beeline", 0)),
                tele2_rostelecom=int(curr_row.get("tele2_rostelecom", 0)),
                other_operators=int(curr_row.get("other_operators", 0)),
                alt_channels_total=int(curr_row.get("alt_channels_total", 0)),
                teleads_views=int(curr_row.get("teleads_views", 0)),
            )
            text = format_daily_comparison(curr=curr, prev=prev)
            img_path = render_daily_comparison_png(
                output_dir=Path("data/charts"),
                title="За вчера и прирост",
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
            await message.answer(text)
            await message.answer_photo(FSInputFile(str(img_path)))
        else:
            await message.answer("Недостаточно данных для сравнения: нет ежедневных сводок за последние два дня.")

    # DM: /weekly -> send last complete week vs previous to current chat
    @router.message(Command("weekly"))
    async def on_weekly(message: Message) -> None:
        if not _is_allowed(message, settings):
            return
        now = dt.datetime.now(dt.timezone.utc)
        data = await weekly_from_daily(db, channel_id, settings, now)
        text = format_weekly_from_daily("Еженедельная сводка OmniChannel (по ежедневным отчётам)", data)
        await message.answer(text)
        img_path = render_weekly_sums_png(
            output_dir=Path("data/charts"),
            title="Итоги недели",
            period_label_prev="пред. неделя",
            period_label_curr=str(data.get("period", "текущая неделя")),
            prev=data.get("prev", {}),  # type: ignore[arg-type]
            curr=data.get("curr", {}),  # type: ignore[arg-type]
        )
        await message.answer_photo(FSInputFile(str(img_path)))

    # DM: /month -> current month-to-date stats
    @router.message(Command("month"))
    async def on_month(message: Message) -> None:
        if not _is_allowed(message, settings):
            return
        tz = settings.tz()
        now_local = dt.datetime.now(dt.timezone.utc).astimezone(tz)
        start = now_local.replace(day=1).date()
        end = now_local.date()
        data = await period_from_daily(db, channel_id, start, end)
        text = format_period_from_daily("Ежемесячная сводка (MTD)", f"{start.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')}", data)
        await message.answer(text)
        img_path = render_period_totals_png(
            output_dir=Path("data/charts"),
            title="MTD итоги",
            label=f"{start.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')}",
            totals=data.get("totals", {}),  # type: ignore[arg-type]
        )
        await message.answer_photo(FSInputFile(str(img_path)))

    # DM: /year -> current year-to-date stats
    @router.message(Command("year"))
    async def on_year(message: Message) -> None:
        if not _is_allowed(message, settings):
            return
        tz = settings.tz()
        now_local = dt.datetime.now(dt.timezone.utc).astimezone(tz)
        start = dt.date(year=now_local.year, month=1, day=1)
        end = now_local.date()
        data = await period_from_daily(db, channel_id, start, end)
        text = format_period_from_daily("Годовая сводка (YTD)", f"{start.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')}", data)
        await message.answer(text)
        img_path = render_period_totals_png(
            output_dir=Path("data/charts"),
            title="YTD итоги",
            label=f"{start.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')}",
            totals=data.get("totals", {}),  # type: ignore[arg-type]
        )
        await message.answer_photo(FSInputFile(str(img_path)))

    @router.message(Command("stats"))
    async def on_stats(message: Message) -> None:
        if not _is_allowed(message, settings):
            return
        await message.answer("Бот активен и собирает статистику по каналу.")