"""Episode library: local files, or Cloudflare R2 when you configure it."""
from __future__ import annotations

import fcntl
import json
import os
import urllib.error
import urllib.parse
from datetime import datetime

from config import COVER_NAMES, JobError, cloudflare_creds, data_dir, demo, feed_path, load_cfg, log, public_base, use_r2, zone_of
from http_client import http_get, safe_url


def _r2_url(key: str, cfg=None) -> tuple[str, str]:
    account, token, bucket = cloudflare_creds(cfg)
    url = (
        f"https://api.cloudflare.com/client/v4/accounts/{account}/r2/buckets/{bucket}/objects/"
        + urllib.parse.quote(key, safe="/")
    )
    return url, token


def r2_get(key: str) -> bytes | None:
    url, token = _r2_url(key)
    try:
        _status, body, _headers, _final = http_get(url, headers={"Authorization": f"Bearer {token}"}, timeout=120)
        return body
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise JobError(f"R2 read failed for {key}: HTTP {exc.code}") from exc


def r2_put(key: str, data: bytes, content_type: str):
    import time
    import urllib.request
    url, token = _r2_url(key)
    last = ""
    for attempt in range(3):
        req = urllib.request.Request(
            url,
            data=data,
            method="PUT",
            headers={"Authorization": f"Bearer {token}", "Content-Type": content_type, "User-Agent": "Masthead/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=600) as res:
                res.read()
                return
        except urllib.error.HTTPError as exc:
            last = f"HTTP {exc.code}"
        except Exception as exc:
            last = str(exc)
        log(f"  R2 write {key} failed ({last}), retrying…")
        time.sleep(2 * (attempt + 1))
    raise JobError(f"Could not write {key} to R2: {last}")


def r2_delete(key: str):
    import urllib.request
    url, token = _r2_url(key)
    req = urllib.request.Request(url, method="DELETE", headers={"Authorization": f"Bearer {token}", "User-Agent": "Masthead/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            res.read()
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise JobError(f"R2 delete failed for {key}: HTTP {exc.code}") from exc


def _demo_feed() -> list:
    from pathlib import Path
    from config import ROOT
    path = Path(os.environ.get("MASTHEAD_DEMO_FEED", ROOT / "examples" / "demo-feed.json"))
    return json.loads(path.read_text(encoding="utf-8"))


def feed_get() -> list:
    if demo():
        data = _demo_feed()
    elif use_r2():
        raw = r2_get("feed.json")
        if raw is None:
            return []
        data = json.loads(raw.decode("utf-8"))
    else:
        path = data_dir() / "feed.json"
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise JobError("feed.json is not a list. Refusing to change the library.")
    return data


def _write_feed_bytes(raw: bytes):
    path = data_dir() / "feed.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_bytes(raw)
    tmp.replace(path)
    if use_r2():
        r2_put("feed.json", raw, "application/json; charset=utf-8")


def feed_modify(mutator, reason: str = ""):
    """Read the latest library, back it up, run mutator(feed), and write it back."""
    if demo():
        raise JobError("Demo mode is read-only. Stop the demo server and run npm start to publish.")
    folder = data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    backups = folder / "backups"
    backups.mkdir(exist_ok=True)
    with open(folder / "feed.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        feed = feed_get()
        before = json.dumps(feed, ensure_ascii=False, indent=2).encode("utf-8")
        stamp = datetime.now(zone_of()).strftime("%Y%m%d-%H%M%S")
        (backups / f"feed.backup-{stamp}.json").write_bytes(before)
        olds = sorted(backups.glob("feed.backup-*.json"))
        for old in olds[:-60]:
            old.unlink(missing_ok=True)
        if use_r2() and feed:
            try:
                r2_put(f"backups/feed.backup-{stamp}.json", before, "application/json; charset=utf-8")
            except JobError as exc:
                log(f"  (remote backup skipped: {exc})")
        updated = mutator(feed)
        if not isinstance(updated, list):
            raise JobError("The library update did not return a list.")
        if len(feed) > 3 and len(updated) < len(feed) // 2:
            raise JobError("Refusing to drop more than half the episodes. Restore a backup if this was intentional.")
        raw = json.dumps(updated, ensure_ascii=False, indent=2).encode("utf-8")
        _write_feed_bytes(raw)
        log(f"Library updated ({len(feed)} → {len(updated)} episodes). Backup feed.backup-{stamp}.json {reason}")
        return updated


def merge_episode(episode: dict):
    def mutate(feed):
        return [item for item in feed if item.get("id") != episode["id"]] + [episode]
    return feed_modify(mutate, f"(+ {episode['id']})")


def ensure_new_id(episode_id: str, force: bool = False):
    if force:
        return
    if any(item.get("id") == episode_id for item in feed_get()):
        raise JobError(f"Already in the library: {episode_id}")


def put_bytes(key: str, data: bytes, content_type: str):
    """Store under data/ for local mode, and in R2 when configured."""
    relative = data_dir() / key
    relative.parent.mkdir(parents=True, exist_ok=True)
    relative.write_bytes(data)
    if use_r2():
        r2_put(key, data, content_type)


def delete_bytes(key: str):
    path = data_dir() / key
    path.unlink(missing_ok=True)
    if use_r2():
        r2_delete(key)


def episode_audio_url(episode: dict, cfg=None) -> str:
    if episode.get("audioUrl"):
        return episode["audioUrl"]
    base = public_base(cfg or load_cfg())
    return f"{base}/audio/{urllib.parse.quote(episode['id'])}.mp3"


def episode_feed_url(episode: dict, cfg=None) -> str:
    base = public_base(cfg or load_cfg())
    return base + feed_path(episode.get("kind"))


def cover_url(kind: str, cfg=None) -> str:
    base = public_base(cfg or load_cfg())
    name = COVER_NAMES.get((kind or "article").lower(), "articles")
    return f"{base}/covers/{name}.png"
