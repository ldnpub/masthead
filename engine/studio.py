#!/usr/bin/env python3
"""Masthead engine. Stdlib plus ffmpeg, edge-tts or Piper, and yt-dlp.

Usage: studio.py <command> '<json>'   or   studio.py <command> -
Logs go to stdout. The last line is RESULT {json}.
"""
from __future__ import annotations

import hashlib
import html as htmlmod
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (  # noqa: E402
    FEED_PATHS, MONTHS, MONTHS_ABBR, ROOT, WEEKDAYS, JobError, data_dir, demo,
    feed_path, lang_of, load_cfg, log, public_base, tts_tuple, use_r2, zone_of,
)
from extractors import ExtractError, choose_extractor, load_extractors  # noqa: E402
from http_client import decode_body, host_of, http_get, http_json, public_link, safe_url, source_headers  # noqa: E402
from speak import (  # noqa: E402
    auto_sections, edge_cmd, heading_sections, probe, publish_audio, smart_sections,
    spoken_date, synthesize, tool, tts_and_publish, voice_label,
)
from storage import ensure_new_id, feed_get, feed_modify, r2_delete  # noqa: E402

MIN_ARTICLE_WORDS = 80
MIN_WEB_WORDS = 120

RIGHTS = {
    "en": "Personal copy. You are responsible for the rights to this recording.",
    "fr": "Copie personnelle. Vous êtes responsable des droits sur cet enregistrement.",
}
PREVIEW = {
    "en": "This is Masthead. A short preview of the voice you picked.",
    "fr": "Ici Masthead. Un court aperçu de la voix que vous avez choisie.",
}
PART = {"en": "Part", "fr": "Partie"}
INTRO_CH = {"en": "Introduction", "fr": "Introduction"}

PROMPTS = {
    "en": """You write a rigorous spoken script. In English, write the AUDIO script of a short lesson about: "{sujet}" (episode {numero}: {angle}).
Progressive method: 1) the idea in one concrete image; 2) the precise mechanism; 3) the limits, debates, and received ideas; 4) a three-sentence recap.
Never mention age levels. Present as settled only what several serious sources agree on. Do not invent a citation; if you are unsure of a source, leave it out.
Spoken style: short sentences, no bullet lists, no markdown, no URLs, numbers written to be read aloud. Aim for about {mots} words.
End with a line "SOURCES:" listing the real sources you used (author, title, year). That line will not be read aloud.""",
    "fr": """Tu es un vulgarisateur rigoureux. Écris en français le script AUDIO d'un mini-cours sur : « {sujet} » (épisode {numero} : {angle}).
Méthode progressive : 1) l'idée simple avec une image concrète ; 2) le mécanisme précis ; 3) les nuances, limites, débats et idées reçues ; 4) un récapitulatif en 3 phrases.
Ne mentionne jamais de niveaux d'âge. Ne présente comme établi que ce qui est recoupé par plusieurs sources sérieuses. N'invente aucune référence ; si tu n'es pas sûr d'une source, ne la cite pas.
Style oral : phrases courtes, pas de listes à puces, pas de markdown, pas d'URL, chiffres écrits pour être lus. Longueur visée : environ {mots} mots.
Termine par une ligne « SOURCES : » listant les sources réelles utilisées (auteur, titre, année) — cette ligne ne sera pas lue.""",
}
DIGEST_PROMPTS = {
    "en": """Write a spoken {periode} digest, in English, of posts by @{handle} ({nom}), from {debut} to {fin}.
Strict rules:
- Use ONLY the posts below. Invent nothing: no extra facts, numbers, or outside opinions.
- Group the ideas into 3 to 7 themes. Start each theme with a line by itself: "## Theme name".
- Summarize faithfully, citing dates ("on Tuesday 6 October, they say that…"). Attribute every claim to the author.
- Spoken style: short sentences, no bullets, no markdown except the "##" lines, no URLs.
- Begin with two introductory sentences (before the first "##") and end with a theme "## In brief" of three sentences.
Posts:
{posts}""",
    "fr": """Tu prépares le script AUDIO, en français, d'un résumé {periode} des posts publiés par le compte @{handle} ({nom}), du {debut} au {fin}.
Règles strictes :
- N'utilise QUE les posts fournis ci-dessous. N'invente rien, n'ajoute aucun fait, aucun chiffre, aucune opinion extérieure.
- Regroupe les idées par grands thèmes (3 à 7). Commence chaque thème par une ligne seule « ## Nom du thème ».
- Résume fidèlement, en citant les dates (« le mardi 6 octobre, l'auteur affirme que… »). Attribue toujours les propos à l'auteur.
- Style oral : phrases courtes, pas de listes à puces, pas de markdown sauf les lignes « ## », pas d'URL.
- Commence par deux phrases d'introduction (avant le premier « ## ») et termine par un thème « ## En bref » de trois phrases.
Posts :
{posts}""",
}


def L() -> str:
    return lang_of()


def rights() -> str:
    return RIGHTS[L()]


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFD", value.lower())
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")[:70]


def decode_xml(value: str) -> str:
    value = re.sub(r"<!\[CDATA\[([\s\S]*?)\]\]>", r"\1", value or "")
    return htmlmod.unescape(value).strip()


def tag_text(block: str, name: str) -> str:
    match = re.search(rf"<{name}(?:\s[^>]*)?>([\s\S]*?)</{name}>", block, re.I)
    return decode_xml(match.group(1)) if match else ""


def parse_rss(xml: str) -> list[dict]:
    items = []
    for block in re.findall(r"<item\b[\s\S]*?</item>", xml, re.I):
        link = tag_text(block, "link")
        if not link:
            match = re.search(r'<link[^>]+href=["\']([^"\']+)["\']', block, re.I)
            link = match.group(1).strip() if match else ""
        content = tag_text(block, "content:encoded") or tag_text(block, "encoded")
        items.append({
            "title": tag_text(block, "title"),
            "url": link,
            "pubDate": tag_text(block, "pubDate") or tag_text(block, "dc:date"),
            "author": tag_text(block, "dc:creator") or tag_text(block, "author"),
            "contentHtml": content,
            "guid": tag_text(block, "guid"),
        })
    return [item for item in items if item["url"] or item["title"]]


def parse_atom(xml: str) -> list[dict]:
    items = []
    for block in re.findall(r"<entry\b[\s\S]*?</entry>", xml, re.I):
        link = ""
        for match in re.finditer(r"<link\b([^>]*)/?>", block, re.I):
            attrs = match.group(1)
            href = re.search(r'href=["\']([^"\']+)["\']', attrs)
            rel = re.search(r'rel=["\']([^"\']+)["\']', attrs)
            if href and (not rel or rel.group(1) in ("alternate", "")):
                link = href.group(1)
                break
        author = ""
        author_block = re.search(r"<author\b[\s\S]*?</author>", block, re.I)
        if author_block:
            author = tag_text(author_block.group(0), "name")
        items.append({
            "title": tag_text(block, "title"),
            "url": link,
            "pubDate": tag_text(block, "published") or tag_text(block, "updated"),
            "author": author,
            "contentHtml": tag_text(block, "content") or tag_text(block, "summary"),
            "guid": tag_text(block, "id"),
        })
    return [item for item in items if item["url"] or item["title"]]


