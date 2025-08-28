import datetime as dt
import re
from dataclasses import dataclass
from typing import Dict, Optional, List, Tuple

from .config import Settings


@dataclass
class DailyMetrics:
    date_str: str  # YYYY-MM-DD (local date for the summary)
    sms_namings_total: int
    active_clients: int
    mts: int
    megafon: int
    beeline: int
    tele2_rostelecom: int
    other_operators: int
    alt_channels_total: int
    teleads_views: int


_NUM = r"([\d\s]+)"

_PATTERNS = {
    "sms_namings_total": re.compile(r"SMS-?нейминги\s*\(всего\)\s*[-—:]\s*" + _NUM, re.IGNORECASE),
    "active_clients": re.compile(r"Активные\s+клиенты\s*[-—:]\s*" + _NUM, re.IGNORECASE),
    "mts": re.compile(r"МТС\s*[-—:]\s*" + _NUM, re.IGNORECASE),
    "megafon": re.compile(r"Мегафон\s*[-—:]\s*" + _NUM, re.IGNORECASE),
    "beeline": re.compile(r"Билайн\s*[-—:]\s*" + _NUM, re.IGNORECASE),
    "tele2_rostelecom": re.compile(r"Теле2\s+и\s+Ростелеком\s*[-—:]\s*" + _NUM, re.IGNORECASE),
    "other_operators": re.compile(r"Прочие\s+операторы\s*[-—:]\s*" + _NUM, re.IGNORECASE),
    "alt_channels_total": re.compile(r"Все\s+каналы\s*[-—:]\s*" + _NUM, re.IGNORECASE),
    "teleads_views": re.compile(r"Просмотры\s+в\s+TeleAds\s*[-—:]\s*" + _NUM, re.IGNORECASE),
}

_HEADER_RE = re.compile(r"Ежедневная\s+сводка\s+показателей.*за\s+вчера", re.IGNORECASE | re.DOTALL)


def _to_int(num_str: Optional[str]) -> int:
    if not num_str:
        return 0
    return int(num_str.replace(" ", "").strip())


def parse_daily_summary(text: str, message_dt_utc: dt.datetime, settings: Settings) -> Optional[DailyMetrics]:
    if not _HEADER_RE.search(text):
        return None
    values: Dict[str, int] = {}
    for key, rx in _PATTERNS.items():
        m = rx.search(text)
        values[key] = _to_int(m.group(1)) if m else 0

    tz = settings.tz()
    local_dt = message_dt_utc.astimezone(tz)
    target_date = (local_dt - dt.timedelta(days=1)).date()
    date_str = target_date.isoformat()

    return DailyMetrics(date_str=date_str, **values)  # type: ignore[arg-type]


def format_daily_comparison(curr: DailyMetrics, prev: Optional[DailyMetrics]) -> str:
    def line(label: str, a: int, b: int) -> str:
        diff = b - a
        return f"- {label}: {b} ({diff:+})"

    header = f"Ежедневная сводка: сравнение со вчерашним днём ({curr.date_str} vs -1д)"
    if prev is None:
        return header + "\nНет данных за предыдущий день для сравнения."

    parts = [
        header,
        line("SMS-нейминги (всего)", prev.sms_namings_total, curr.sms_namings_total),
        line("Активные клиенты", prev.active_clients, curr.active_clients),
        "",
        "SMS-трафик (отправлено):",
        line("МТС", prev.mts, curr.mts),
        line("Мегафон", prev.megafon, curr.megafon),
        line("Билайн", prev.beeline, curr.beeline),
        line("Теле2 и Ростелеком", prev.tele2_rostelecom, curr.tele2_rostelecom),
        line("Прочие операторы", prev.other_operators, curr.other_operators),
        "",
        "Трафик в альт. каналы:",
        line("Все каналы", prev.alt_channels_total, curr.alt_channels_total),
        line("Просмотры в TeleAds", prev.teleads_views, curr.teleads_views),
    ]
    return "\n".join(parts)


def _sum_metrics(rows: List[Dict[str, int]], keys: List[str]) -> Dict[str, int]:
    result = {k: 0 for k in keys}
    for row in rows:
        for k in keys:
            result[k] += int(row.get(k, 0))
    return result


