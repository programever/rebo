#!/usr/bin/env python3
"""Tests that need no internet and no Microsoft. Run before every push:
    .venv/bin/python selftest.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIX = ROOT / "tests" / "fixtures"

# Point all output at a scratch folder before the pipeline is imported.
SCRATCH = Path(tempfile.mkdtemp(prefix="rebo-selftest-"))
os.environ["DOCSACH_OUT"] = str(SCRATCH)

from pipeline import config, fetch, plan, site, voice  # noqa: E402

config.OUT_DIR = SCRATCH
config.DAYS_DIR = SCRATCH / "days"
config.CACHE_DIR = SCRATCH / "cache"
config.PROGRESS_FILE = SCRATCH / "progress.json"
plan.PROGRESS_FILE = config.PROGRESS_FILE
plan.day_dir = lambda d: config.DAYS_DIR / d.isoformat()
site.DAYS_DIR = config.DAYS_DIR

fails = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global fails
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else "  " + extra))
    if not ok:
        fails += 1


def read(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


# ---- reading the site's pages ----
books = fetch.parse_catalog(read("catalog.html"))
check("catalog has 37 books", len(books) == 37, str(len(books)))
check("first book is An lạc từng bước chân", books[0].slug == "an-lac-tung-buoc-chan" and books[0].title == "An lạc từng bước chân")
check("book slugs are unique", len({b.slug for b in books}) == len(books))

parts = fetch.parse_parts(read("book-an-lac.html"), books[0].url)
check("book has 3 parts, no doubles", [p.slug for p in parts] == [
    "phan-i-hoi-tho-y-thuc-hoi-tho-mau-nhiem", "phan-ii-chuyen-hoa-va-tri-lieu", "phan-iii-an-lac-tung-buoc-chan"], str([p.slug for p in parts]))
check("part titles", parts[0].title.startswith("Phần I:"))

sections = fetch.parse_sections(read("part1-an-lac.html"), parts[0].title)
check("part I has 24 sections", len(sections) == 24, str(len(sections)))
check("first section title", sections[0].title == "Hai Mươi Bốn Giờ Tinh Khôi", sections[0].title)
check("first paragraph text", sections[0].paragraphs[0].startswith("Buổi sáng khi thức dậy"), sections[0].paragraphs[0][:60])
check("about 12,000 words", 11500 < sum(s.words for s in sections) < 13000, str(sum(s.words for s in sections)))
check("no empty section titles", all(s.title.strip() for s in sections))
check("no empty paragraphs", all(p.strip() for s in sections for p in s.paragraphs))
check("no html left in text", not any("<" in p or "&nbsp;" in p for s in sections for p in s.paragraphs))

# ---- grouping into days ----
check("first day is sections 1-6", plan.pick_sections(sections, 0, 2000) == 6, str(plan.pick_sections(sections, 0, 2000)))
check("last section alone", plan.pick_sections(sections, 23, 2000) == 24)
check("a huge budget takes the whole part", plan.pick_sections(sections, 0, 10**6) == 24)
check("a tiny budget still takes one section", plan.pick_sections(sections, 0, 1) == 1)

# ---- moving on ----
lib = books
p = plan.Progress(book="an-lac-tung-buoc-chan", part=0, section=0)
check("middle of a part: same part, next section", plan.advance(p, 6, 24, 3, lib) == plan.Progress("an-lac-tung-buoc-chan", 0, 6))
check("end of a part: next part", plan.advance(p, 24, 24, 3, lib) == plan.Progress("an-lac-tung-buoc-chan", 1, 0))
p3 = plan.Progress(book="an-lac-tung-buoc-chan", part=2, section=0)
nxt = plan.advance(p3, 24, 24, 3, lib)
check("end of the book: next book in the library", nxt.book == books[1].slug and nxt.part == 0 and nxt.section == 0, str(nxt))
check("the first book comes from books.txt", plan.next_book_slug(None, lib) == "an-lac-tung-buoc-chan")
last = plan.next_book_slug(books[-1].slug, lib)
check("after the last book, the library starts again", last == books[0].slug, last)

# ---- the page ----
r = plan.Reading(day="2026-09-22", book_slug=books[0].slug, book_title=books[0].title, book_url=books[0].url,
                 part_index=0, part_count=3, part_title=parts[0].title, part_url=parts[0].url,
                 section_start=0, section_end=2, section_count=24,
                 sections=[{"title": s.title, "paragraphs": s.paragraphs} for s in sections[:2]],
                 words=sum(s.words for s in sections[:2]),
                 progress_before={"book": books[0].slug, "part": 0, "section": 0},
                 progress_after={"book": books[0].slug, "part": 0, "section": 2})
r.save(config.DAYS_DIR / "2026-09-22")
r2 = plan.Reading(**{**r.__dict__, "day": "2026-09-21", "section_start": 22, "section_end": 24,
                     "sections": [{"title": s.title, "paragraphs": s.paragraphs} for s in sections[22:]],
                     "progress_after": {"book": books[1].slug, "part": 0, "section": 0}})
r2.save(config.DAYS_DIR / "2026-09-21")
# a fake sound file with a wrong stamp: must be left off the page
(config.DAYS_DIR / "2026-09-21" / "audio.mp3").write_bytes(b"not really sound")
voice.stamp_file(config.DAYS_DIR / "2026-09-21").write_text("wrong", encoding="utf-8")

cfg = config.Config.load()
out = SCRATCH / "site"
out.mkdir()
days = site.build_site(cfg, out)
check("two days published, newest first", days == [date(2026, 9, 22), date(2026, 9, 21)], str(days))
index = (out / "index.html").read_text(encoding="utf-8")
check("front page has the book title", books[0].title in index)
check("front page has today's first section", sections[0].title in index)
check("front page says there is no sound today", "không có giọng đọc" in index)
check("front page lists the earlier day", 'href="days/2026-09-21/"' in index)
check("front page links to the source", "langmai.org" in index)
old = (out / "days" / "2026-09-21" / "index.html").read_text(encoding="utf-8")
check("old day page exists with its text", sections[23].title in old)
check("old day says the book is finished", "Hết sách" in old)
check("mismatched sound is left off", not (out / "days" / "2026-09-21" / "audio.mp3").exists() and "<audio" not in old)
check("no html escaping problems", "&lt;" not in index and "&amp;amp;" not in index)

# ---- voice fingerprint ----
pieces = voice.spoken_pieces(r.sections)
check("one piece per title and per paragraph", len(pieces) == 2 + len(sections[0].paragraphs) + len(sections[1].paragraphs), str(len(pieces)))
check("no ellipsis character goes to the voice", not any("\u2026" in x for x in pieces))
check("cleaning keeps the words", voice.clean_for_speech("a\u2026 b\xa0c\n d") == "a... b c d")
check("first piece is the title", pieces[0] == sections[0].title + ".")
check("fingerprint changes with the words", voice.fingerprint(pieces) != voice.fingerprint(pieces[:1]))

# ---- undo ----
plan.Progress(**r.progress_after).save()
plan.undo_day(date(2026, 9, 22))
check("undo puts progress back", plan.Progress.load() == plan.Progress(**r.progress_before))
check("undo removes the day's files", not (config.DAYS_DIR / "2026-09-22" / "reading.json").exists())

print(f"\n{fails} failed" if fails else "\nall tests passed")
sys.exit(1 if fails else 0)