def parse_feed(xml: str) -> list[dict]:
    head = xml[:800].lower()
    if "<feed" in head and "<entry" in xml.lower():
        return parse_atom(xml)
    return parse_rss(xml)


def html_words(fragment: str) -> int:
    text = re.sub(r"<[^>]+>", " ", fragment or "")
    text = htmlmod.unescape(text)
    return len(text.split())


def article_id_for(url: str) -> str:
    parts = urllib.parse.urlsplit(public_link(url))
    slug = slugify(parts.path.strip("/").split("/")[-1] or parts.netloc)[:48] or "item"
    digest = hashlib.sha1(public_link(url).encode()).hexdigest()[:8]
    return f"article-{slug}-{digest}"


def find_source(cfg: dict, source_id: str | None, url: str | None = None) -> dict | None:
    sources = [s for s in (cfg.get("sources") or []) if isinstance(s, dict)]
    if source_id:
        for source in sources:
            if source.get("id") == source_id:
                return source
        raise JobError(f"Unknown source: {source_id}")
    if url and len(sources) == 1:
        return sources[0]
    if url:
        host = host_of(url)
        for source in sources:
            if host and host == host_of(source.get("feedUrl") or ""):
                return source
    return None


def fetch_feed_items(source: dict) -> list[dict]:
    url = (source.get("feedUrl") or "").strip()
    if not url:
        raise JobError("This source has no feed URL.")
    try:
        _status, body, headers, _final = http_get(
            url, headers=source_headers(source), timeout=30,
            accept="application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        )
    except urllib.error.HTTPError as exc:
        raise JobError(f"Feed {host_of(url)} returned HTTP {exc.code}. Check the address and the saved login.") from exc
    except urllib.error.URLError as exc:
        raise JobError(f"Feed {host_of(url)} is unreachable: {exc.reason}") from exc
    return parse_feed(decode_body(body, headers))


def skipped_set() -> set[str]:
    path = data_dir() / "skipped.json"
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data if isinstance(data, list) else [])
    except Exception:
        return set()


def is_published(url: str, episodes: list) -> bool:
    link = public_link(url).rstrip("/")
    eid = article_id_for(url)
    for episode in episodes:
        if episode.get("id") == eid:
            return True
        other = public_link(episode.get("link") or "").rstrip("/")
        if link and other and link == other:
            return True
    return False


def extract_document(url: str, html: str, source: dict | None):
    explicit = ((source or {}).get("extractor") or "auto").strip() or "auto"
    try:
        return choose_extractor(url, explicit).extract(url, html)
    except ExtractError:
        if explicit not in ("", "auto", "readable"):
            raise
        return choose_extractor(url, "readable").extract(url, html)


def fetch_html(url: str, source: dict | None) -> tuple[str, str]:
    try:
        _status, body, headers, final = http_get(
            url, headers=source_headers(source), timeout=40,
            accept="text/html,application/xhtml+xml",
        )
    except urllib.error.HTTPError as exc:
        raise JobError(f"Page {host_of(url)} returned HTTP {exc.code}. The saved login may have expired.") from exc
    except urllib.error.URLError as exc:
        raise JobError(f"Page unreachable: {exc.reason}") from exc
    ctype = headers.get("Content-Type") or ""
    if "html" not in ctype and "xml" not in ctype and not body.lstrip().startswith(b"<"):
        raise JobError(f"This address is not an HTML page ({ctype or 'unknown type'}).")
    return decode_body(body, headers), final


def _byline(author: str, site: str, when: str) -> str:
    if L() == "fr":
        bits = []
        if author:
            bits.append(f"un article de {author}")
        else:
            bits.append("un article")
        if site:
            bits.append(f"publié sur {site}")
        if when:
            bits.append(f"le {when}")
        return ", ".join(bits).capitalize() + "."
    bits = ["An article"]
    if author:
        bits.append(f"by {author}")
    if site:
        bits.append(f"from {site}")
    if when:
        bits.append(f"published {when}")
    return " ".join(bits) + "."


def _parse_date(value: str | None) -> datetime:
    if not value:
        return datetime.now(zone_of())
    raw = value.strip()
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[:31], fmt)
        except ValueError:
            continue
    return datetime.now(zone_of())


def sections_from_blocks(blocks: list[str], intro: str):
    marked = intro + "\n\n" + "\n\n".join(blocks)
    sections = heading_sections(marked, INTRO_CH[L()], max_len=0)
    if len(sections) >= 2:
        return sections
    plain = intro + "\n\n" + "\n\n".join(b.replace("#H# ", "") for b in blocks)
    if len(plain) > 4000:
        return auto_sections(plain, label=PART[L()])
    return [(None, plain)]


def cmd_article(args: dict):
    cfg = load_cfg()
    url = (args.get("url") or "").split("#")[0].strip()
    if not url.startswith("http"):
        raise JobError("An http(s) article address is required.")
    source = find_source(cfg, args.get("sourceId"), url)
    log(f"Article: {safe_url(url)}")
    item = None
    if source:
        for candidate in fetch_feed_items(source):
            if public_link(candidate.get("url") or "") == public_link(url) or candidate.get("url") == url:
                item = candidate
                break
    content = (item or {}).get("contentHtml") or ""
    article = None
    if html_words(content) >= MIN_ARTICLE_WORDS:
        article = extract_document(url, content, source)
        if article.words < MIN_ARTICLE_WORDS:
            article = extract_document(url, f"<html><body>{content}</body></html>", {"extractor": "readable"})
        if article.words < MIN_ARTICLE_WORDS:
            article = None
    if article is None:
        html, final = fetch_html(url, source)
        article = extract_document(final, html, source)
        url = final
    if article.words < MIN_ARTICLE_WORDS:
        language = L()
        if language == "fr":
            raise JobError(
                f"Seulement {article.words} mots ont pu être lus. Si la source est privée, ajoutez le flux complet, "
                "un cookie de session ou un extracteur. Rien n'a été inventé."
            )
        raise JobError(
            f"Only {article.words} words could be read. If this source is private, add the full-text feed, "
            "a session cookie, or an extractor. Nothing was invented."
        )
    title = (args.get("title") or article.title or "Untitled").strip()
    author = article.author or (item or {}).get("author") or ""
    when_dt = _parse_date(article.published or (item or {}).get("pubDate"))
    when = spoken_date(when_dt, L())
    site = article.site or (host_of(url) if url else "")
    episode_id = article_id_for(url)
    if not args.get("dryRun"):
        ensure_new_id(episode_id, args.get("force"))
    intro = f"{title}. {_byline(author, site, when)}"
    if L() == "fr":
        intro += " Lecture intégrale."
    else:
        intro += " Full reading."
    sections = sections_from_blocks(article.blocks, intro)
    link = public_link(url)
    description = (
        f"{'Lecture intégrale' if L() == 'fr' else 'Full reading'} ({voice_label(cfg)})"
        f"{' depuis ' if L() == 'fr' else ' from '}{site or link}, {when}. {rights()}\n\nSource: {link}"
    )
    episode = {
        "title": title,
        "description": description,
        "pubDate": when_dt.astimezone(zone_of()).isoformat(timespec="seconds"),
        "guid": episode_id,
        "link": link,
        "kind": "article",
    }
    return tts_and_publish(episode_id, sections, episode, cfg, args.get("dryRun"))


