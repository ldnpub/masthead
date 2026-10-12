"""Example adapter for a fictional subscriber site.

Host: members.example-press.test
This is a teaching extractor. It does not target a real publisher. Copy it to
``extractors/your_site.py`` and change the host plus the selectors to match a
site you subscribe to. Keep that copy out of git (the ``extractors/`` directory
is ignored). Never commit session cookies or private feed URLs.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urlparse

from .base import Article, ExtractError, Extractor

_HOSTS = {"members.example-press.test"}


class _MemberParser(HTMLParser):
    """Collect text inside <article class="member-body"> only."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.capture = 0
        self.skip = 0
        self.tag: str | None = None
        self.buf: list[str] = []
        self.blocks: list[str] = []
        self.h1 = ""
        self.author = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.depth += 1
        if tag == "article":
            classes = (a.get("class") or "").split()
            if "member-body" in classes and self.capture == 0:
                self.capture = self.depth
                self.author = (a.get("data-author") or "").strip()
            return
        if not self.capture:
            return
        if tag in ("script", "style"):
            self.skip += 1
            return
        if tag in ("p", "h1", "h2", "h3", "blockquote", "li"):
            self.flush()
            self.tag = tag

    def handle_endtag(self, tag):
        if self.capture and tag in ("p", "h1", "h2", "h3", "blockquote", "li"):
            self.flush()
        if tag in ("script", "style") and self.skip:
            self.skip -= 1
        if tag == "article" and self.capture == self.depth:
            self.flush()
            self.capture = 0
        self.depth = max(0, self.depth - 1)

    def handle_data(self, data):
        if self.capture and not self.skip and self.tag:
            self.buf.append(data)

    def flush(self):
        text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        self.buf = []
        tag, self.tag = self.tag, None
        if not text:
            return
        if tag == "h1" and not self.h1:
            self.h1 = text
            return
        if tag in ("h2", "h3"):
            self.blocks.append("#H# " + text)
        else:
            self.blocks.append(text)


class ExampleMemberPress(Extractor):
    id = "example-member-press"
    description = (
        "Fictional subscriber site members.example-press.test. "
        "Copy this class when you write an adapter for a site you pay for."
    )

    def matches(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return host in _HOSTS

    def extract(self, url: str, html: str) -> Article:
        parser = _MemberParser()
        parser.feed(html)
        parser.flush()
        if not parser.blocks and not parser.h1:
            raise ExtractError(
                "example-member-press: no <article class=\"member-body\">. "
                "This sample only understands the fictional markup in docs/private-feeds.md."
            )
        return Article(
            title=parser.h1 or "Member article",
            author=parser.author,
            site="Example Press",
            blocks=parser.blocks,
        )
