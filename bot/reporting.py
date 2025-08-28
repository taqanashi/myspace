import datetime as dt
from dataclasses import dataclass
from typing import Dict, Tuple

from .db import Database


@dataclass
class Period:
    start: dt.datetime
    end: dt.datetime

    def range_ts(self) -> Tuple[int, int]:
        from .db import to_unix

        return to_unix(self.start), to_unix(self.end)


def start_of_week(d: dt.datetime) -> dt.datetime:
    # Monday as start of week
    return (d - dt.timedelta(days=d.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


def start_of_month(d: dt.datetime) -> dt.datetime:
    return d.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def weekly_report(db: Database, channel_id: int, now: dt.datetime) -> Dict:
    this_week_start = start_of_week(now)
    last_week_start = this_week_start - dt.timedelta(days=7)
    last_week_end = this_week_start
    this_week_end = this_week_start + dt.timedelta(days=7)

    s1, e1 = Period(last_week_start, last_week_end).range_ts()
    s2, e2 = Period(this_week_start, this_week_end).range_ts()

    prev_stats = await db.aggregate_between(channel_id, s1, e1)
    curr_stats = await db.aggregate_between(channel_id, s2, e2)
    return {"prev": prev_stats, "curr": curr_stats}


async def monthly_report(db: Database, channel_id: int, now: dt.datetime) -> Dict:
    this_month_start = start_of_month(now)
    last_month_end = this_month_start
    # previous month start: subtract 1 day then set to first of that month
    prev_month_last_day = this_month_start - dt.timedelta(days=1)
    last_month_start = start_of_month(prev_month_last_day)
    # next month start
    if this_month_start.month == 12:
        next_month_start = this_month_start.replace(year=this_month_start.year + 1, month=1)
    else:
        next_month_start = this_month_start.replace(month=this_month_start.month + 1)

    s1, e1 = Period(last_month_start, last_month_end).range_ts()
    s2, e2 = Period(this_month_start, next_month_start).range_ts()

    prev_stats = await db.aggregate_between(channel_id, s1, e1)
    curr_stats = await db.aggregate_between(channel_id, s2, e2)
    return {"prev": prev_stats, "curr": curr_stats}


def format_comparison(title: str, prev: Dict, curr: Dict) -> str:
    def delta(a, b):
        if a is None or b is None:
            return "n/a"
        diff = b - a
        if a == 0:
            return f"{diff:+}"
        pct = (diff / a) * 100
        return f"{diff:+} ({pct:+.1f}%)"

    lines = [f"{title}"]
    keys = [
        ("messages_count", "Сообщений"),
        ("avg_text_length", "Средняя длина текста"),
        ("avg_word_count", "Среднее число слов"),
        ("links_count", "Сообщений со ссылками"),
        ("photos", "Фото"),
        ("videos", "Видео"),
        ("documents", "Документы"),
        ("audios", "Аудио"),
        ("voices", "Голосовые"),
    ]
    for key, label in keys:
        a = prev.get(key)
        b = curr.get(key)
        lines.append(f"- {label}: {b or 0} ({delta(a or 0, b or 0)})")
    return "\n".join(lines)