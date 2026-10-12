#!/usr/bin/env bash
# Install the local tools Masthead needs: a virtualenv, edge-tts, yt-dlp.
# ffmpeg must already be on the PATH.
#
#   ./installer.sh
#   ./installer.sh --piper en
#   ./installer.sh --piper fr
set -euo pipefail
cd "$(dirname "$0")"

PIPER=""
if [[ "${1:-}" == "--piper" ]]; then
  PIPER="${2:-en}"
fi
if [[ -n "$PIPER" && "$PIPER" != "en" && "$PIPER" != "fr" ]]; then
  echo "Piper language must be en or fr." >&2
  exit 2
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required." >&2
  exit 1
fi
if ! command -v node >/dev/null 2>&1; then
  echo "Node.js 18 or newer is required for the dashboard." >&2
  exit 1
fi
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg is required to join speech into an episode." >&2
  echo "Debian/Ubuntu: sudo apt install ffmpeg" >&2
  echo "Fedora: sudo dnf install ffmpeg" >&2
  echo "macOS (Homebrew): brew install ffmpeg" >&2
  exit 1
fi

python3 -m venv .venv
./.venv/bin/python -m pip install -U pip
./.venv/bin/python -m pip install -r requirements.txt

if [[ -n "$PIPER" ]]; then
  if ! command -v curl >/dev/null 2>&1; then
    echo "curl is required to download a Piper voice." >&2
    exit 1
  fi
  mkdir -p voices
  if [[ "$PIPER" == "fr" ]]; then
    BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/siwis/medium/fr_FR-siwis-medium"
    STEM="fr_FR-siwis-medium"
  else
    BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium"
    STEM="en_US-lessac-medium"
  fi
  echo "Downloading the Piper voice ${STEM}…"
  curl -L --fail -o "voices/${STEM}.onnx" "${BASE}.onnx"
  curl -L --fail -o "voices/${STEM}.onnx.json" "${BASE}.onnx.json"
  echo "Piper model: $(pwd)/voices/${STEM}.onnx"
  echo "Point Compose → Piper model path at that file, and install the piper binary for your system."
fi

echo
echo "Ready."
echo "  npm start          local desk at http://127.0.0.1:8741"
echo "  npm run demo       sample shelf, no network calls to voice or the wire"
echo "  ./setup.sh         optional Cloudflare Worker + R2 for your own feeds"