def cmd_source_items(args: dict):
    if demo():
        return json.loads((ROOT / "examples" / "demo-sources.json").read_text(encoding="utf-8"))
    cfg = load_cfg()
    episodes = []
    try:
        episodes = feed_get()
    except JobError as exc:
        return {"sources": [], "error": str(exc)}
    skipped = skipped_set()
    out = []
    sources = cfg.get("sources") or []
    if args.get("sourceId"):
        sources = [s for s in sources if s.get("id") == args["sourceId"]]
    for source in sources:
        if not isinstance(source, dict):
            continue
        entry = {"id": source.get("id"), "label": source.get("label") or source.get("id"), "items": [], "error": None}
        try:
            for item in fetch_feed_items(source):
                url = item.get("url") or ""
                if not url:
                    continue
                entry["items"].append({
                    "title": item.get("title") or url,
                    "url": url,
                    "pubDate": item.get("pubDate") or "",
                    "author": item.get("author") or "",
                    "published": is_published(url, episodes),
                    "skipped": url in skipped or public_link(url) in skipped,
                    "hasFullText": html_words(item.get("contentHtml") or "") >= MIN_ARTICLE_WORDS,
                })
        except JobError as exc:
            entry["error"] = str(exc)
        out.append(entry)
    return {"sources": out}


def cmd_extractors(_args: dict):
    extractors, errors = load_extractors()
    return {
        "extractors": [{"id": ext.id, "description": ext.description} for ext in extractors],
        "errors": errors,
    }


def get_json(url: str, timeout: int = 30, tries: int = 4):
    err = None
    for attempt in range(tries):
        try:
            _status, payload, _headers = http_json(url, timeout=timeout)
            return payload
        except urllib.error.HTTPError as exc:
            err = exc
            if exc.code not in (404, 429, 500, 502, 503, 504):
                break
        except (urllib.error.URLError, TimeoutError) as exc:
            err = exc
        time.sleep(1.5 * (attempt + 1))
    raise JobError(f"Service unavailable ({host_of(url)}). fxtwitter is unofficial and may break. ({err})")


def parse_status(url: str):
    match = re.search(r"(?:x|twitter|fxtwitter|vxtwitter|fixupx)\.com/([^/]+)/status(?:es)?/(\d+)", url)
    if not match:
        raise JobError(f"Unrecognized X address: {safe_url(url)}")
    return match.group(1), match.group(2)


def tweet_text(tweet: dict) -> str:
    text = (tweet.get("raw_text") or {}).get("text") or tweet.get("text") or ""
    text = re.sub(r"https?://t\.co/\S+", "", text)
    text = re.sub(r"https?://\S+", "", text)
    return htmlmod.unescape(text).strip()


def short_title(text: str, n: int = 7) -> str:
    words = re.sub(r"\s+", " ", text).strip().split(" ")
    return " ".join(words[:n]).rstrip(",;:.") + ("…" if len(words) > n else "")


def x_one(url: str, cfg: dict, args: dict):
    user, status_id = parse_status(url)
    log(f"X post {user}/{status_id} via api.fxtwitter.com (unofficial)")
    payload = get_json(f"https://api.fxtwitter.com/2/thread/{status_id}")
    status = payload.get("status") or {}
    thread = payload.get("thread") or [status]
    if not status:
        raise JobError("Post not found via fxtwitter (deleted, private, or the unofficial API changed).")
    author = status.get("author") or {}
    handle = author.get("screen_name") or user
    name = re.sub(r"[^\w\s\-'’.]", "", author.get("name") or handle).strip() or handle
    episode_id = f"x-{handle.lower()}-{status_id}"
    if not args.get("dryRun"):
        ensure_new_id(episode_id, args.get("force"))
    seen, parts = set(), []
    if args.get("single"):
        thread = [status]
    for tweet in thread:
        screen = (tweet.get("author") or {}).get("screen_name", handle)
        if screen.lower() != handle.lower():
            continue
        if tweet.get("id") in seen:
            continue
        seen.add(tweet.get("id"))
        text = tweet_text(tweet)
        if text:
            parts.append(text)
    if not parts:
        raise JobError("Post has no readable text.")
    created = datetime.fromtimestamp(status.get("created_timestamp") or time.time(), timezone.utc)
    when = spoken_date(created, L())
    kind_word = ("Lecture du fil" if L() == "fr" else "Thread") if len(parts) > 1 else ("Lecture du post" if L() == "fr" else "Post")
    if L() == "fr":
        intro = f"Post de {name}, compte {handle} sur X. Publié le {when}. {kind_word}."
    else:
        intro = f"Post by {name}, @{handle} on X. Published {when}. {kind_word}."
    first = re.sub(r"\s+", " ", parts[0])[:70].rstrip()
    title = f"X — {name}: {first}{'…' if len(parts[0]) > 70 else ''}"
    link = f"https://x.com/{handle}/status/{status_id}"
    episode = {
        "title": title,
        "description": f"{intro} {rights()}\n\nSource: {link}",
        "pubDate": created.astimezone(zone_of()).isoformat(timespec="seconds"),
        "link": link,
        "guid": episode_id,
        "kind": args.get("kind") or "x",
    }
    if len(parts) > 1:
        label = "Post" if L() == "en" else "Post"
        sections = [(INTRO_CH[L()], intro)] + [(f"{label} {i + 1}/{len(parts)} — {short_title(part)}", part) for i, part in enumerate(parts)]
    else:
        body = auto_sections(parts[0], label=PART[L()]) if len(parts[0]) > 4000 else [(None, parts[0])]
        sections = [(INTRO_CH[L()], intro)] + [(t or ("Reading" if L() == "en" else "Lecture"), x) for t, x in body] if len(body) > 1 else [(None, intro + "\n\n" + parts[0])]
    quote = status.get("quote")
    if quote and tweet_text(quote):
        who = (quote.get("author") or {}).get("name", "")
        quoted = (f"Post cité, de {who} : " if L() == "fr" else f"Quoted post, by {who}: ") + tweet_text(quote)
        sections.append(("Post cité" if L() == "fr" else "Quoted post", quoted))
    log(f"{len(parts)} post(s)")
    return tts_and_publish(episode_id, sections, episode, cfg, args.get("dryRun"))


