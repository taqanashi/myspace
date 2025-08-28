import datetime as dt
import re
from dataclasses import dataclass
from typing import Dict, Optional

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

    # Compute local date for "yesterday" relative to message time
    tz = settings.tz()
    local_dt = message_dt_utc.astimezone(tz)
    target_date = (local_dt - dt.timedelta(days=1)).date()
    date_str = target_date.isoformat()

    return DailyMetrics(date_str=date_str, **values)  # type: ignore[arg-type]


def format_daily_comparison(curr: DailyMetrics, prev: Optional[DailyMetrics]) -> str:
    def line(label: str, a: int, b: int) -> str:
        diff = b - a
        sign = "+" if diff > 0 else "" if diff == 0 else ""
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