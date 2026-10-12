#!/usr/bin/env bash
# First-run publisher for Masthead.
# Creates your R2 bucket, deploys the Worker, uploads covers, and writes an inbox token
# into studio-config.json (mode 600). The token is not printed.
#
#   ./setup.sh --dry-run
#   ./setup.sh --yes --worker-name masthead --bucket masthead-library
#   ./setup.sh --account-id <32 hex chars> --author "Your name" --title Masthead --lang en
set -euo pipefail
cd "$(dirname "$0")"

DRY=0
YES=0
WORKER_NAME=""
BUCKET=""
ACCOUNT=""
AUTHOR="Masthead"
TITLE="Masthead"
LANG="en"

usage() {
  sed -n '2,12p' "$0"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY=1; shift ;;
    --yes|-y) YES=1; shift ;;
    --worker-name) WORKER_NAME="${2:-}"; shift 2 ;;
    --bucket) BUCKET="${2:-}"; shift 2 ;;
    --account-id) ACCOUNT="${2:-}"; shift 2 ;;
    --author) AUTHOR="${2:-}"; shift 2 ;;
    --title) TITLE="${2:-}"; shift 2 ;;
    --lang) LANG="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
done

valid_name() {
  [[ "$1" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]]
}

if [[ "$LANG" != "en" && "$LANG" != "fr" ]]; then
  echo "Language must be en or fr." >&2
  exit 2
fi

if [[ -z "$WORKER_NAME" ]]; then
  if [[ "$YES" -eq 1 || "$DRY" -eq 1 ]]; then
    WORKER_NAME="masthead"
  else
    read -r -p "Worker name [masthead]: " WORKER_NAME
    WORKER_NAME="${WORKER_NAME:-masthead}"
  fi
fi
WORKER_NAME="$(printf '%s' "$WORKER_NAME" | tr '[:upper:]' '[:lower:]')"
if ! valid_name "$WORKER_NAME"; then
  echo "Worker name must be a DNS label: lowercase letters, numbers, hyphens." >&2
  exit 2
fi

if [[ -z "$BUCKET" ]]; then
  if [[ "$YES" -eq 1 || "$DRY" -eq 1 ]]; then
    BUCKET="${WORKER_NAME}-library"
  else
    read -r -p "R2 bucket name [${WORKER_NAME}-library]: " BUCKET
    BUCKET="${BUCKET:-${WORKER_NAME}-library}"
  fi
fi
BUCKET="$(printf '%s' "$BUCKET" | tr '[:upper:]' '[:lower:]')"
if ! valid_name "$BUCKET"; then
  echo "Bucket name must be a DNS label: lowercase letters, numbers, hyphens." >&2
  exit 2
fi

if ! command -v npx >/dev/null 2>&1; then
  echo "Node.js (npx) is required." >&2
  exit 1
fi

if [[ -z "$ACCOUNT" ]]; then
  WHO="$(npx --yes wrangler@4 whoami 2>&1 || true)"
  ACCOUNT="$(printf '%s\n' "$WHO" | grep -Eo '[0-9a-f]{32}' | head -n 1 || true)"
fi

if [[ -n "$ACCOUNT" && ! "$ACCOUNT" =~ ^[0-9a-f]{32}$ ]]; then
  echo "Account id must be 32 hex characters. Pass --account-id or run: npx wrangler login" >&2
  exit 2
fi

if [[ "$DRY" -eq 1 ]]; then
  echo "Dry run. No bucket, no worker, no token."
  echo "Worker: $WORKER_NAME"
  echo "Bucket: $BUCKET"
  if [[ -n "$ACCOUNT" ]]; then
    echo "Account: ${ACCOUNT:0:4}…${ACCOUNT: -4}"
  else
    echo "Account: not resolved. Run 'npx wrangler login' before a real setup."
  fi
  echo "Language: $LANG"
  echo "Inbox token: would be generated and written to studio-config.json. Not created."
  echo "Would write cloudflare/wrangler.jsonc (gitignored) and upload public/covers."
  exit 0
fi

if [[ -z "$ACCOUNT" ]]; then
  echo "Could not read a Cloudflare account id." >&2
  echo "Log in with: npx wrangler login" >&2
  echo "Or pass --account-id." >&2
  exit 1
fi

TOKEN="$(openssl rand -hex 24)"

