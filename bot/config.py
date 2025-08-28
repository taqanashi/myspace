import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ValidationError


class Settings(BaseModel):
    telegram_bot_token: str
    channel_id: int
    database_path: str = "data/bot.db"
    timezone: str = "UTC"
    weekly_report_hour: int = 9
    monthly_report_hour: int = 9

    @classmethod
    def from_env(cls) -> "Settings":
        try:
            return cls(
                telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
                channel_id=int(os.environ["CHANNEL_ID"]),
                database_path=os.environ.get("DATABASE_PATH", "data/bot.db"),
                timezone=os.environ.get("TIMEZONE", "UTC"),
                weekly_report_hour=int(os.environ.get("WEEKLY_REPORT_HOUR", 9)),
                monthly_report_hour=int(os.environ.get("MONTHLY_REPORT_HOUR", 9)),
            )
        except KeyError as exc:
            raise RuntimeError(f"Missing required environment variable: {exc}") from exc
        except ValidationError as exc:
            raise RuntimeError(f"Invalid configuration: {exc}") from exc

    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


@dataclass
class Paths:
    project_root: Path
    data_dir: Path

    @classmethod
    def ensure(cls, project_root: Path) -> "Paths":
        data_dir = project_root / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return cls(project_root=project_root, data_dir=data_dir)