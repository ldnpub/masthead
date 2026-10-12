"""Text to speech, chapter marks, and publishing one episode."""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import wave
from datetime import datetime
from pathlib import Path

from config import ENGINE, JobError, data_dir, lang_of, load_cfg, log, tts_tuple, zone_of, MONTHS
from storage import episode_feed_url, merge_episode, put_bytes


def tool(name: str) -> str | None:
    found = shutil.which(name)
    venv = ENGINE.parent / ".venv" / "bin" / name
    if not found and venv.exists():
        return str(venv)
    return found


def edge_cmd() -> list[str]:
    et = tool("edge-tts")
    if not et:
        raise JobError("edge-tts is not installed. Run ./installer.sh, or switch the engine to Piper.")
    py = Path(et).resolve().parent / "python3"
    launcher = ENGINE / "edge_tts_launcher.py"
    if py.exists() and launcher.exists():
        return [str(py), str(launcher)]
    return [et]


def probe(path: Path) -> tuple[int, int]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        dur = float(result.stdout.strip())
    except ValueError:
        dur = 0.0
    return int(round(dur)), path.stat().st_size


def split_chunks(text: str, max_c: int = 3000) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    pieces: list[str] = []
    for para in paras:
        if len(para) <= max_c:
            pieces.append(para)
            continue
        buf = ""
        for sentence in re.split(r"(?<=[.!?…»])\s+", para):
            if buf and len(buf) + len(sentence) + 1 > max_c:
                pieces.append(buf)
                buf = sentence
            else:
                buf = (buf + " " + sentence).strip()
        if buf:
            pieces.append(buf)
    chunks: list[str] = []
    buf = ""
    for piece in pieces:
        if buf and len(buf) + len(piece) + 2 > max_c:
            chunks.append(buf)
            buf = piece
        else:
            buf = (buf + "\n\n" + piece).strip()
    if buf:
        chunks.append(buf)
    return chunks or [text]


def tts_chunk(text: str, out_mp3: Path, engine: str, voice: str, rate: int, piper_model: str):
    note = out_mp3.with_suffix(".txt")
    note.write_text(text, encoding="utf-8")
    last = ""
    result = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="")
    for attempt in range(1, 4):
        out_mp3.unlink(missing_ok=True)
        if engine == "piper":
            pp = tool("piper")
            if not pp or not piper_model or not Path(piper_model).exists():
                raise JobError("Piper is not installed, or the voice model path is missing (Compose → Voice).")
            wav = out_mp3.with_suffix(".wav")
            result = subprocess.run(
                [pp, "--model", piper_model, "--output_file", str(wav)],
                input=text, capture_output=True, text=True, timeout=900,
            )
            if result.returncode == 0 and wav.exists():
                subprocess.run(
                    ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-ac", "1", "-ar", "24000", "-b:a", "48k", str(out_mp3)],
                    check=False,
                )
                wav.unlink(missing_ok=True)
        else:
            result = subprocess.run(
                edge_cmd() + ["--voice", voice, f"--rate={rate:+d}%", "--file", str(note), "--write-media", str(out_mp3)],
                capture_output=True, text=True, timeout=600,
            )
        if out_mp3.exists() and out_mp3.stat().st_size > 1000:
            note.unlink(missing_ok=True)
            return
        last = (result.stderr or "")[-400:]
        log(f"  TTS attempt {attempt} failed: {last.strip()[:200]}")
        import time
        time.sleep(2 ** attempt)
    raise JobError(f"Speech synthesis failed after 3 attempts ({engine}): {last.strip()[:300]}")


def wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / float(handle.getframerate())