export MH_WORKER="$WORKER_NAME" MH_BUCKET="$BUCKET" MH_ACCOUNT="$ACCOUNT"
export MH_AUTHOR="$AUTHOR" MH_TITLE="$TITLE" MH_LANG="$LANG"
python3 - <<'PY'
import json, os, pathlib, re
src = pathlib.Path("cloudflare/wrangler.example.jsonc").read_text()
text = re.sub(r"^\s*//.*$", "", src, flags=re.M)
cfg = json.loads(text)
cfg["name"] = os.environ["MH_WORKER"]
cfg["account_id"] = os.environ["MH_ACCOUNT"]
cfg["r2_buckets"] = [{"binding": "BUCKET", "bucket_name": os.environ["MH_BUCKET"]}]
cfg.setdefault("vars", {})
cfg["vars"]["PODCAST_TITLE"] = os.environ["MH_TITLE"]
cfg["vars"]["PODCAST_AUTHOR"] = os.environ["MH_AUTHOR"]
cfg["vars"]["PODCAST_LANGUAGE"] = os.environ["MH_LANG"]
path = pathlib.Path("cloudflare/wrangler.jsonc")
path.write_text(json.dumps(cfg, indent=2) + "\n")
os.chmod(path, 0o600)
print("Wrote cloudflare/wrangler.jsonc")
PY

echo "Creating the R2 bucket if it does not exist…"
(cd cloudflare && npx --yes wrangler@4 r2 bucket create "$BUCKET") || echo "Bucket create returned an error. Continuing in case it already exists."

upload() {
  local key="$1" file="$2" type="$3"
  (cd cloudflare && npx --yes wrangler@4 r2 object put "${BUCKET}/${key}" --file="$file" --content-type="$type")
}

echo "Uploading covers…"
upload "covers/articles.png" "../public/covers/articles.png" "image/png"
upload "covers/x.png" "../public/covers/x.png" "image/png"
upload "covers/videos.png" "../public/covers/videos.png" "image/png"
upload "covers/learn.png" "../public/covers/learn.png" "image/png"
upload "covers/readings.png" "../public/covers/readings.png" "image/png"
upload "covers/icon-192.png" "../public/pwa/icon-192.png" "image/png"
upload "covers/icon-512.png" "../public/pwa/icon-512.png" "image/png"

echo "Deploying the worker…"
DEPLOY="$(cd cloudflare && npx --yes wrangler@4 deploy 2>&1)" || { printf '%s\n' "$DEPLOY" >&2; exit 1; }
printf '%s\n' "$DEPLOY"
URL="$(printf '%s\n' "$DEPLOY" | grep -Eo 'https://[a-z0-9.-]+\.workers\.dev' | head -n 1 || true)"

echo "Storing the inbox token as a Worker secret…"
printf '%s' "$TOKEN" | (cd cloudflare && npx --yes wrangler@4 secret put INBOX_TOKEN)

export MH_URL="${URL:-}" MH_TOKEN="$TOKEN"
python3 - <<'PY'
import json, os, pathlib
path = pathlib.Path("studio-config.json")
cfg = {}
if path.exists():
    cfg = json.loads(path.read_text())
cfg.setdefault("cloudflare", {})
cfg["cloudflare"]["accountId"] = os.environ["MH_ACCOUNT"]
cfg["cloudflare"]["bucket"] = os.environ["MH_BUCKET"]
cfg.setdefault("inbox", {})
cfg["inbox"]["token"] = os.environ["MH_TOKEN"]
cfg.setdefault("publish", {})
cfg["publish"]["author"] = os.environ["MH_AUTHOR"]
cfg["publish"]["title"] = os.environ["MH_TITLE"]
if os.environ.get("MH_URL"):
    cfg["publish"]["publicBaseUrl"] = os.environ["MH_URL"]
cfg.setdefault("ui", {})
cfg["ui"]["lang"] = os.environ["MH_LANG"]
path.write_text(json.dumps(cfg, indent=2) + "\n")
os.chmod(path, 0o600)
print("Wrote studio-config.json (mode 600).")
if os.environ.get("MH_URL"):
    print("Feeds:", os.environ["MH_URL"])
print("Inbox token saved in studio-config.json. Open Compose on this computer to view it. It was not printed.")
print("The Python library talks to R2 with an API token. Wrangler login is enough to deploy. Paste a token with R2 access in Compose when you want publishes to leave this machine.")
PY
unset TOKEN MH_TOKEN
