"""Load built-in extractors and personal adapters from /extractors."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from .base import Article, ExtractError, Extractor
from .example_member_press import ExampleMemberPress
from .readable import ReadableExtractor

ROOT = Path(__file__).resolve().parent.parent.parent
USER_DIR = ROOT / "extractors"

__all__ = [
    "Article",
    "ExtractError",
    "Extractor",
    "choose_extractor",
    "load_extractors",
]


def _user_instances(path: Path) -> list[Extractor]:
    """Load a personal adapter. Relative imports (from .base) keep working."""
    name = f"extractors._user_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path.name}")
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "extractors"
    sys.modules[name] = module
    spec.loader.exec_module(module)
    found: list[Extractor] = []
    for obj in vars(module).values():
        if isinstance(obj, type) and issubclass(obj, Extractor) and obj is not Extractor:
            if getattr(obj, "id", "base") == "base":
                continue
            found.append(obj())
    return found


def load_extractors() -> tuple[list[Extractor], list[dict]]:
    """Return (extractors, load errors). A personal adapter overrides a built-in id."""
    errors: list[dict] = []
    by_id: dict[str, Extractor] = {ExampleMemberPress.id: ExampleMemberPress()}
    if USER_DIR.is_dir():
        for path in sorted(USER_DIR.glob("*.py")):
            if path.name.startswith("_"):
                continue
            try:
                for ext in _user_instances(path):
                    by_id[ext.id] = ext
            except Exception as exc:
                errors.append({"file": path.name, "error": str(exc)})
    rest = [ext for key, ext in by_id.items() if key != "readable"]
    rest.sort(key=lambda ext: ext.id)
    return rest + [by_id.get("readable", ReadableExtractor())], errors


def choose_extractor(url: str, explicit: str | None = None) -> Extractor:
    extractors, _errors = load_extractors()
    by_id = {ext.id: ext for ext in extractors}
    name = (explicit or "").strip()
    if name and name != "auto":
        if name not in by_id:
            raise ExtractError(f"Unknown extractor '{name}'.")
        return by_id[name]
    for ext in extractors:
        if ext.id == "readable":
            continue
        try:
            if ext.matches(url):
                return ext
        except Exception:
            continue
    return by_id["readable"]
