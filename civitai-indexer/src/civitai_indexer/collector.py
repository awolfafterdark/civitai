from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from . import db
from .importers import find_next_cursor, import_payload


TRPC_ENDPOINT = "https://civitai.com/api/trpc/image.getInfinite"
TRPC_HEADERS = {
    "Origin": "https://civitai.com",
    "Referer": "https://civitai.com/images",
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
}


def fetch_json(url: str, headers: dict[str, str], timeout: float = 90.0) -> Any:
    request = Request(url, headers=headers, method="GET")
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def trpc_url(cursor: Any | None = None, limit: int = 200) -> str:
    query: dict[str, Any] = {"limit": limit, "sort": "Newest", "include": ["tagIds"], "browsingLevel": 1}
    if cursor is not None:
        query["cursor"] = cursor
    return TRPC_ENDPOINT + "?" + urlencode({"input": json.dumps({"json": query}, separators=(",", ":"))})


def sync_trpc(conn, *, max_pages: int = 1, checkpoint: str = "trpc-newest", delay_seconds: float = 2.0,
              timeout: float = 90.0, resume: bool = True, fetcher=fetch_json) -> dict[str, int]:
    """Fetch metadata/tag IDs only. Never dereferences image URLs or downloads media bytes."""
    if not 1 <= max_pages:
        raise ValueError("max_pages must be at least one")
    if resume:
        saved = db.get_checkpoint(conn, checkpoint) or {}
        cursor = saved.get("cursor")
    else:
        cursor = None
    totals = {"pages": 0, "records": 0, "images": 0, "tags": 0, "memberships": 0}
    for page in range(max_pages):
        try:
            payload = fetcher(trpc_url(cursor), TRPC_HEADERS, timeout)
        except HTTPError as exc:
            if exc.code == 401:
                raise RuntimeError("HTTP 401. Verify Origin, Referer, and User-Agent match the documented browser-context baseline.") from exc
            raise RuntimeError(f"HTTP {exc.code} while fetching cursor {cursor!r}") from exc
        except URLError as exc:
            raise RuntimeError(f"Network failure while fetching cursor {cursor!r}: {exc.reason}") from exc
        counters = import_payload(conn, payload, "civitai-image-getInfinite", "public-facing-trpc", f"trpc:{checkpoint}:{page}", TRPC_ENDPOINT)
        for key in ("records", "images", "tags", "memberships"):
            totals[key] += counters[key]
        totals["pages"] += 1
        cursor = find_next_cursor(payload)
        db.set_checkpoint(conn, checkpoint, {"cursor": cursor, "page": page + 1, "endpoint": TRPC_ENDPOINT})
        conn.commit()
        if cursor is None:
            break
        if page + 1 < max_pages and delay_seconds > 0:
            time.sleep(delay_seconds)
    return totals