def synthesize_sections(sections, out_mp3: Path, cfg: dict, override=None):
    engine, voice, rate, piper_model = tts_tuple(cfg, override)
    sections = [(title, text.strip()) for title, text in sections if text and text.strip()]
    total = sum(len(text) for _, text in sections)
    log(f"Voice: {engine}, {voice}, rate {rate:+d}%, {total} characters, {len(sections)} section(s)")
    work = Path(tempfile.mkdtemp(prefix="tts-", dir=data_dir()))
    chapters = []
    cursor = 0.0
    try:
        wavs = []
        n = 0
        for index, (title, text) in enumerate(sections):
            chunks = split_chunks(text)
            if title:
                chapters.append({"startTime": round(cursor, 2), "title": title})
            for chunk in chunks:
                n += 1
                log(f"  section {index + 1}/{len(sections)} · chunk {n} ({len(chunk)} chars)")
                mp3 = work / f"part{n:04d}.mp3"
                tts_chunk(chunk, mp3, engine, voice, rate, piper_model)
                wav_path = work / f"part{n:04d}.wav"
                result = subprocess.run(
                    ["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le", str(wav_path)],
                    capture_output=True, text=True,
                )
                if result.returncode != 0:
                    raise JobError("ffmpeg (decode): " + result.stderr[-300:])
                cursor += wav_seconds(wav_path)
                wavs.append(wav_path)
        listing = work / "list.txt"
        listing.write_text("".join(f"file '{path}'\n" for path in wavs))
        result = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
             "-c:a", "libmp3lame", "-b:a", "48k", "-ar", "24000", "-ac", "1", str(out_mp3)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise JobError("ffmpeg (join): " + result.stderr[-300:])
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if len(chapters) < 2:
        chapters = []
    return chapters


def synthesize(text: str, out_mp3: Path, cfg: dict, override=None):
    synthesize_sections([(None, text)], out_mp3, cfg, override)


def embed_chapters(mp3: Path, chapters, title: str = "") -> bool:
    if not chapters or len(chapters) < 2:
        return False
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(mp3)],
        capture_output=True, text=True,
    )
    total_ms = int(float(result.stdout.strip() or 0) * 1000)

    def esc(value):
        return re.sub(r"([=;#\\\n])", r"\\\1", str(value))

    meta = [";FFMETADATA1"]
    if title:
        meta.append("title=" + esc(title))
    for index, chapter in enumerate(chapters):
        start = int(chapter["startTime"] * 1000)
        end = int(chapters[index + 1]["startTime"] * 1000) if index + 1 < len(chapters) else total_ms
        meta += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={start}", f"END={max(end, start + 1)}", "title=" + esc(chapter["title"])]
    sidecar = mp3.with_suffix(".ffmeta")
    sidecar.write_text("\n".join(meta) + "\n", encoding="utf-8")
    tagged = mp3.with_name(mp3.stem + ".chap.mp3")
    result = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), "-i", str(sidecar), "-map", "0:a",
         "-map_metadata", "1", "-map_chapters", "1", "-c", "copy", "-id3v2_version", "3", "-write_id3v1", "0", str(tagged)],
        capture_output=True, text=True,
    )
    sidecar.unlink(missing_ok=True)
    if result.returncode != 0 or not tagged.exists():
        log("  (ID3 chapters were not written: " + result.stderr[-200:] + ")")
        return False
    tagged.replace(mp3)
    return True


def chapters_document(chapters, title: str = "") -> dict:
    return {
        "version": "1.2.0",
        "title": title,
        "chapters": [{"startTime": c["startTime"], "title": c["title"]} for c in chapters],
    }


def heading_sections(text: str, intro_title: str = "Introduction", max_len: int = 90):
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    sections = []
    current_title, current = intro_title, []
    for index, para in enumerate(paras):
        nxt = paras[index + 1] if index + 1 < len(paras) else ""
        is_head = (
            index > 0 and len(para) <= max_len and len(nxt) > len(para) * 1.5 and "\n" not in para
            and len(re.findall(r"[.!?…]\s", para + " ")) <= 1
        )
        if para.startswith("#H# "):
            is_head, para = True, para[4:].strip()
        if is_head and current:
            sections.append((current_title, "\n\n".join(current)))
            current_title, current = re.sub(r"[.:…\s]+$", "", para), [para]
        elif is_head:
            current_title, current = re.sub(r"[.:…\s]+$", "", para), [para]
        else:
            current.append(para)
    if current:
        sections.append((current_title, "\n\n".join(current)))
    return sections


