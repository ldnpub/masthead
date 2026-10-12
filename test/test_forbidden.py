"""Fail if a personal identifier or a live secret is in the tree we ship."""
import os
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "node_modules", ".venv", "data", "__pycache__", "uploads", "voices"}
BINARY_SUFFIXES = {".png", ".ttf", ".otf", ".woff", ".woff2", ".mp3", ".tgz", ".gz", ".zip", ".pyc"}

# Joined at runtime so this file does not contain the forbidden strings.
NEEDLES = [
    "elu" + "cid",
    "élu" + "cid",
    "Élu" + "cid",
    "rodo" + "lphe",
    "Rodo" + "lphe",
    "bouch" + "ier",
    "anato" + "lium",
    "1925b36d" + "8e9a0ebc70d50c200a5a24ed",
    "ldn" + "pub",
    "BEGIN " + "PRIVATE KEY",
    "AKIA" + "IOSFODNN7",
]


def tracked_names():
    try:
        out = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


class ForbiddenTests(unittest.TestCase):
    def test_git_does_not_track_secrets_or_the_archive(self):
        names = tracked_names()
        banned = {
            "studio-config.json",
            "cloudflare/wrangler.jsonc",
            "uploads/studio-src_ddcf.tgz",
        }
        self.assertFalse(banned & set(names), names)

    def test_tree_has_no_personal_markers(self):
        hits = []
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS]
            for filename in filenames:
                path = pathlib.Path(dirpath) / filename
                if path.suffix.lower() in BINARY_SUFFIXES:
                    continue
                if path.name.endswith(".pyc"):
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                lowered = text.lower()
                for needle in NEEDLES:
                    if needle.lower() in lowered:
                        hits.append(f"{path.relative_to(ROOT)}: {needle}")
                if "@" in text and path.suffix.lower() in {".py", ".js", ".mjs", ".md", ".json", ".html", ".css", ".sh", ".jsonc"}:
                    for token in text.replace("(", " ").replace(")", " ").replace("<", " ").replace(">", " ").split():
                        if "@" in token and "." in token.split("@")[-1] and not token.startswith("@"):
                            # Allow the fictional handle mention style only when it is not an email.
                            if any(ch.isalnum() for ch in token.split("@", 1)[0]):
                                host = token.split("@", 1)[1].strip(".,:;\"'")
                                if "." in host and not host.endswith(".example") and "example-press" not in host:
                                    hits.append(f"{path.relative_to(ROOT)}: email-like {token[:80]}")
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