def cmd_x(args: dict):
    cfg = load_cfg()
    results = []
    for url in [u.strip() for u in args.get("urls") or [] if u.strip()]:
        try:
            results.append(x_one(url, cfg, args))
        except JobError as exc:
            log(f"FAILED {safe_url(url)}: {exc}")
            results.append({"url": safe_url(url), "error": str(exc)})
    if results and all("error" in item for item in results):
        raise JobError("; ".join(item["error"] for item in results))
    return {"items": results}


def cmd_x_timeline(args: dict):
    handle = str(args.get("handle") or "").lstrip("@").strip()
    if not re.fullmatch(r"\w{1,15}", handle):
        raise JobError("X handle should be 1–15 letters, numbers, or underscores.")
    payload = get_json(f"https://api.fxtwitter.com/2/profile/{urllib.parse.quote(handle)}/statuses?count={int(args.get('count', 20))}")
    have = {ep.get("id") for ep in feed_get()} if args.get("withFeed", True) and not demo() else set()
    posts = []
    for tweet in payload.get("results") or []:
        author = (tweet.get("author") or {}).get("screen_name", "")
        if tweet.get("reposted_by") or author.lower() != handle.lower():
            continue
        text = tweet_text(tweet)
        posts.append({
            "id": tweet.get("id"),
            "url": f"https://x.com/{author}/status/{tweet.get('id')}",
            "text": text,
            "chars": len(text),
            "date": tweet.get("created_timestamp"),
            "isReply": bool(tweet.get("replying_to")),
            "hasVideo": bool(((tweet.get("media") or {}).get("videos"))),
            "published": f"x-{author.lower()}-{tweet.get('id')}" in have,
        })
    return {"handle": handle, "posts": posts}


def cmd_video(args: dict):
    cfg = load_cfg()
    url = (args.get("url") or "").strip()
    yd = tool("yt-dlp")
    if not yd:
        raise JobError("yt-dlp is not installed. Run ./installer.sh.")
    log(f"yt-dlp metadata: {safe_url(url)}")
    result = subprocess.run([yd, "-J", "--no-playlist", url], capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        raise JobError("yt-dlp: " + result.stderr.strip()[-400:])
    info = json.loads(result.stdout)
    vid = re.sub(r"[^a-z0-9]+", "-", str(info.get("id", "")).lower()).strip("-")
    ext = re.sub(r"[^a-z0-9]+", "-", (info.get("extractor_key") or "web").lower())
    kind = args.get("kind") or "video"
    episode_id = f"video-{ext}-{vid}"
    if not args.get("dryRun"):
        ensure_new_id(episode_id, args.get("force"))
    title = args.get("title") or info.get("title") or episode_id
    log(f"“{title}” — {info.get('uploader', '?')} — {info.get('duration', '?')} s")
    data_dir().mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=data_dir()) as tmp:
        result = subprocess.run(
            [yd, "--no-playlist", "-f", "bestaudio/best", "-x", "--audio-format", "mp3",
             "--postprocessor-args", "ffmpeg:-ac 1 -b:a 64k", "-o", f"{tmp}/a.%(ext)s", url],
            capture_output=True, text=True, timeout=3600,
        )
        mp3 = Path(tmp) / "a.mp3"
        if result.returncode != 0 or not mp3.exists():
            raise JobError("Audio extraction failed: " + result.stderr.strip()[-400:])
        stamp = info.get("timestamp")
        created = datetime.fromtimestamp(stamp, timezone.utc) if stamp else datetime.now(zone_of())
        if info.get("upload_date") and not stamp:
            created = datetime.strptime(info["upload_date"], "%Y%m%d").replace(tzinfo=zone_of())
        page = info.get("webpage_url", url)
        episode = {
            "title": title,
            "description": (
                f"{'Bande-son de la vidéo' if L() == 'fr' else 'Soundtrack of'} «{title}» "
                f"({info.get('uploader', '')}, {spoken_date(created, L())}). {rights()}\n\nSource: {public_link(page)}"
            ),
            "pubDate": created.astimezone(zone_of()).isoformat(timespec="seconds"),
            "link": public_link(page),
            "guid": episode_id,
            "kind": kind,
        }
        chapters = [
            {"startTime": round(float(c.get("start_time") or 0), 2), "title": c.get("title") or f"Chapter {i + 1}"}
            for i, c in enumerate(info.get("chapters") or [])
        ]
        return publish_audio(episode_id, mp3, episode, args.get("dryRun"), chapters or None)


def llm_generate(cfg: dict, prompt: str) -> str:
    settings = cfg.get("llm") or {}
    provider = settings.get("provider") or "none"
    if provider == "none":
        raise JobError("No AI provider is configured (Compose → AI). Paste your own script instead.")
    model = settings.get("model") or ("llama3.1" if provider == "ollama" else "")
    if provider == "ollama":
        base = (settings.get("baseUrl") or "http://127.0.0.1:11434").rstrip("/")
        try:
            _status, payload, _headers = http_json(base + "/api/generate", {"model": model, "prompt": prompt, "stream": False}, timeout=1800)
        except Exception as exc:
            raise JobError(f"Ollama is not reachable at {base} ({exc}). Install it and run ollama pull {model}.") from exc
        return payload["response"]
    base = (settings.get("baseUrl") or {"openai": "https://api.openai.com/v1", "mistral": "https://api.mistral.ai/v1"}.get(provider, "")).rstrip("/")
    if not base or not settings.get("apiKey"):
        raise JobError("The AI base URL or API key is missing (Compose → AI).")
    try:
        _status, payload, _headers = http_json(
            base + "/chat/completions",
            {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.4},
            headers={"Authorization": f"Bearer {settings['apiKey']}"},
            timeout=900,
        )
    except urllib.error.HTTPError as exc:
        raise JobError(f"AI provider returned HTTP {exc.code}.") from exc
    return payload["choices"][0]["message"]["content"]


def cmd_learn_generate(args: dict):
    cfg = load_cfg()
    template = args.get("prompt") or PROMPTS[L()]
    prompt = template.format(
        sujet=args.get("sujet", ""),
        numero=args.get("numero", 1),
        angle=args.get("angle", "the basics" if L() == "en" else "les bases"),
        mots=args.get("mots", 1800),
    )
    log("Asking the configured model for a script. Check it before publishing.")
    return {"text": llm_generate(cfg, prompt).strip()}


def cmd_prompt_template(_args: dict):
    return {"template": PROMPTS[L()], "lang": L()}


