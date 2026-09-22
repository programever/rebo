"""Step 4: the web page. Plain HTML, no build step, no JavaScript needed.

index.html shows today's reading in full, with its sound, and a list of the
earlier days. Each day also has its own page in days/<date>/ with its own
sound file, so an old day can still be listened to.
"""
from __future__ import annotations

import html
import logging
import shutil
from datetime import date
from pathlib import Path

from .config import DAYS_DIR, Config, day_in_words
from .plan import Reading
from .voice import audio_matches, duration_seconds, spoken_pieces

log = logging.getLogger(__name__)

SOURCE_NAME = "Làng Mai"
SOURCE_URL = "https://langmai.org/tang-kinh-cac/vien-sach/thien-tap/"
AUTHOR = "Thiền sư Thích Nhất Hạnh"

CSS = """
:root { color-scheme: light dark; --bg: #fcfcfb; --fg: #1a1a19; --muted: #5c5b57; --line: #dcdbd5; --accent: #2a78d6; }
@media (prefers-color-scheme: dark) { :root { --bg: #1a1a19; --fg: #f0efe9; --muted: #b8b7ae; --line: #3a3a38; --accent: #6aa5ec; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg); font: 19px/1.7 Georgia, "Times New Roman", serif; }
main { max-width: 680px; margin: 0 auto; padding: 20px 18px 60px; }
header.top { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; border-bottom: 1px solid var(--line); padding-bottom: 12px; margin-bottom: 20px; }
header.top h1 { font-size: 22px; margin: 0; }
header.top p { margin: 4px 0 0; color: var(--muted); font-size: 15px; }
h2.book { font-size: 26px; margin: 8px 0 2px; }
p.meta { color: var(--muted); font-size: 15px; margin: 0 0 12px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
audio { width: 100%; margin: 8px 0 20px; }
h3 { font-size: 21px; margin: 32px 0 8px; }
p { margin: 0 0 1em; }
a { color: var(--accent); }
ul.days { list-style: none; padding: 0; margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
ul.days li { padding: 12px 0; border-bottom: 1px solid var(--line); }
ul.days .d { color: var(--muted); font-size: 14px; }
ul.days .s { display: block; color: var(--muted); font-size: 15px; }
footer { margin-top: 48px; padding-top: 16px; border-top: 1px solid var(--line); color: var(--muted); font-size: 14px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
nav.prevnext { display: flex; justify-content: space-between; margin-top: 32px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; font-size: 15px; }
.done { background: rgba(42,120,214,.1); border-radius: 8px; padding: 10px 14px; margin: 20px 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; font-size: 15px; }
"""


def published_days(limit: int) -> list[date]:
    """The newest `limit` days that have a reading, newest first."""
    if not DAYS_DIR.is_dir():
        return []
    days: list[date] = []
    for folder in DAYS_DIR.iterdir():
        if folder.is_dir() and (folder / "reading.json").is_file():
            try:
                days.append(date.fromisoformat(folder.name))
            except ValueError:
                continue
    days.sort(reverse=True)
    return days[:limit]


def _e(s: str) -> str:
    return html.escape(s, quote=True)


def _minutes(seconds: int) -> str:
    return f"{max(1, round(seconds / 60))} phút" if seconds else ""


def _sections_line(r: Reading) -> str:
    titles = [s["title"] for s in r.sections]
    return " · ".join(titles)


def _audio_tag(src: str | None) -> str:
    if not src:
        return '<p class="meta">Hôm nay không có giọng đọc. Bạn vẫn đọc được chữ bên dưới.</p>'
    return f'<audio controls preload="none" src="{_e(src)}"></audio>'


def _reading_html(r: Reading, audio_src: str | None, seconds: int, finished_book: bool) -> str:
    day = date.fromisoformat(r.day)
    out = [f'<h2 class="book"><a href="{_e(r.book_url)}">{_e(r.book_title)}</a></h2>']
    span = f"{r.section_start + 1}–{r.section_end}" if r.section_end - r.section_start > 1 else str(r.section_start + 1)
    dur = f" · nghe {_minutes(seconds)}" if seconds else ""
    out.append(f'<p class="meta">{_e(day_in_words(day))} · {_e(r.part_title)} · mục {span}/{r.section_count}{dur}</p>')
    out.append(_audio_tag(audio_src))
    for s in r.sections:
        out.append(f"<h3>{_e(s['title'])}</h3>")
        for p in s["paragraphs"]:
            out.append(f"<p>{_e(p)}</p>")
    if finished_book:
        out.append('<p class="done">Hết sách. Ngày mai bắt đầu sách mới.</p>')
    return "\n".join(out)


