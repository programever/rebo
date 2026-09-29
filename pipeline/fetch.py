"""Step 1: read the books from langmai.org.

Three kinds of page:
  * the catalog: the list of books,
  * a book page: its parts (the side menu),
  * a part page: the text, split into sections by the small headings.

Pages are fetched once and kept in out/cache, so a rerun does not ask the site
again. We only ever need one part page per day, so the site is barely touched.
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from bs4 import BeautifulSoup, Tag

from .config import CACHE_DIR, CATALOG_URL

log = logging.getLogger(__name__)

USER_AGENT = "rebo (a private daily reader; contact tdtrinh.web@gmail.com)"


class FetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class Book:
    slug: str
    title: str
    url: str


@dataclass(frozen=True)
class Part:
    slug: str
    title: str
    url: str


@dataclass
class Section:
    title: str
    paragraphs: list[str] = field(default_factory=list)

    @property
    def words(self) -> int:
        return sum(len(p.split()) for p in self.paragraphs)


# ---------- getting pages ----------

def _norm(url: str) -> str:
    return url if url.endswith("/") else url + "/"


def _slug(url: str) -> str:
    return _norm(url).rstrip("/").rsplit("/", 1)[-1]


def get_html(url: str, cache_dir: Path = CACHE_DIR, tries: int = 3) -> str:
    """The page text, from the cache if we already have it."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(_norm(url).encode("utf-8")).hexdigest()[:16]
    cached = cache_dir / f"{key}.html"
    if cached.is_file() and cached.stat().st_size > 0:
        return cached.read_text(encoding="utf-8")
    last: Exception | None = None
    for attempt in range(1, tries + 1):
        try:
            with httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=30) as client:
                answer = client.get(url)
            if answer.status_code != 200:
                raise FetchError(f"{url} answered {answer.status_code}")
            text = answer.text
            if "<html" not in text[:2000].lower():
                raise FetchError(f"{url} did not answer with a web page")
            cached.write_text(text, encoding="utf-8")
            return text
        except (httpx.HTTPError, FetchError) as err:
            last = err
            log.warning("fetch: try %d of %d failed for %s (%s)", attempt, tries, url, err)
            if attempt < tries:
                time.sleep(5 * attempt)
    raise FetchError(str(last))


# ---------- reading pages ----------

def _clean(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text.strip()


def parse_catalog(html: str, catalog_url: str = CATALOG_URL) -> list[Book]:
    """All books in the library, in the order the page shows them."""
    soup = BeautifulSoup(html, "html.parser")
    base = _norm(catalog_url)
    books: list[Book] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = _norm(a["href"])
        if not href.startswith(base) or href == base:
            continue
        rest = href[len(base):].strip("/")
        if "/" in rest or not rest:
            continue  # a part page, not a book page
        title = _clean(a.get_text(" "))
        if href in seen or not title:
            continue
        seen.add(href)
        books.append(Book(slug=rest, title=title, url=href))
    if not books:
        raise FetchError("the catalog page has no books in it; the site may have changed")
    return books


def parse_parts(html: str, book_url: str) -> list[Part]:
    """The parts (chapters) of one book, in reading order, from its side menu."""
    soup = BeautifulSoup(html, "html.parser")
    base = _norm(book_url)
    menu = soup.find(id="menu-side") or soup.find(id="side-menu") or soup
    parts: list[Part] = []
    seen: set[str] = set()
    for a in menu.find_all("a", href=True):
        href = _norm(a["href"])
        if not href.startswith(base) or href == base:
            continue
        title = _clean(a.get_text(" "))
        if href in seen or not title:
            continue
        seen.add(href)
        parts.append(Part(slug=_slug(href), title=title, url=href))
    if not parts:
        raise FetchError(f"no parts found in {book_url}; the site may have changed")
    return parts


def _content_root(soup: BeautifulSoup) -> Tag:
    for selector in ("div.the-content", "div.entry-content", "article"):
        node = soup.select_one(selector)
        if node is not None:
            return node
    raise FetchError("no text container found; the site may have changed")


# A <br> becomes this character, so a line break the writer meant can be told
# apart from a plain newline in the page source (which is only white space).
LINE_BREAK = "\u2028"
# A heading written as a short bold line in capitals is at most this long.
HEADING_MAX_CHARS = 120


def _has_letters(text: str) -> bool:
    return any(c.isalnum() for c in text)


def _is_heading_paragraph(node: Tag) -> bool:
    """Some parts mark a section not with a heading tag but with a short bold
    line in capitals, like <p><strong>DÒNG SÔNG CẢM THỌ</strong></p>. Part II
    and III of "An lạc từng bước chân" are written that way (found 2026-09-29)."""
    text = _clean(node.get_text(" ").replace(LINE_BREAK, " "))
    if not text or len(text) > HEADING_MAX_CHARS or "\n" in text:
        return False
    if not _has_letters(text) or text != text.upper():
        return False
    bold = " ".join(_clean(b.get_text(" ")) for b in node.find_all(["strong", "b"]))
    return "".join(bold.split()) == "".join(text.split())


def parse_sections(html: str, part_title: str) -> list[Section]:
    """The text of one part page, split into sections by its headings.

    A heading is an h2/h3/h4, or a short bold line in capitals on its own.
    Text before the first heading becomes a section named after the part.
    Inside a paragraph, only a <br> starts a new line; bold or italic words
    stay in their sentence. Lines with no letters (a lone dash or dot) are
    dropped: they broke the voice on 2026-09-28 and 2026-09-29."""
    soup = BeautifulSoup(html, "html.parser")
    root = _content_root(soup)
    for junk in root.select("script, style, nav, .sharedaddy, .jp-relatedposts, #side-menu, .wp-block-image, figure"):
        junk.decompose()
    for br in root.find_all("br"):
        br.replace_with(LINE_BREAK)

    sections: list[Section] = []
    current: Section | None = None

    def open_section(title: str) -> None:
        nonlocal current
        if current is not None and current.paragraphs:
            sections.append(current)
        current = Section(title=title)

    def add_text(text: str) -> None:
        nonlocal current
        pieces = [_clean(piece.replace("\n", " ")) for piece in text.split(LINE_BREAK)]
        pieces = [piece for piece in pieces if _has_letters(piece)]
        if not pieces:
            return
        if current is None:
            open_section(part_title)
        assert current is not None
        current.paragraphs.extend(pieces)

    for node in root.descendants:
        if not isinstance(node, Tag):
            continue
        name = node.name.lower()
        if name in ("h2", "h3", "h4"):
            title = _clean(node.get_text(" ").replace(LINE_BREAK, " "))
            if title:
                open_section(title)
            continue
        if name == "h1":
            continue  # the part title; already known
        if name in ("p", "li", "blockquote"):
            if node.find(["p", "li", "blockquote"]) is not None:
                continue  # a box that holds smaller pieces; those come next
            if name == "p" and _is_heading_paragraph(node):
                open_section(_clean(node.get_text(" ").replace(LINE_BREAK, " ")))
                continue
            add_text(node.get_text(""))
    if current is not None and current.paragraphs:
        sections.append(current)
    if not sections:
        raise FetchError(f"no text found for part {part_title!r}")
    return sections


# ---------- the three steps together ----------

def catalog() -> list[Book]:
    return parse_catalog(get_html(CATALOG_URL))


def parts_of(book: Book) -> list[Part]:
    return parse_parts(get_html(book.url), book.url)


def sections_of(part: Part) -> list[Section]:
    return parse_sections(get_html(part.url), part.title)
