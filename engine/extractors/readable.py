"""Generic reading extractor. No site-specific rules."""
from __future__ import annotations

import html as htmlmod
import re
from html.parser import HTMLParser
from urllib.parse import urlparse

from .base import Article, Extractor


class _ReadableParser(HTMLParser):
    SKIP = {
        "script", "style", "noscript", "template", "nav", "header", "footer",
        "aside", "form", "svg", "button", "select", "iframe", "figure",
    }
    BLOCKS = {"p", "h1", "h2", "h3", "h4", "li", "blockquote", "pre"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.stack: list[tuple[str, bool]] = []
        self.buf: list[str] = []
        self.cur: str | None = None
        self.blocks: list[tuple[str, str]] = []
        self.title = ""
        self.in_title = False
        self.meta: dict[str, str] = {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key and a.get("content"):
                self.meta[key] = a["content"]
            return
        if tag in ("br", "img", "input", "hr", "link", "source", "wbr"):
            return
        cls = ((a.get("class") or "") + " " + (a.get("id") or "")).lower()
        bad = tag in self.SKIP or bool(re.search(
            r"\b(comment|share|social|newsletter|cookie|related|sidebar|menu|breadcrumb|footer|promo|advert|popup|modal)\b",
            cls,
        ))
        self.stack.append((tag, bad))
        if bad:
            self.skip += 1
        if tag == "title":
            self.in_title = True
        if tag in self.BLOCKS and not self.skip:
            self.flush()
            self.cur = tag

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag in self.BLOCKS:
            self.flush()
        while self.stack:
            opened, bad = self.stack.pop()
            if bad:
                self.skip -= 1
            if opened == tag:
                break

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if not self.skip and self.cur:
            self.buf.append(data)

    def flush(self):
        if self.cur:
            text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
            text = re.sub(r"\[(?:note |ref\.? )?\w{1,4}\]", "", text).strip()
            if text:
                self.blocks.append((self.cur, text))
        self.buf = []
        self.cur = None


def parse_readable(html: str) -> tuple[dict, list[str]]:
    parser = _ReadableParser()
    parser.feed(html)
    parser.flush()
    out: list[str] = []
    for tag, text in parser.blocks:
        if tag.startswith("h"):
            if 3 <= len(text) <= 160:
                out.append("#H# " + text)
        elif len(text) >= 60 or (tag == "li" and len(text) >= 40) or (
            out and len(text) >= 25 and text[-1:] in ".!?»\"'"
        ):
            out.append(text)
    clean: list[str] = []
    for block in out:
        if not clean or clean[-1] != block:
            clean.append(block)
    while clean and clean[-1].startswith("#H# "):
        clean.pop()
    meta = {
        "title": (parser.meta.get("og:title") or htmlmod.unescape(parser.title)).strip(),
        "site": (parser.meta.get("og:site_name") or "").strip(),
        "author": (parser.meta.get("author") or parser.meta.get("article:author") or "").strip(),
        "published": (parser.meta.get("article:published_time") or parser.meta.get("date") or "").strip(),
    }
    return meta, clean


class ReadableExtractor(Extractor):
    id = "readable"
    description = (
        "Generic article text: headings and paragraphs, skipping navigation, "
        "comments, and newsletter blocks. Used when no adapter matches."
    )

    def matches(self, url: str) -> bool:
        return False

    def extract(self, url: str, html: str) -> Article:
        meta, blocks = parse_readable(html)
        title = meta["title"]
        if blocks and blocks[0].replace("#H# ", "").strip().lower() == title.lower():
            blocks = blocks[1:]
        site = meta["site"] or urlparse(url).netloc.replace("www.", "")
        return Article(
            title=title or site or "Untitled",
            author=meta["author"],
            site=site,
            published=meta["published"] or None,
            blocks=blocks,
        )
