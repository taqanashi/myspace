import datetime as dt
from pathlib import Path
from typing import Dict, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def render_daily_comparison_png(output_dir: Path, title: str, prev_label: str, curr_label: str, prev: Dict[str, int], curr: Dict[str, int]) -> Path:
    metrics = [
        ("SMS (МТС)", "mts"),
        ("SMS (Мегафон)", "megafon"),
        ("SMS (Билайн)", "beeline"),
        ("SMS (Теле2+РТК)", "tele2_rostelecom"),
        ("SMS (прочие)", "other_operators"),
        ("Альт. каналы", "alt_channels_total"),
        ("TeleAds", "teleads_views"),
    ]
    labels = [m[0] for m in metrics]
    prev_vals = [int(prev.get(m[1], 0)) for m in metrics]
    curr_vals = [int(curr.get(m[1], 0)) for m in metrics]

    _ensure_dir(output_dir)
    filepath = output_dir / f"daily_{dt.datetime.utcnow().strftime('%Y%m%d%H%M%S')}.png"

    x = range(len(labels))
    width = 0.35
    plt.figure(figsize=(10, 5))
    plt.bar([i - width / 2 for i in x], prev_vals, width=width, label=prev_label)
    plt.bar([i + width / 2 for i in x], curr_vals, width=width, label=curr_label)
    plt.xticks(list(x), labels, rotation=20)
    plt.title(title)
    plt.legend()
    plt.tight_layout()
    plt.savefig(filepath)
    plt.close()
    return filepath


def render_weekly_sums_png(output_dir: Path, title: str, period_label_prev: str, period_label_curr: str, prev: Dict[str, int], curr: Dict[str, int]) -> Path:
    metrics = [
        ("SMS (итого)", ["mts", "megafon", "beeline", "tele2_rostelecom", "other_operators"]),
        ("Альт. каналы", ["alt_channels_total"]),
        ("TeleAds", ["teleads_views"]),
    ]
    labels = [m[0] for m in metrics]

    def total(d: Dict[str, int], keys: List[str]) -> int:
        return sum(int(d.get(k, 0)) for k in keys)

    prev_vals = [total(prev, m[1]) for m in metrics]
    curr_vals = [total(curr, m[1]) for m in metrics]

    _ensure_dir(output_dir)
    filepath = output_dir / f"weekly_{dt.datetime.utcnow().strftime('%Y%m%d%H%M%S')}.png"

    x = range(len(labels))
    width = 0.35
    plt.figure(figsize=(8, 4))
    plt.bar([i - width / 2 for i in x], prev_vals, width=width, label=period_label_prev)
    plt.bar([i + width / 2 for i in x], curr_vals, width=width, label=period_label_curr)
    plt.xticks(list(x), labels)
    plt.title(title)
    plt.legend()
    plt.tight_layout()
    plt.savefig(filepath)
    plt.close()
    return filepath