def auto_sections(text: str, target: int = 1800, label: str = "Part"):
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    groups, current = [], []
    for para in paras:
        current.append(para)
        if sum(len(x) for x in current) >= target:
            groups.append(current)
            current = []
    if current:
        if groups and sum(len(x) for x in current) < target / 3:
            groups[-1] += current
        else:
            groups.append(current)
    out = []
    for index, group in enumerate(groups):
        words = re.sub(r"\s+", " ", group[0]).split(" ")
        head = " ".join(words[:7]).rstrip(",;:.") + ("…" if len(words) > 7 else "")
        title = f"{label} {index + 1} — {head}" if len(groups) > 1 else None
        out.append((title, "\n\n".join(group)))
    return out


def smart_sections(text: str, intro_title: str = "Introduction", part_label: str = "Part"):
    sections = heading_sections(text, intro_title)
    if len(sections) >= 2:
        return sections
    if len(text) > 4000:
        return auto_sections(text, label=part_label)
    return [(None, text)]


def spoken_date(dt: datetime, language: str) -> str:
    dt = dt.astimezone(zone_of())
    months = MONTHS.get(language, MONTHS["en"])
    if language == "fr":
        return f"{dt.day} {months[dt.month]} {dt.year}"
    return f"{months[dt.month]} {dt.day}, {dt.year}"


def voice_label(cfg: dict) -> str:
    engine, voice, _rate, _model = tts_tuple(cfg)
    if engine == "piper":
        return "Piper"
    match = re.match(r"[a-z]{2}-[A-Z]{2}-([A-Za-z]+?)(?:Multilingual)?Neural", voice)
    return match.group(1) if match else voice


def save_text(episode_id: str, sections):
    try:
        folder = data_dir() / "transcripts"
        folder.mkdir(parents=True, exist_ok=True)
        payload = [{"title": title, "text": text} for title, text in sections]
        (folder / f"{episode_id}.sections.json").write_text(
            __import__("json").dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass


def publish_audio(episode_id: str, mp3: Path, episode: dict, dry: bool = False, chapters=None) -> dict:
    cfg = load_cfg()
    if chapters and len(chapters) >= 2:
        if embed_chapters(mp3, chapters, episode.get("title", "")):
            log(f"{len(chapters)} ID3 chapters written into the MP3")
        episode["chapters"] = True
    duration, size = probe(mp3)
    episode.update({
        "id": episode_id,
        "audioKey": f"episodes/{episode_id}.mp3",
        "bytes": size,
        "durationSeconds": duration,
        "guid": episode.get("guid") or episode_id,
    })
    if dry:
        if chapters:
            episode["chaptersList"] = chapters
        kept = data_dir() / "sorties" / f"{episode_id}.mp3"
        kept.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(mp3, kept)
        log(f"Dry run: nothing was published. Local MP3: {kept}")
        return {"dryRun": True, "mp3": str(kept), "episode": episode}
    log(f"Storing audio episodes/{episode_id}.mp3 ({size / 1e6:.2f} MB, {duration} s)")
    put_bytes(f"episodes/{episode_id}.mp3", mp3.read_bytes(), "audio/mpeg")
    if episode.get("chapters") and chapters:
        import json
        raw = json.dumps(chapters_document(chapters, episode.get("title", "")), ensure_ascii=False, indent=1).encode("utf-8")
        put_bytes(f"chapters/{episode_id}.json", raw, "application/json+chapters; charset=utf-8")
    merge_episode(episode)
    return {
        "published": True,
        "id": episode_id,
        "feed": episode_feed_url(episode, cfg),
        "audio": f"{public_base_audio(episode_id, cfg)}",
        "durationSeconds": duration,
        "bytes": size,
    }


def public_base_audio(episode_id: str, cfg) -> str:
    from config import public_base
    return f"{public_base(cfg)}/audio/{episode_id}.mp3"


def tts_and_publish(episode_id: str, text, episode: dict, cfg: dict, dry: bool = False, override=None) -> dict:
    data_dir().mkdir(parents=True, exist_ok=True)
    sections = text if isinstance(text, list) else [(None, text)]
    save_text(episode_id, sections)
    with tempfile.TemporaryDirectory(dir=data_dir()) as tmp:
        mp3 = Path(tmp) / f"{episode_id}.mp3"
        chapters = synthesize_sections(sections, mp3, cfg, override)
        return publish_audio(episode_id, mp3, episode, dry, chapters)