def cmd_digest_prompt(_args: dict):
    return {"template": DIGEST_PROMPTS[L()], "lang": L()}


def cmd_learn(args: dict):
    cfg = load_cfg()
    text = (args.get("text") or "").strip()
    sources = ""
    match = re.search(r"\n\s*SOURCES?\s*:(.*)$", text, re.S | re.I)
    if match:
        sources = match.group(1).strip()
        text = text[:match.start()].strip()
    text = re.sub(r"[#*_`>]+", "", text)
    if len(text) < 200:
        raise JobError("The script is shorter than 200 characters.")
    title = args.get("title") or ("Short lesson" if L() == "en" else "Mini-cours")
    episode_id = (args.get("id") or slugify(title) or "lesson") + "-learn"
    if not args.get("dryRun"):
        ensure_new_id(episode_id, args.get("force"))
    sections = smart_sections(text, INTRO_CH[L()], PART[L()])
    if len(sections) > 1:
        sections[0] = (sections[0][0], f"{title}.\n\n" + sections[0][1])
    else:
        sections = [(None, f"{title}.\n\n{text}")]
    description = f"{'Mini-cours personnel' if L() == 'fr' else 'Personal lesson'} ({voice_label(cfg)}). {args.get('description', '')}".strip()
    if sources:
        description += f"\n\n{'Sources citées' if L() == 'fr' else 'Sources cited'}: {sources}"
    description += f"\n\n{rights()}"
    episode = {
        "title": title,
        "description": description,
        "pubDate": datetime.now(zone_of()).isoformat(timespec="seconds"),
        "guid": episode_id,
        "link": "",
        "kind": "learn",
    }
    return tts_and_publish(episode_id, sections, episode, cfg, args.get("dryRun"))


def cmd_web(args: dict):
    cfg = load_cfg()
    url = (args.get("url") or "").split("#")[0].strip()
    log(f"Web page: {safe_url(url)}")
    html, final = fetch_html(url, find_source(cfg, args.get("sourceId"), url))
    article = extract_document(final, html, {"extractor": "auto"})
    if article.words < MIN_WEB_WORDS:
        if L() == "fr":
            raise JobError(f"Texte trop court ou illisible ({article.words} mots). Paywall, page dynamique, ou vidéo ? Rien n'a été inventé.")
        raise JobError(f"Too little readable text ({article.words} words). Paywall, scripted page, or a video? Nothing was invented.")
    title = article.title or host_of(final)
    digest = hashlib.sha1(public_link(final).encode()).hexdigest()[:6]
    episode_id = f"web-{slugify(article.site or host_of(final))[:30]}-{slugify(title)[:50] or 'page'}-{digest}"
    if not args.get("dryRun"):
        ensure_new_id(episode_id, args.get("force"))
    when_dt = _parse_date(article.published)
    if L() == "fr":
        intro = f"{title}. Page publiée sur {article.site or host_of(final)}" + (f", par {article.author}" if article.author else "") + ". Lecture intégrale."
    else:
        intro = f"{title}. Page from {article.site or host_of(final)}" + (f", by {article.author}" if article.author else "") + ". Full reading."
    sections = sections_from_blocks(article.blocks, intro)
    link = public_link(final)
    episode = {
        "title": title,
        "description": f"{'Lecture' if L() == 'fr' else 'Reading'} ({voice_label(cfg)}) · {article.site or host_of(final)}. {rights()}\n\nSource: {link}",
        "pubDate": datetime.now(zone_of()).isoformat(timespec="seconds"),
        "link": link,
        "guid": episode_id,
        "kind": "web",
    }
    return tts_and_publish(episode_id, sections, episode, cfg, args.get("dryRun"))


def cmd_feed(_args: dict):
    cfg = load_cfg()
    return {
        "episodes": feed_get(),
        "baseUrl": public_base(cfg),
        "storage": "r2" if use_r2(cfg) else "local",
        "demo": demo(),
    }


def cmd_edit(args: dict):
    episode_id = args["id"]
    changes = {k: v for k, v in (args.get("changes") or {}).items() if k in ("title", "description", "kind", "pubDate")}
    if "kind" in changes and changes["kind"] not in FEED_PATHS and changes["kind"] != "thread":
        raise JobError("Unknown feed.")
    found = {}

    def mutate(feed):
        for episode in feed:
            if episode.get("id") == episode_id:
                episode.update(changes)
                found["episode"] = episode
        if not found:
            raise JobError(f"Episode {episode_id} was not found.")
        return feed

    feed_modify(mutate, f"(edit {episode_id})")
    return {"ok": True, "episode": found["episode"]}


def cmd_delete(args: dict):
    episode_id = args["id"]
    gone = {}

    def mutate(feed):
        kept = [episode for episode in feed if episode.get("id") != episode_id]
        if len(kept) == len(feed):
            raise JobError(f"Episode {episode_id} was not found.")
        gone["episode"] = next(episode for episode in feed if episode.get("id") == episode_id)
        return kept

    feed_modify(mutate, f"(delete {episode_id})")
    episode = gone["episode"]
    if args.get("deleteAudio") and episode.get("audioKey") and not episode.get("audioUrl"):
        from storage import delete_bytes
        delete_bytes(episode["audioKey"])
        log(f"Audio removed: {episode['audioKey']}")
        chapters = f"chapters/{episode_id}.json"
        try:
            delete_bytes(chapters)
        except JobError:
            pass
    return {"ok": True}


def cmd_restore(args: dict):
    name = args["name"]
    if not re.fullmatch(r"feed\.backup-[\d-]+\.json", name):
        raise JobError("Invalid backup name.")
    path = data_dir() / "backups" / name
    data = json.loads(path.read_text(encoding="utf-8"))
    feed_modify(lambda _feed: data, f"(restore {name})")
    return {"ok": True, "count": len(data)}


def cmd_auto_import(args: dict):
    cfg = load_cfg()
    count = int(args.get("count") or (cfg.get("scheduler") or {}).get("count") or 2)
    episodes = feed_get()
    skipped = skipped_set()
    todo = []
    for source in cfg.get("sources") or []:
        if not isinstance(source, dict) or not source.get("feedUrl"):
            continue
        try:
            items = fetch_feed_items(source)
        except JobError as exc:
            log(str(exc))
            continue
        for item in items:
            url = item.get("url") or ""
            if not url or is_published(url, episodes) or url in skipped:
                continue
            todo.append((item, source))
            if len(todo) >= count:
                break
        if len(todo) >= count:
            break
    log(f"Automatic import: {len(todo)} item(s)")
    results = []
    for item, source in todo:
        try:
            results.append(cmd_article({"url": item["url"], "sourceId": source.get("id"), "title": item.get("title")}))
        except JobError as exc:
            log(f"FAILED {safe_url(item['url'])}: {exc}")
            results.append({"url": safe_url(item["url"]), "error": str(exc)})
    return {"items": results}


