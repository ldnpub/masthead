"""HTTP helpers. Authorization and cookies stay on the original host."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from config import UA, JobError


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def host_of(url: str) -> str:
    return urllib.parse.urlparse(url).netloc


def safe_url(url: str) -> str:
    """Drop the query string so logs and job files do not keep tokens."""
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


_SENSITIVE_QUERY = {
    "token", "key", "apikey", "api_key", "auth", "secret", "k",
    "access_token", "sig", "signature", "password", "pass",
}


def public_link(url: str) -> str:
    """Episode links must not republish query secrets."""
    parts = urllib.parse.urlsplit(url or "")
    if not parts.scheme:
        return url or ""
    kept = [
        (k, v)
        for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _SENSITIVE_QUERY
    ]
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(kept), ""))


def source_headers(source: dict | None) -> dict:
    auth = (source or {}).get("auth") or {}
    scheme = str(auth.get("scheme") or "none").lower()
    headers: dict[str, str] = {}
    if scheme == "bearer" and auth.get("token"):
        headers["Authorization"] = "Bearer " + str(auth["token"])
    elif scheme == "basic" and auth.get("username"):
        import base64
        raw = f"{auth.get('username', '')}:{auth.get('password', '')}".encode()
        headers["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")
    elif scheme == "cookie" and auth.get("cookie"):
        headers["Cookie"] = str(auth["cookie"])
    elif scheme == "header" and auth.get("name") and auth.get("value"):
        headers[str(auth["name"])] = str(auth["value"])
    extra = auth.get("headers") or {}
    if isinstance(extra, dict):
        for key, value in extra.items():
            if key and value is not None:
                headers[str(key)] = str(value)
    return headers


def http_get(url: str, headers: dict | None = None, timeout: int = 60, accept: str | None = None, limit: int = 5):
    """GET, following redirects. Secrets are not forwarded to another host."""
    headers = dict(headers or {})
    if accept:
        headers["Accept"] = accept
    current = url
    origin = host_of(url)
    opener = urllib.request.build_opener(_NoRedirect)
    last_error = None
    for _ in range(limit):
        send = {"User-Agent": UA, "Accept": headers.get("Accept", "*/*")}
        current_host = host_of(current)
        same = current_host == origin
        if not same and origin.endswith("cloudflare.com") and current_host.endswith("cloudflare.com"):
            same = True
        if same:
            send.update(headers)
        req = urllib.request.Request(current, headers=send, method="GET")
        try:
            with opener.open(req, timeout=timeout) as res:
                return res.status, res.read(), res.headers, res.geturl()
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code in (301, 302, 303, 307, 308) and exc.headers.get("Location"):
                current = urllib.parse.urljoin(current, exc.headers["Location"])
                continue
            raise
    raise JobError(f"Too many redirects for {safe_url(url)}") from last_error


def http_json(url: str, payload: dict | None = None, headers: dict | None = None, timeout: int = 60, method: str | None = None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    send = {"User-Agent": UA, "Accept": "application/json"}
    if payload is not None:
        send["Content-Type"] = "application/json"
    send.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=send, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as res:
        body = res.read()
        return res.status, json.loads(body.decode("utf-8")), res.headers


def decode_body(body: bytes, headers) -> str:
    charset = "utf-8"
    ctype = ""
    if headers is not None:
        ctype = headers.get("Content-Type") or ""
    import re
    match = re.search(r"charset=([\w.-]+)", ctype, re.I)
    if match:
        charset = match.group(1)
    return body.decode(charset, "replace")
