from __future__ import annotations

import concurrent.futures
import json
import os
import sqlite3
import tarfile
import tempfile
from contextlib import closing
from pathlib import Path
from typing import Any, BinaryIO, Callable, Iterable
from urllib.request import Request, urlopen

from . import db


OpenStream = Callable[[str, dict[str, str], float], BinaryIO]


def http_stream(url: str, headers: dict[str, str], timeout: float) -> BinaryIO:
    """Open a remote response body. The caller consumes it once; no archive is written to disk."""
    return urlopen(Request(url, headers=headers), timeout=timeout)


def default_headers() -> dict[str, str]:
    headers = {"User-Agent": "civitai-indexer/0.1 metadata-only"}
    token = os.environ.get("HF_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _empty_counters() -> dict[str, int]:
    return {"records": 0, "images": 0, "tags": 0, "memberships": 0, "skipped_media": 0, "discarded_media_bytes": 0}


def stream_tar_gz(conn: sqlite3.Connection, url: str, source_name: str, source_kind: str = "webdataset-sidecars",
                  *, timeout: float = 90.0, opener: OpenStream = http_stream, headers: dict[str, str] | None = None,
                  commit_every: int = 500) -> dict[str, int]:
    """Stream one gzip-compressed tar archive and ingest only JSON members.

    Media members are never extracted or written. Standard gzip remains sequential, so their
    compressed bytes still traverse the connection before tar can reach later JSON members.
    """
    source_id = db.ensure_source(conn, source_name, source_kind, url)
    import_id = db.begin_import(conn, source_id, url, db.digest({"url": url, "mode": "stream-tar-gz"}))
    counters = _empty_counters()
    request_headers = default_headers()
    request_headers.update(headers or {})
    pending = 0
    with closing(opener(url, request_headers, timeout)) as response:
        with tarfile.open(fileobj=response, mode="r|gz") as archive:
            for member in archive:
                if not member.isfile():
                    continue
                if not member.name.lower().endswith(".json"):
                    counters["skipped_media"] += 1
                    counters["discarded_media_bytes"] += member.size
                    continue
                extracted = archive.extractfile(member)
                if extracted is None:
                    continue
                try:
                    record = json.load(extracted)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ValueError(f"Invalid JSON sidecar {member.name!r} in {url}") from exc
                if not isinstance(record, dict):
                    continue
                counters["records"] += 1
                ok, memberships = db.upsert_image(conn, record, source_id, import_id)
                counters["images"] += int(ok)
                counters["memberships"] += memberships
                raw_tags = record.get("tagIds", record.get("tags", []))
                counters["tags"] += len(raw_tags) if isinstance(raw_tags, list) else 0
                pending += 1
                if pending >= commit_every:
                    conn.commit()
                    pending = 0
    db.finish_import(conn, import_id, counters)
    conn.commit()
    return counters


def _worker(url: str, source_name: str, source_kind: str, timeout: float) -> tuple[str, str, dict[str, int]]:
    handle = tempfile.NamedTemporaryFile(prefix="civitai-indexer-", suffix=".sqlite", delete=False)
    handle.close()
    conn = db.connect(handle.name)
    try:
        result = stream_tar_gz(conn, url, source_name, source_kind, timeout=timeout)
    finally:
        conn.close()
    return url, handle.name, result


def _merge_worker_database(target: sqlite3.Connection, worker_path: str, url: str, source_name: str,
                           source_kind: str) -> dict[str, int]:
    source_id = db.ensure_source(target, source_name, source_kind, url)
    import_id = db.begin_import(target, source_id, url, None)
    counters = _empty_counters()
    worker = sqlite3.connect(worker_path)
    worker.row_factory = sqlite3.Row
    try:
        for row in worker.execute("SELECT metadata_json FROM images ORDER BY id"):
            record = json.loads(row["metadata_json"])
            counters["records"] += 1
            ok, memberships = db.upsert_image(target, record, source_id, import_id)
            counters["images"] += int(ok)
            counters["memberships"] += memberships
            raw_tags = record.get("tagIds", record.get("tags", []))
            counters["tags"] += len(raw_tags) if isinstance(raw_tags, list) else 0
    finally:
        worker.close()
    db.finish_import(target, import_id, counters)
    return counters


def stream_many_tar_gz(conn: sqlite3.Connection, urls: Iterable[str], source_name: str,
                       source_kind: str = "webdataset-sidecars", *, workers: int = 4,
                       timeout: float = 90.0, checkpoint_prefix: str = "stream-tar-gz") -> dict[str, Any]:
    """Process separate archives concurrently, then merge metadata-only worker databases.

    Concurrent work occurs *between* archives. It does not split a single gzip member stream,
    which would be invalid without a seekable/indexed compression format.
    """
    if workers < 1:
        raise ValueError("workers must be at least one")
    candidates = []
    for url in urls:
        url = url.strip()
        if url and db.get_checkpoint(conn, f"{checkpoint_prefix}:{db.digest(url)}") is None:
            candidates.append(url)
    totals: dict[str, Any] = {"archives_requested": len(candidates), "archives_completed": 0, **_empty_counters(), "failures": []}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_worker, url, source_name, source_kind, timeout) for url in candidates]
        for future in concurrent.futures.as_completed(futures):
            worker_path = None
            try:
                url, worker_path, worker_counters = future.result()
                merged = _merge_worker_database(conn, worker_path, url, source_name, source_kind)
                # Count transferred/discarded media from the worker and database records from the merge.
                for key in ("records", "images", "tags", "memberships"):
                    totals[key] += merged[key]
                for key in ("skipped_media", "discarded_media_bytes"):
                    totals[key] += worker_counters[key]
                totals["archives_completed"] += 1
                db.set_checkpoint(conn, f"{checkpoint_prefix}:{db.digest(url)}", {"url": url, "status": "complete"})
                conn.commit()
            except Exception as exc:
                totals["failures"].append(str(exc))
            finally:
                if worker_path:
                    Path(worker_path).unlink(missing_ok=True)
    return totals