def cmd_preview(args: dict):
    cfg = load_cfg()
    data_dir().mkdir(parents=True, exist_ok=True)
    out = data_dir() / "preview.mp3"
    text = args.get("text") or PREVIEW[L()]
    synthesize(text, out, cfg, args.get("tts"))
    return {"file": str(out)}


def cmd_voices(_args: dict):
    try:
        result = subprocess.run(edge_cmd() + ["--list-voices"], capture_output=True, text=True, timeout=90)
    except JobError as exc:
        return {"voices": [], "error": str(exc)}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"voices": [], "error": str(exc)}
    voices = []
    for line in result.stdout.splitlines():
        part = line.split()
        if part and re.match(r"^[a-z]{2}-[A-Z]{2}-", part[0]):
            voices.append(part[0])
    return {"voices": voices, "error": None if voices or result.returncode == 0 else (result.stderr or "")[-200:]}


def cmd_health(args: dict):
    if demo() and not args.get("live"):
        return {
            "edge_tts": {"ok": True, "detail": "Demo shelf — voice is not contacted."},
            "ffmpeg": {"ok": True, "detail": "Demo shelf."},
            "yt_dlp": {"ok": True, "detail": "Demo shelf."},
            "storage": {"ok": True, "detail": "Sample library, not your episodes."},
            "fxtwitter": {"ok": True, "detail": "Unofficial. Not contacted in the demo."},
            "disk": {"ok": True, "detail": "Demo shelf."},
            "piper": {"ok": False, "detail": "Optional offline voice. Not required."},
        }
    cfg = load_cfg()
    report = {}

    def check(name, fn):
        try:
            report[name] = {"ok": True, "detail": fn()}
        except Exception as exc:
            report[name] = {"ok": False, "detail": str(exc)[:300]}

    def edge():
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                edge_cmd() + ["--voice", tts_tuple(cfg)[1], "--text", "Test.", "--write-media", f"{tmp}/t.mp3"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                raise JobError((result.stderr or "edge-tts failed")[-200:])
        return "Microsoft online synthesis responded. This service is unofficial and can break."

    check("edge_tts", edge)
    check("ffmpeg", lambda: subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout.split("\n")[0][:80])

    def ytdl():
        binary = tool("yt-dlp") or "yt-dlp"
        result = subprocess.run([binary, "--version"], capture_output=True, text=True)
        if result.returncode != 0:
            raise JobError("yt-dlp is not installed")
        return "yt-dlp " + result.stdout.strip()

    check("yt_dlp", ytdl)

    def storage():
        if use_r2(cfg):
            count = len(feed_get())
            return f"R2 library readable ({count} episodes)"
        count = len(feed_get())
        return f"Local library ({count} episodes)"

    check("storage", storage)

    def fx():
        try:
            http_get("https://api.fxtwitter.com/", timeout=15)
        except urllib.error.HTTPError as exc:
            if exc.code >= 500:
                raise JobError(f"HTTP {exc.code}")
        except urllib.error.URLError as exc:
            raise JobError(str(exc.reason))
        return "Reachable. Unofficial API; it can change or disappear."

    check("fxtwitter", fx)

    def disk():
        usage = shutil.disk_usage(str(ROOT))
        free = usage.free / 1e9
        if free < 2:
            raise JobError(f"Only {free:.1f} GB free")
        return f"{free:.0f} GB free"

    check("disk", disk)
    llm = cfg.get("llm") or {}
    if (llm.get("provider") or "none") == "ollama":
        def ollama():
            base = (llm.get("baseUrl") or "http://127.0.0.1:11434").rstrip("/")
            _status, payload, _headers = http_json(base + "/api/tags", timeout=5)
            names = ", ".join(model["name"] for model in payload.get("models", []))
            return names or "no models pulled yet"
        check("ollama", ollama)
    report["piper"] = {"ok": bool(tool("piper")), "detail": "Installed" if tool("piper") else "Optional offline voice, not installed"}
    return report


def cmd_deploy(_args: dict):
    cfg = load_cfg()
    account, token, _bucket = _deploy_creds(cfg)
    env = dict(os.environ)
    env["CLOUDFLARE_API_TOKEN"] = token
    env["CLOUDFLARE_ACCOUNT_ID"] = account
    local = ROOT / "cloudflare" / "node_modules" / ".bin" / "wrangler"
    command = [str(local), "deploy"] if local.exists() else ["npx", "--yes", "wrangler@4", "deploy"]
    result = subprocess.run(command, cwd=str(ROOT / "cloudflare"), env=env, capture_output=True, text=True, timeout=900)
    log(result.stdout[-3000:])
    log(result.stderr[-2000:])
    if result.returncode != 0:
        raise JobError("wrangler deploy failed. See the log. You can also run ./setup.sh from a terminal.")
    return {"ok": True}


def _deploy_creds(cfg: dict):
    from config import cloudflare_creds
    return cloudflare_creds(cfg)


VIDEO_HOSTS = re.compile(
    r"(^|\.)(youtube\.com|youtu\.be|vimeo\.com|dailymotion\.com|dai\.ly|twitch\.tv|tiktok\.com|"
    r"rumble\.com|odysee\.com|peertube|arte\.tv|france\.tv|ted\.com)$",
    re.I,
)


def classify_url(url: str):
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return None, None, "invalid"
    host = (parsed.hostname or "").lower()
    if re.search(r"(^|\.)(x|twitter|fxtwitter|vxtwitter|fixupx|mobile\.twitter)\.com$", host):
        if re.search(r"/status(?:es)?/\d+", parsed.path):
            return "x", {"urls": [url]}, "x-post"
        return None, None, "x-profile"
    if VIDEO_HOSTS.search(host):
        return "video", {"url": url, "kind": "video"}, "video"
    return "web", {"url": url}, "web"


def inbox_call(path: str, data=None):
    cfg = load_cfg()
    token = (cfg.get("inbox") or {}).get("token")
    if not token:
        raise JobError("No inbox token yet. Run ./setup.sh, then paste the same token in Compose if it asks.")
    headers = {"X-Inbox-Token": token, "Accept": "application/json"}
    url = public_base(cfg) + path
    try:
        if data is None:
            _status, body, resp_headers, _final = http_get(url, headers=headers, timeout=30, accept="application/json")
            return json.loads(decode_body(body, resp_headers))
        _status, payload, _headers = http_json(url, data, headers=headers, timeout=30)
        return payload
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise JobError("The inbox refused the token.") from exc
        raise JobError(f"Inbox returned HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise JobError(f"Inbox unreachable: {exc.reason}") from exc


def cmd_inbox_list(_args: dict):
    payload = inbox_call("/inbox/list")
    items = []
    for item in payload.get("items") or []:
        kind, job_args, label = classify_url(item.get("url", ""))
        items.append({**item, "type": kind, "args": job_args, "label": label})
    return {"items": items}


def cmd_inbox_ack(args: dict):
    return inbox_call("/inbox/ack", {"items": args.get("items") or []})


def x_timeline_window(handle: str, since_ts: float, max_pages: int = 12):
    out, cursor = [], None
    for _ in range(max_pages):
        url = f"https://api.fxtwitter.com/2/profile/{urllib.parse.quote(handle)}/statuses?count=20"
        if cursor:
            url += "&cursor=" + urllib.parse.quote(cursor)
        payload = get_json(url)
        results = payload.get("results") or []
        if not results:
            break
        older = False
        for tweet in results:
            stamp = tweet.get("created_timestamp") or 0
            if stamp < since_ts:
                older = True
                continue
            author = (tweet.get("author") or {}).get("screen_name", "")
            if tweet.get("reposted_by") or author.lower() != handle.lower():
                continue
            out.append(tweet)
        cursor = (payload.get("cursor") or {}).get("bottom")
        if older or not cursor:
            break
    seen, uniq = set(), []
    for tweet in sorted(out, key=lambda item: item.get("created_timestamp") or 0):
        if tweet.get("id") not in seen:
            seen.add(tweet.get("id"))
            uniq.append(tweet)
    return uniq


def is_reply_to_other(tweet: dict, handle: str) -> bool:
    reply = tweet.get("replying_to")
    if not reply:
        return False
    screen = reply.get("screen_name") if isinstance(reply, dict) else str(reply)
    return (screen or "").lower() != handle.lower()


def cmd_x_follow(args: dict):
    cfg = load_cfg()
    handle = str(args.get("handle") or "").lstrip("@").strip()
    minimum = int(args.get("minChars") or 280)
    threads = args.get("includeThreads", True)
    since = float(args.get("since") or (time.time() - 86400))
    limit = int(args.get("max") or 5)
    posts = x_timeline_window(handle, since, max_pages=3)
    have = {ep.get("id") for ep in feed_get()}
    todo, skipped = [], 0
    for tweet in posts:
        text = tweet_text(tweet)
        if is_reply_to_other(tweet, handle) or (tweet.get("replying_to") and not threads):
            skipped += 1
            continue
        if tweet.get("replying_to"):
            skipped += 1
            continue
        if len(text) < minimum:
            skipped += 1
            continue
        if f"x-{handle.lower()}-{tweet['id']}" in have:
            continue
        todo.append(tweet)
    log(f"@{handle}: {len(posts)} post(s) in the window, {len(todo)} new long post(s), {skipped} skipped")
    if len(todo) > limit:
        todo = todo[:limit]
    if not args.get("autoPublish", True):
        return {"handle": handle, "new": [f"https://x.com/{handle}/status/{t['id']}" for t in todo], "items": []}
    results = []
    for tweet in todo:
        url = f"https://x.com/{handle}/status/{tweet['id']}"
        try:
            results.append(x_one(url, cfg, {"single": not threads, "dryRun": args.get("dryRun")}))
        except JobError as exc:
            log(f"FAILED {url}: {exc}")
            results.append({"url": url, "error": str(exc)})
    return {"handle": handle, "items": results, "checked": len(posts)}


def first_sentence(text: str, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    match = re.match(r"(.{20,}?[.!?…])(\s|$)", text)
    sentence = match.group(1) if match else text
    return sentence if len(sentence) <= limit else sentence[:limit].rsplit(" ", 1)[0] + "…"


def short_date(stamp: float) -> str:
    moment = datetime.fromtimestamp(stamp, zone_of())
    months = MONTHS_ABBR[L()]
    return f"{months[moment.month]} {moment.day}" if L() == "en" else f"{moment.day} {months[moment.month]}"


def day_label(stamp: float) -> str:
    moment = datetime.fromtimestamp(stamp, zone_of())
    weekday = WEEKDAYS[L()][moment.weekday()]
    if L() == "fr":
        return f"{weekday} {moment.day} {MONTHS['fr'][moment.month]}"
    return f"{weekday} {MONTHS['en'][moment.month]} {moment.day}"


def cmd_x_digest(args: dict):
    cfg = load_cfg()
    handle = str(args.get("handle") or "").lstrip("@").strip()
    period = args.get("period") or "weekly"
    days = 1 if period == "daily" else 7
    end = datetime.now(zone_of())
    start = end - timedelta(days=days)
    episode_id = f"x-digest-{handle.lower()}-{end:%Y-%m-%d}"
    if not args.get("dryRun"):
        ensure_new_id(episode_id, args.get("force"))
    posts = [tweet for tweet in x_timeline_window(handle, start.timestamp()) if not is_reply_to_other(tweet, handle)]
    posts = [tweet for tweet in posts if tweet_text(tweet)]
    if not posts:
        raise JobError(f"No posts from @{handle} in this period, so there is nothing to summarize.")
    name = re.sub(r"[^\w\s\-'’.]", "", ((posts[-1].get("author") or {}).get("name") or handle)).strip() or handle
    settings = cfg.get("llm") or {}
    use_ai = (settings.get("provider") or "none") != "none" and args.get("mode") != "noai"
    label = ("de la semaine" if days == 7 else "du jour") if L() == "fr" else ("of the week" if days == 7 else "of the day")
    title = (f"Résumé {label} — @{handle}" if L() == "fr" else f"Digest {label} — @{handle}")
    start_s, end_s = spoken_date(start, L()), spoken_date(end, L())
    if L() == "fr":
        intro = f"Résumé {label} du compte {name}, @{handle} sur X, du {start_s} au {end_s}. {len(posts)} post{'s' if len(posts) > 1 else ''} sur la période."
    else:
        intro = f"Digest {label} of {name}, @{handle} on X, from {start_s} to {end_s}. {len(posts)} post{'s' if len(posts) > 1 else ''} in the period."
    sections = []
    if use_ai:
        listing = "\n\n".join(f"[{day_label(tweet['created_timestamp'])}] {tweet_text(tweet)}" for tweet in posts)
        prompt = DIGEST_PROMPTS[L()].format(
            periode="hebdomadaire" if L() == "fr" and days == 7 else "quotidien" if L() == "fr" else "weekly" if days == 7 else "daily",
            handle=handle, nom=name, debut=start_s, fin=end_s, posts=listing[:60000],
        )
        text = re.sub(r"[*_`>]+", "", llm_generate(cfg, prompt).strip())
        current_title, current = INTRO_CH[L()], [intro]
        for line in text.splitlines():
            match = re.match(r"^\s*#{1,3}\s*(.+?)\s*$", line)
            if match:
                if current:
                    sections.append((current_title, "\n".join(current)))
                current_title, current = match.group(1), [match.group(1) + "."]
            elif line.strip():
                current.append(line.strip())
        if current:
            sections.append((current_title, "\n".join(current)))
        mode = f"AI digest ({settings.get('provider')})"
    else:
        summary = " ".join(f"{day_label(tweet['created_timestamp'])}: {first_sentence(tweet_text(tweet), 160)}" for tweet in posts)
        if L() == "fr":
            sections.append((INTRO_CH[L()], intro + " Ce résumé est produit sans intelligence artificielle."))
            sections.append(("Sommaire", "Voici les posts de la période. " + summary))
        else:
            sections.append((INTRO_CH[L()], intro + " This digest was made without an AI model."))
            sections.append(("Summary", "Here are the posts from the period. " + summary))
        if args.get("full", True):
            floor = int(args.get("fullMinChars") or 0)
            for tweet in posts:
                text = tweet_text(tweet)
                if len(text) < floor:
                    continue
                sections.append((f"{short_date(tweet['created_timestamp'])} — {short_title(text)}", f"{day_label(tweet['created_timestamp']).capitalize()}. {text}"))
        mode = "no AI: summary, then a full reading of the longer posts"
    episode = {
        "title": title,
        "description": f"{title}. {len(posts)} posts. {mode}. {rights()}\n\nSource: https://x.com/{handle}",
        "pubDate": end.isoformat(timespec="seconds"),
        "link": f"https://x.com/{handle}",
        "guid": episode_id,
        "kind": "x",
        "digest": {"handle": handle, "period": period, "posts": len(posts), "mode": "ai" if use_ai else "plain"},
    }
    return tts_and_publish(episode_id, sections, episode, cfg, args.get("dryRun"))


def backfill_sections(episode: dict):
    episode_id = episode["id"]
    folder = data_dir() / "transcripts"
    sidecar = folder / f"{episode_id}.sections.json"
    if sidecar.exists():
        sections = [(item["title"], item["text"]) for item in json.loads(sidecar.read_text(encoding="utf-8"))]
        if len(sections) >= 2:
            return sections
    text = None
    for candidate in (folder / f"{episode_id}.txt", data_dir() / "scripts" / f"{episode_id}.txt"):
        if candidate.exists():
            text = candidate.read_text(encoding="utf-8")
            break
    if text is None:
        return None
    kind = episode.get("kind") or "article"
    if kind == "learn":
        title, _, rest = text.partition("\n\n")
        sections = smart_sections(rest.strip(), INTRO_CH[L()], PART[L()])
        if len(sections) > 1:
            sections[0] = (sections[0][0], title.strip() + "\n\n" + sections[0][1])
        return sections
    if kind in ("x", "thread"):
        intro, _, rest = text.partition("\n\n")
        body = auto_sections(rest.strip(), target=1600, label=PART[L()])
        return [(INTRO_CH[L()], intro)] + [(t or "Reading", x) for t, x in body] if len(body) > 1 else None
    return smart_sections(text, INTRO_CH[L()], PART[L()])


def cmd_chapters_backfill(args: dict):
    cfg = load_cfg()
    feed = {episode["id"]: episode for episode in feed_get()}
    ids = args.get("ids") or []
    if not ids:
        folder = data_dir() / "transcripts"
        ids = []
        if folder.exists():
            ids = sorted({path.name.split(".")[0] for path in folder.glob("*.txt")} | {path.name[: -len(".sections.json")] for path in folder.glob("*.sections.json")})
        ids = [episode_id for episode_id in ids if episode_id in feed and not feed[episode_id].get("chapters")]
    results = []
    for episode_id in ids:
        episode = feed.get(episode_id)
        if not episode:
            results.append({"id": episode_id, "error": "not in the library"})
            continue
        if episode.get("audioUrl"):
            results.append({"id": episode_id, "error": "external audio, no chapters to generate"})
            continue
        if episode.get("chapters") and not args.get("force"):
            results.append({"id": episode_id, "skipped": "already has chapters"})
            continue
        sections = backfill_sections(episode)
        if not sections or len(sections) < 2:
            results.append({"id": episode_id, "error": "no saved transcript with sections"})
            continue
        log(f"Chapters for {episode_id}: {len(sections)} sections")
        try:
            kept = {k: v for k, v in episode.items() if k not in ("bytes", "durationSeconds", "audioKey", "chapters")}
            result = tts_and_publish(episode_id, sections, kept, cfg, args.get("dryRun"))
            results.append({"id": episode_id, "chapters": len(sections), "durationSeconds": result.get("durationSeconds")})
        except JobError as exc:
            results.append({"id": episode_id, "error": str(exc)})
    if results and all("error" in item for item in results):
        raise JobError("; ".join(f"{item['id']}: {item['error']}" for item in results))
    return {"items": results}


def cmd_chapters_candidates(_args: dict):
    feed = feed_get()
    folder = data_dir() / "transcripts"
    have = set()
    if folder.exists():
        have = {path.name.split(".")[0] for path in folder.glob("*.txt")} | {path.name[: -len(".sections.json")] for path in folder.glob("*.sections.json")}
    return {
        "items": [
            {"id": episode["id"], "title": episode.get("title"), "kind": episode.get("kind"), "chapters": bool(episode.get("chapters"))}
            for episode in feed if episode["id"] in have and not episode.get("audioUrl")
        ]
    }


COMMANDS = {
    "article": cmd_article,
    "source-items": cmd_source_items,
    "extractors": cmd_extractors,
    "x": cmd_x,
    "x-timeline": cmd_x_timeline,
    "video": cmd_video,
    "learn": cmd_learn,
    "learn-generate": cmd_learn_generate,
    "feed": cmd_feed,
    "edit": cmd_edit,
    "delete": cmd_delete,
    "restore": cmd_restore,
    "health": cmd_health,
    "preview": cmd_preview,
    "voices": cmd_voices,
    "auto-import": cmd_auto_import,
    "deploy": cmd_deploy,
    "prompt-template": cmd_prompt_template,
    "digest-prompt": cmd_digest_prompt,
    "web": cmd_web,
    "inbox-list": cmd_inbox_list,
    "inbox-ack": cmd_inbox_ack,
    "x-follow": cmd_x_follow,
    "x-digest": cmd_x_digest,
    "chapters-backfill": cmd_chapters_backfill,
    "chapters-candidates": cmd_chapters_candidates,
}


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "health"
    raw = sys.argv[2] if len(sys.argv) > 2 else "{}"
    arguments = json.loads(sys.stdin.read() or "{}") if raw == "-" else json.loads(raw)
    try:
        if command not in COMMANDS:
            raise JobError(f"Unknown command: {command}")
        result = COMMANDS[command](arguments)
        print("RESULT " + json.dumps({"ok": True, "result": result}, ensure_ascii=False), flush=True)
    except JobError as exc:
        print("RESULT " + json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), flush=True)
        sys.exit(2)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        print("RESULT " + json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), flush=True)
        sys.exit(1)
