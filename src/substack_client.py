"""
Minimal client for pulling your own paid Substack content.

Posts: uses Substack's public archive/post JSON endpoints (the same ones the
unofficial `substack-api` package uses), but attaches your logged-in session
cookie so paywalled posts come back in full instead of the free preview.

Chat: Substack Chat has no documented API at all (official or unofficial),
so there is no verified endpoint to hardcode here. `fetch_chat_raw` calls
whatever endpoint URL you discover yourself from your browser's Network tab
(see README "Finding your chat endpoint") and hands back the parsed JSON --
the UI layer does its best to make sense of the shape it gets back.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import requests
from bs4 import BeautifulSoup

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_TIMEOUT = 30


class SubstackAuthError(RuntimeError):
    """Raised when a request that should have returned paid content didn't."""


@dataclass
class PostMeta:
    slug: str
    title: str
    subtitle: str
    url: str
    post_date: str
    audience: str  # "everyone" or "only_paid" (paywalled)


def _subdomain(pub_url: str) -> str:
    match = re.search(r"https?://([^./]+)\.substack\.com", pub_url)
    if not match:
        raise ValueError(
            f"Expected a URL like https://yourpub.substack.com, got: {pub_url!r}"
        )
    return match.group(1)


def _headers(cookie_header: str | None) -> dict:
    headers = {"User-Agent": _UA, "Accept": "application/json"}
    if cookie_header:
        headers["Cookie"] = cookie_header
    return headers


def cookies_to_header(cookies: list[dict[str, Any]]) -> str:
    """Turn a browser cookie export (list of {"name":..., "value":...}) into a Cookie header string."""
    parts = [f"{c['name']}={c['value']}" for c in cookies if c.get("name") and c.get("value")]
    return "; ".join(parts)


def parse_pasted_cookies(text: str) -> str:
    """
    Build a Cookie header from cookie lines copied straight out of a browser cookie-editor
    extension, one per line, in the raw `name=value;Domain=...;Path=...;Expires=...` form
    those tools tend to produce (as opposed to hand-built JSON). Also tolerates plain
    `name=value` lines and blank lines between entries.
    """
    parts = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        name_value = line.split(";", 1)[0].strip()
        if "=" in name_value:
            parts.append(name_value)
    return "; ".join(parts)


def fetch_recent_posts(pub_url: str, limit: int = 10) -> list[PostMeta]:
    """List recent post metadata. Works without auth -- titles/slugs are public even for paid posts."""
    subdomain = _subdomain(pub_url)
    endpoint = f"https://{subdomain}.substack.com/api/v1/archive"
    resp = requests.get(
        endpoint,
        params={"sort": "new", "search": "", "offset": 0, "limit": limit},
        headers=_headers(None),
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return [
        PostMeta(
            slug=item["slug"],
            title=item.get("title", "(untitled)"),
            subtitle=item.get("subtitle", "") or "",
            url=item.get("canonical_url", f"https://{subdomain}.substack.com/p/{item['slug']}"),
            post_date=item.get("post_date", ""),
            audience=item.get("audience", "unknown"),
        )
        for item in data
    ]


def fetch_post_content(pub_url: str, slug: str, cookie_header: str | None) -> dict:
    """Fetch a single post's full content. Requires a valid session cookie for paywalled posts."""
    subdomain = _subdomain(pub_url)
    endpoint = f"https://{subdomain}.substack.com/api/v1/posts/{slug}"
    resp = requests.get(endpoint, headers=_headers(cookie_header), timeout=_TIMEOUT)
    resp.raise_for_status()
    post = resp.json()

    body_html = post.get("body_html") or ""
    text = BeautifulSoup(body_html, "html.parser").get_text("\n").strip()

    if post.get("audience") == "only_paid" and cookie_header and len(text) < 200:
        raise SubstackAuthError(
            "This is a paid post but the body came back nearly empty. Your session "
            "cookie is probably expired or missing -- re-export it from your browser "
            "(see README) and update the SUBSTACK_COOKIES_JSON secret."
        )

    return {
        "slug": slug,
        "title": post.get("title", "(untitled)"),
        "subtitle": post.get("subtitle", "") or "",
        "post_date": post.get("post_date", ""),
        "audience": post.get("audience", "unknown"),
        "url": post.get("canonical_url", f"https://{subdomain}.substack.com/p/{slug}"),
        "text": text,
    }


def fetch_chat_raw(endpoint_url: str, cookie_header: str) -> Any:
    """
    Call a user-supplied chat endpoint URL (discovered via browser devtools) with
    the user's session cookie attached. Returns parsed JSON as-is -- the caller
    is responsible for making sense of whatever shape comes back.
    """
    resp = requests.get(endpoint_url, headers=_headers(cookie_header), timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def extract_chat_messages(raw: Any) -> list[dict]:
    """
    Best-effort flattening of a chat API response into a uniform list of
    {author, created_at, body} dicts. Substack Chat's JSON shape is unverified
    and may not match this -- if it returns nothing useful, fall back to the
    "Paste in" tab in the UI instead of fighting this parser.
    """
    candidates: list[Any] = []
    if isinstance(raw, list):
        candidates = raw
    elif isinstance(raw, dict):
        for key in ("items", "threads", "comments", "messages", "data"):
            if isinstance(raw.get(key), list):
                candidates = raw[key]
                break

    messages = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        body = item.get("body") or item.get("body_text") or item.get("message") or ""
        author = (
            (item.get("author") or {}).get("name")
            if isinstance(item.get("author"), dict)
            else item.get("author") or item.get("name") or "Unknown"
        )
        created_at = item.get("created_at") or item.get("date") or item.get("post_date") or ""
        if body:
            messages.append({"author": author, "created_at": created_at, "body": body})
    return messages
