"""Step 2: decide what today's reading is.

Progress is one small file, out/progress.json:
    {"book": "<slug>", "part": <index>, "section": <index of the next unread section>}

A day's reading is a few sections in a row, about WORDS_PER_DAY words. A section
is never cut. When a part ends, the next part starts the next day. When a book
ends, the next book in books.txt starts; when books.txt is used up, the next
book in the library after the current one.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from . import fetch
from .config import BOOKS_FILE, PROGRESS_FILE, day_dir

log = logging.getLogger(__name__)


class PlanError(RuntimeError):
    pass


@dataclass
class Progress:
    book: str
    part: int
    section: int

    @staticmethod
    def load(path: Path = PROGRESS_FILE) -> "Progress | None":
        if not path.is_file():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        return Progress(book=str(raw["book"]), part=int(raw["part"]), section=int(raw["section"]))

    def save(self, path: Path = PROGRESS_FILE) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=1), encoding="utf-8")


def wanted_books(path: Path = BOOKS_FILE) -> list[str]:
    """Book slugs from books.txt, in order. Empty lines and # notes are skipped."""
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line.rstrip("/").rsplit("/", 1)[-1])
    return out


def next_book_slug(current: str | None, library: list[fetch.Book]) -> str:
    """The book to read after `current` (or the first one when current is None)."""
    wanted = wanted_books()
    known = {b.slug for b in library}
    wanted = [w for w in wanted if w in known]
    if current is None:
        if wanted:
            return wanted[0]
        return library[0].slug
    if current in wanted:
        i = wanted.index(current)
        if i + 1 < len(wanted):
            return wanted[i + 1]
    order = [b.slug for b in library]
    if current in order:
        i = order.index(current)
        return order[(i + 1) % len(order)]
    return wanted[0] if wanted else order[0]


def pick_sections(sections: list[fetch.Section], start: int, words_per_day: int) -> int:
    """Index just past the last section for today. At least one section; then
    more, as long as the total is still under the word budget."""
    if start >= len(sections):
        raise PlanError("start is past the end of the part")
    end = start + 1
    total = sections[start].words
    while end < len(sections) and total < words_per_day:
        total += sections[end].words
        end += 1
    return end


@dataclass
class Reading:
    """One day's reading, saved as days/<date>/reading.json."""
    day: str
    book_slug: str
    book_title: str
    book_url: str
    part_index: int
    part_count: int
    part_title: str
    part_url: str
    section_start: int
    section_end: int
    section_count: int
    sections: list[dict]
    words: int
    progress_before: dict
    progress_after: dict

    def save(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "reading.json").write_text(json.dumps(asdict(self), ensure_ascii=False, indent=1), encoding="utf-8")

    @staticmethod
    def load(folder: Path) -> "Reading | None":
        f = folder / "reading.json"
        if not f.is_file():
            return None
        return Reading(**json.loads(f.read_text(encoding="utf-8")))

    @property
    def spoken_parts(self) -> list[str]:
        """What the voice reads: each section's title, then its paragraphs."""
        out: list[str] = []
        for s in self.sections:
            out.append(s["title"])
            out.extend(s["paragraphs"])
        return out


def advance(progress: Progress, section_end: int, section_count: int, part_count: int,
            library: list[fetch.Book]) -> Progress:
    """Where tomorrow starts."""
    if section_end < section_count:
        return Progress(book=progress.book, part=progress.part, section=section_end)
    if progress.part + 1 < part_count:
        return Progress(book=progress.book, part=progress.part + 1, section=0)
    return Progress(book=next_book_slug(progress.book, library), part=0, section=0)


def plan_day(day: date, words_per_day: int) -> Reading:
    """Today's reading. If it was already planned, the same one is returned.
    Otherwise it is planned from the progress file, and progress moves on."""
    folder = day_dir(day)
    existing = Reading.load(folder)
    if existing is not None:
        log.info("plan: %s was already planned (%s, part %d, sections %d-%d)", day, existing.book_title,
                 existing.part_index + 1, existing.section_start + 1, existing.section_end)
        return existing

    library = fetch.catalog()
    progress = Progress.load()
    if progress is None:
        progress = Progress(book=next_book_slug(None, library), part=0, section=0)
        log.info("plan: starting from the beginning with %s", progress.book)
    books = {b.slug: b for b in library}
    if progress.book not in books:
        raise PlanError(f"book {progress.book!r} is not in the library any more")
    book = books[progress.book]
    parts = fetch.parts_of(book)
    if progress.part >= len(parts):
        raise PlanError(f"part {progress.part} does not exist in {book.title!r} ({len(parts)} parts)")
    part = parts[progress.part]
    sections = fetch.sections_of(part)
    if progress.section >= len(sections):
        raise PlanError(f"section {progress.section} does not exist in part {part.title!r}")

    end = pick_sections(sections, progress.section, words_per_day)
    chosen = sections[progress.section:end]
    after = advance(progress, end, len(sections), len(parts), library)
    reading = Reading(
        day=day.isoformat(),
        book_slug=book.slug, book_title=book.title, book_url=book.url,
        part_index=progress.part, part_count=len(parts), part_title=part.title, part_url=part.url,
        section_start=progress.section, section_end=end, section_count=len(sections),
        sections=[{"title": s.title, "paragraphs": s.paragraphs} for s in chosen],
        words=sum(s.words for s in chosen),
        progress_before=asdict(progress), progress_after=asdict(after),
    )
    reading.save(folder)
    after.save()
    log.info("plan: %s, part %d/%d, sections %d-%d of %d, %d words. Tomorrow: %s",
             book.title, progress.part + 1, len(parts), progress.section + 1, end, len(sections),
             reading.words, asdict(after))
    return reading


def undo_day(day: date) -> None:
    """Forget today's plan, so --force can plan it again from the same place."""
    folder = day_dir(day)
    reading = Reading.load(folder)
    if reading is None:
        return
    Progress(**reading.progress_before).save()
    for f in folder.iterdir():
        if f.is_file():
            f.unlink()
        else:
            import shutil
            shutil.rmtree(f)
    log.info("plan: %s forgotten; progress set back to %s", day, reading.progress_before)