def week_starts(local_now: dt.datetime) -> Tuple[dt.date, dt.date]:
    # Monday as start; return (this_week_start, last_week_start)
    this_week_start = (local_now - dt.timedelta(days=local_now.weekday())).date()
    last_week_start = this_week_start - dt.timedelta(days=7)
    return this_week_start, last_week_start


def _format_period(start: dt.date, end: dt.date) -> str:
    return f"{start.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')}"


async def weekly_from_daily(db: "Database", channel_id: int, settings: Settings, now_utc: dt.datetime) -> Dict[str, Dict[str, int] | str]:
    from .db import Database  # type: ignore # for type hints only

    tz = settings.tz()
    local_now = now_utc.astimezone(tz)
    this_week_start, last_week_start = week_starts(local_now)

    # We want last complete week (Mon..Sun) vs previous week
    last_week_end = this_week_start - dt.timedelta(days=1)
    prev_week_start = last_week_start - dt.timedelta(days=7)
    prev_week_end = last_week_start - dt.timedelta(days=1)

    rows_prev = await db.fetch_daily_metrics_between(channel_id, prev_week_start.isoformat(), prev_week_end.isoformat())
    rows_curr = await db.fetch_daily_metrics_between(channel_id, last_week_start.isoformat(), last_week_end.isoformat())

    traffic_keys = [
        "mts",
        "megafon",
        "beeline",
        "tele2_rostelecom",
        "other_operators",
        "alt_channels_total",
        "teleads_views",
    ]

    sums_prev = _sum_metrics(rows_prev, traffic_keys)
    sums_curr = _sum_metrics(rows_curr, traffic_keys)

    # cumulative metrics deltas
    def last_value(rows: List[Dict[str, int]], key: str) -> int:
        return int(rows[-1][key]) if rows else 0

    cum_keys = ["sms_namings_total", "active_clients"]
    cum_prev = {k: last_value(rows_prev, k) for k in cum_keys}
    cum_curr = {k: last_value(rows_curr, k) for k in cum_keys}
    cum_delta = {k: (cum_curr.get(k, 0) - cum_prev.get(k, 0)) for k in cum_keys}

    period_curr = _format_period(last_week_start, last_week_end)

    return {
        "period": period_curr,
        "prev": sums_prev | cum_prev,
        "curr": sums_curr | cum_curr,
        "cum_delta": cum_delta,
    }


def format_weekly_from_daily(title: str, data: Dict[str, Dict[str, int] | str]) -> str:
    period = str(data.get("period", ""))
    prev = data.get("prev", {})  # type: ignore[assignment]
    curr = data.get("curr", {})  # type: ignore[assignment]
    cum_delta = data.get("cum_delta", {})  # type: ignore[assignment]

    def total_sms(d: Dict[str, int]) -> int:
        return int(d.get("mts", 0)) + int(d.get("megafon", 0)) + int(d.get("beeline", 0)) + int(d.get("tele2_rostelecom", 0)) + int(d.get("other_operators", 0))

    sms_prev = total_sms(prev)  # type: ignore[arg-type]
    sms_curr = total_sms(curr)  # type: ignore[arg-type]
    sms_diff = sms_curr - sms_prev

    alt_prev = int(prev.get("alt_channels_total", 0))  # type: ignore[union-attr]
    alt_curr = int(curr.get("alt_channels_total", 0))  # type: ignore[union-attr]
    alt_diff = alt_curr - alt_prev

    ta_prev = int(prev.get("teleads_views", 0))  # type: ignore[union-attr]
    ta_curr = int(curr.get("teleads_views", 0))  # type: ignore[union-attr]
    ta_diff = ta_curr - ta_prev

    sms_names_delta = int(cum_delta.get("sms_namings_total", 0))  # type: ignore[union-attr]
    active_clients_delta = int(cum_delta.get("active_clients", 0))  # type: ignore[union-attr]

    parts = [
        f"{title}: {period}",
        "Итоги недели:",
        f"- Отправлено SMS (всего): {sms_curr} ({sms_diff:+})",
        f"- Отправлено в альт. каналы (всего): {alt_curr} ({alt_diff:+})",
        f"- Просмотры в TeleAds (всего): {ta_curr} ({ta_diff:+})",
        "",
        "Клиенты и нейминги (прирост):",
        f"- SMS-нейминги: {sms_names_delta:+}",
        f"- Активные клиенты: {active_clients_delta:+}",
    ]
    return "\n".join(parts)