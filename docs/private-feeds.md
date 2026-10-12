# Private feeds, for your own use

Masthead can read a source you already have the right to read: a public feed, a tokenized private feed, a feed behind HTTP basic auth, or a page you open with your own session cookie. It stores those secrets on the computer that runs the desk, in `studio-config.json`, which is gitignored and written with mode `600`.

This is for personal listening. You are responsible for the rights to anything you convert. Do not point Masthead at a site you do not subscribe to, do not share the resulting feed, and do not commit cookies, tokens, or private URLs.

Masthead does not ship scrapers for commercial paywalls. The extractor interface is a place for an adapter you write, for a site whose terms allow you to read the article.

## A tokenized private RSS URL

Some publishers hand subscribers a feed address with a secret in the query string.

```text
https://members.example-press.test/feed.xml?token=YOUR_TOKEN
```

Paste that whole address into Sources. The desk keeps the query string in `studio-config.json`. The form shows the address without the query and a note that a token is saved. Episode links in the podcast feed have sensitive query keys removed (`token`, `key`, `apikey`, `api_key`, `auth`, `secret`, `k`, `access_token`, `sig`, `signature`, `password`, `pass`), so a podcast app does not republish the secret.

Leaving the feed field as the stripped address does not wipe the saved query. Paste a new address only when you mean to replace it.

## HTTP basic auth

For a feed that expects a username and password:

1. Open Sources and add the feed URL.
2. Set **How to sign in** to HTTP basic.
3. Enter the username and password.

Masthead sends `Authorization: Basic …` only to that host. If the server redirects to a different host, the header is not forwarded, except to `*.cloudflare.com` when you are talking to your own bucket.

An empty password field on a later save keeps the password already stored. Type `__clear__` in the field to delete it.

## Your own session cookie

Use this when you can open the article in your browser while logged in, and the site does not offer a private feed.

1. In the browser where you are logged in, copy the `Cookie` request header for that site (the developer tools network panel shows it).
2. In Sources, set **How to sign in** to Session cookie and paste the header value, for example `session=YOUR_SESSION`.
3. Set the extractor to `auto`, or to an adapter you wrote for that site.

The cookie is sent only when Masthead fetches that source. It is not written into the episode, the RSS feed, or the log line (URLs in logs have their query strings removed).

Cookies expire. When a source starts failing, paste a fresh cookie. Do not put the cookie in a git commit, a screenshot, or a shared config.

A custom header works the same way: scheme `header`, plus the header name and value. A bearer token uses scheme `bearer`.

## What the desk does with a feed item

For each item, Masthead prefers the full text already in the feed (`content:encoded` or the Atom content) when it is at least 80 words. If the feed only has a teaser, it fetches the item URL with that source’s auth and runs an extractor. If the page still does not yield a real article, the job fails. It does not invent the missing text.

## The extractor interface

An extractor turns HTML into blocks of speech. Built-in extractors live in `engine/extractors/`. Your adapters live in `extractors/` at the repository root. That directory is gitignored except for `extractors/.gitkeep`.

```python
from .base import Article, ExtractError, Extractor


class MyPaper(Extractor):
    id = "my-paper"
    description = "The subscriber pages I am allowed to read."

    def matches(self, url: str) -> bool:
        # Used only when the source extractor is "auto".
        return "my-paper.example" in url

    def extract(self, url: str, html: str) -> Article:
        # blocks: paragraphs. Prefix a heading with "#H# " to make a chapter.
        # Raise ExtractError if this HTML is not the page you understand.
        if "subscriber-body" not in html:
            raise ExtractError("my-paper: subscriber body not found")
        return Article(
            title="Title from the page",
            author="",
            site="My Paper",
            blocks=["#H# The argument", "The paragraph you are allowed to read."],
        )
```

Save that as `extractors/my_paper.py`. Restart the desk. Pick `my-paper` on the source, or leave the extractor on Automatic and let `matches()` decide.

`from .base import` works because Masthead loads your file as part of the `extractors` package. A personal adapter with the same `id` as a built-in replaces that built-in. The fallback id `readable` is generic and runs last.

A full adapter, including an HTML parser, is `engine/extractors/example_member_press.py`. It matches only the fictional host `members.example-press.test` and only reads `<article class="member-body">`. Copy that file to `extractors/` and change the host and the selectors. Do not aim it at a publisher you do not subscribe to.

## Check that an adapter sees the text

```bash
python3 - <<'PY'
import json, urllib.request
from pathlib import Path
import sys
sys.path.insert(0, "engine")
from extractors import choose_extractor
html = Path("extractors/sample.html").read_text()
article = choose_extractor("https://my-paper.example/story", "my-paper").extract("https://my-paper.example/story", html)
print(article.title, article.words)
PY
```

Keep `sample.html` next to the adapter, outside git, if it contains text you do not have the right to republish.

## Where secrets live

| Secret | Where it is stored | Shared in RSS? |
| --- | --- | --- |
| Feed query token | `studio-config.json` → `sources[].feedUrl` | No |
| Password, cookie, bearer token, header | `studio-config.json` → `sources[].auth` | No |
| Inbox token | `studio-config.json` → `inbox.token` and the Worker secret `INBOX_TOKEN` | No |
| Cloudflare API token | `studio-config.json` → `cloudflare.token` | No |

The dashboard API returns `tokenSet` / `cookieSet` style flags, not the secret. Open Compose on the loopback address to reveal the inbox token.