def _footer() -> str:
    return (f'<footer>Sách của {_e(AUTHOR)}, lấy từ thư viện <a href="{SOURCE_URL}">{SOURCE_NAME}</a>. '
            f'Giọng đọc là giọng máy (Microsoft). Trang này chỉ giữ 10 ngày gần nhất.</footer>')


def _page(title: str, body: str, css_href: str) -> str:
    return (f'<!doctype html><html lang="vi"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{_e(title)}</title><link rel="stylesheet" href="{css_href}"></head>'
            f'<body><main>{body}</main></body></html>')


def build_site(cfg: Config, folder: Path) -> list[date]:
    """Write the whole page into an empty folder. Returns the days it published."""
    days = published_days(cfg.page_days)
    if not days:
        raise RuntimeError("nothing to publish: no day has a reading yet")
    (folder / "style.css").write_text(CSS.strip() + "\n", encoding="utf-8")
    (folder / ".nojekyll").write_text("", encoding="utf-8")

    entries: list[tuple[date, Reading, str | None, int]] = []
    for day in days:
        src_dir = DAYS_DIR / day.isoformat()
        reading = Reading.load(src_dir)
        assert reading is not None
        audio_rel: str | None = None
        seconds = 0
        mp3 = src_dir / "audio.mp3"
        if audio_matches(src_dir, spoken_pieces(reading.sections)):
            target = folder / "days" / day.isoformat()
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy2(mp3, target / "audio.mp3")
            audio_rel = "audio.mp3"
            seconds = duration_seconds(mp3)
        elif mp3.is_file():
            log.warning("site: %s has a sound file that does not match its words; left off the page", day)
        entries.append((day, reading, audio_rel, seconds))

    # one page per day
    for i, (day, reading, audio_rel, seconds) in enumerate(entries):
        target = folder / "days" / day.isoformat()
        target.mkdir(parents=True, exist_ok=True)
        finished = reading.progress_after["book"] != reading.book_slug
        body = [f'<header class="top"><h1><a href="../../">Rebo</a></h1><p>Mỗi ngày một đoạn sách, có giọng đọc.</p></header>']
        body.append(_reading_html(reading, audio_rel, seconds, finished))
        newer = entries[i - 1][0].isoformat() if i > 0 else None
        older = entries[i + 1][0].isoformat() if i + 1 < len(entries) else None
        body.append('<nav class="prevnext">'
                    + (f'<a href="../{older}/">← Ngày trước</a>' if older else '<span></span>')
                    + (f'<a href="../{newer}/">Ngày sau →</a>' if newer else '<span></span>') + '</nav>')
        body.append(_footer())
        (target / "index.html").write_text(_page(f"{reading.book_title} – {day.isoformat()}", "\n".join(body), "../../style.css"), encoding="utf-8")

    # the front page: today in full, then the list
    day, reading, audio_rel, seconds = entries[0]
    finished = reading.progress_after["book"] != reading.book_slug
    body = ['<header class="top"><h1>Rebo</h1><p>Mỗi ngày một đoạn sách, có giọng đọc.</p></header>']
    body.append(_reading_html(reading, f"days/{day.isoformat()}/audio.mp3" if audio_rel else None, seconds, finished))
    if len(entries) > 1:
        body.append('<h3>Các ngày trước</h3><ul class="days">')
        for d, r, a, sec in entries[1:]:
            listen = f" · {_minutes(sec)}" if a else ""
            body.append(f'<li><span class="d">{_e(day_in_words(d))}{listen}</span><br>'
                        f'<a href="days/{d.isoformat()}/">{_e(r.book_title)}: {_e(r.part_title)}</a>'
                        f'<span class="s">{_e(_sections_line(r))}</span></li>')
        body.append('</ul>')
    body.append(_footer())
    (folder / "index.html").write_text(_page("Rebo", "\n".join(body), "style.css"), encoding="utf-8")
    return days
