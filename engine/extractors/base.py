"""Pluggable article extractors.

An extractor turns HTML the reader is allowed to fetch into plain text Masthead
can speak. Adapters live in ``engine/extractors/`` (built in) or ``extractors/``
at the repository root (yours, never committed). See docs/private-feeds.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field


class ExtractError(Exception):
    """The page did not match what this extractor understands."""


@dataclass
class Article:
    title: str
    author: str = ""
    site: str = ""
    published: str | None = None
    blocks: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(self.blocks)

    @property
    def words(self) -> int:
        return sum(len(b.replace("#H# ", "").split()) for b in self.blocks)


class Extractor:
    """Override ``id``, ``description``, ``matches``, and ``extract``."""

    id = "base"
    description = ""

    def matches(self, url: str) -> bool:
        """True when this adapter should handle ``url`` in automatic mode.

        Return False for a generic fallback. Masthead calls ``matches`` only
        when the source does not name an extractor.
        """
        return False

    def extract(self, url: str, html: str) -> Article:
        """Return an Article. Raise ExtractError if the markup is not yours.

        ``blocks`` is a list of paragraphs. Prefix a heading with ``#H# ``
        (Masthead turns those into chapters). Do not invent missing text.
        """
        raise ExtractError("extract() is not implemented")
