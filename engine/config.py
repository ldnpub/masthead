"""Paths, settings, and language helpers. No network."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
ENGINE = Path(__file__).resolve().parent

for _bin in (ROOT / ".venv" / "bin", Path("/opt/homebrew/bin"), Path("/usr/local/bin")):
    if _bin.is_dir():
        _entry = str(_bin)
        if _entry not in os.environ.get("PATH", ""):
            os.environ["PATH"] = _entry + os.pathsep + os.environ.get("PATH", "")

FEED_PATHS = {
    "article": "/feed.xml",
    "x": "/x.xml",
    "video": "/videos.xml",
    "learn": "/learn.xml",
    "web": "/readings.xml",
}
COVER_NAMES = {
    "article": "articles",
    "x": "x",
    "video": "videos",
    "learn": "learn",
    "web": "readings",
}
DEFAULT_VOICE = "en-US-AriaNeural"
UA = "Mozilla/5.0 (compatible; Masthead/1.0; personal audio reader)"

MONTHS = {
    "en": ["", "January", "February", "March", "April", "May", "June",
           "July", "August", "September", "October", "November", "December"],
    "fr": ["", "janvier", "février", "mars", "avril", "mai", "juin",
           "juillet", "août", "septembre", "octobre", "novembre", "décembre"],
}
MONTHS_ABBR = {
    "en": ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "fr": ["", "janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."],
}
WEEKDAYS = {
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "fr": ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"],
}


class JobError(Exception):
    pass


def data_dir() -> Path:
    return Path(os.environ.get("MASTHEAD_DATA", ROOT / "data"))


def config_path() -> Path:
    if os.environ.get("STUDIO_DEMO") == "1" and not os.environ.get("STUDIO_CONFIG"):
        session = data_dir() / "demo-session.json"
        if session.exists():
            return session
        return ROOT / "examples" / "demo-config.json"
    return Path(os.environ.get("STUDIO_CONFIG", ROOT / "studio-config.json"))


def demo() -> bool:
    return os.environ.get("STUDIO_DEMO") == "1"


def load_cfg() -> dict:
    path = config_path()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_cfg(cfg: dict):
    path = config_path()
    if demo() and path.name == "demo-config.json":
        path = data_dir() / "demo-session.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def lang_of(cfg: dict | None = None) -> str:
    cfg = cfg if cfg is not None else load_cfg()
    raw = str(((cfg.get("ui") or {}).get("lang") or "en")).lower()
    return "fr" if raw.startswith("fr") else "en"


def zone_of(cfg: dict | None = None):
    cfg = cfg if cfg is not None else load_cfg()
    name = str(((cfg.get("ui") or {}).get("timezone") or "")).strip()
    if name:
        return ZoneInfo(name)
    return datetime.now().astimezone().tzinfo


def public_base(cfg: dict | None = None) -> str:
    cfg = cfg if cfg is not None else load_cfg()
    explicit = ((cfg.get("publish") or {}).get("publicBaseUrl") or os.environ.get("MASTHEAD_PUBLIC_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit
    port = os.environ.get("PORT", "8741")
    host = os.environ.get("HOST", "127.0.0.1")
    if host in ("0.0.0.0", "::"):
        host = "127.0.0.1"
    return f"http://{host}:{port}"


def use_r2(cfg: dict | None = None) -> bool:
    cfg = cfg if cfg is not None else load_cfg()
    cloud = cfg.get("cloudflare") or {}
    token = cloud.get("token") or os.environ.get("CLOUDFLARE_API_TOKEN", "")
    bucket = cloud.get("bucket") or os.environ.get("R2_BUCKET", "")
    account = cloud.get("accountId") or os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    return bool(token and bucket and account)


def cloudflare_creds(cfg: dict | None = None) -> tuple[str, str, str]:
    cfg = cfg if cfg is not None else load_cfg()
    cloud = cfg.get("cloudflare") or {}
    token = cloud.get("token") or os.environ.get("CLOUDFLARE_API_TOKEN", "")
    bucket = cloud.get("bucket") or os.environ.get("R2_BUCKET", "")
    account = cloud.get("accountId") or os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    if not (token and bucket and account):
        raise JobError(
            "Cloudflare is not configured. Add an account id, bucket name, and API token "
            "in Compose, or run ./setup.sh. Until then, episodes stay on this computer."
        )
    return account, token, bucket


def tts_tuple(cfg: dict, override: dict | None = None) -> tuple[str, str, int, str]:
    t = dict(cfg.get("tts") or {})
    t.update(override or {})
    engine = t.get("engine") or "edge"
    voice = t.get("voice") or DEFAULT_VOICE
    try:
        rate = int(t.get("rate") or 0)
    except (TypeError, ValueError):
        rate = 0
    return engine, voice, rate, t.get("piperModel") or ""


def feed_path(kind: str | None) -> str:
    key = (kind or "article").lower()
    if key == "thread":
        key = "x"
    return FEED_PATHS.get(key, "/feed.xml")


def log(*parts):
    print(*parts, flush=True)
