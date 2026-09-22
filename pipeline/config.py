"""Settings. Nothing here is secret. Each value can be changed with an
environment variable of the same name, but the defaults are what Iker asked for."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "out"
DAYS_DIR = OUT_DIR / "days"
CACHE_DIR = OUT_DIR / "cache"
PROGRESS_FILE = OUT_DIR / "progress.json"
BOOKS_FILE = ROOT / "books.txt"

VIETNAM = ZoneInfo("Asia/Ho_Chi_Minh")

# The library on langmai.org that holds the books.
CATALOG_URL = "https://langmai.org/tang-kinh-cac/vien-sach/thien-tap/"

# The page shows this many days. Older days stay on this box for ever; they only
# stop being published. Iker asked for 10 on 2026-09-22.
PAGE_DAYS = 10

# One day is a few sections in a row, about this many words. A section is
# never cut in the middle, so a day can be a little longer than this.
WORDS_PER_DAY = 2000


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw.isdigit() else default


@dataclass(frozen=True)
class Config:
    site_repo: str
    site_branch: str
    site_url: str
    tts_voice: str
    tts_rate: str
    page_days: int
    words_per_day: int
    pause_seconds: float

    @staticmethod
    def load() -> "Config":
        return Config(
            site_repo=os.environ.get("SITE_REPO", "git@github.com:programever/Rebo.git").strip(),
            site_branch=os.environ.get("SITE_BRANCH", "gh-pages").strip(),
            site_url=os.environ.get("SITE_URL", "https://programever.github.io/rebo/").strip(),
            # A warm Vietnamese woman's voice from Microsoft. No key, no limit.
            tts_voice=os.environ.get("TTS_VOICE", "vi-VN-HoaiMyNeural").strip(),
            tts_rate=os.environ.get("TTS_RATE", "+0%").strip(),
            page_days=_int("PAGE_DAYS", PAGE_DAYS),
            words_per_day=_int("WORDS_PER_DAY", WORDS_PER_DAY),
            pause_seconds=0.7,
        )


def today_vietnam() -> date:
    return datetime.now(VIETNAM).date()


def day_dir(day: date) -> Path:
    return DAYS_DIR / day.isoformat()


WEEKDAYS_VI = ("Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật")


def day_in_words(day: date) -> str:
    """The date the way a Vietnamese person says it: 'Thứ Ba, 22/9/2026'."""
    return f"{WEEKDAYS_VI[day.weekday()]}, {day.day}/{day.month}/{day.year}"
