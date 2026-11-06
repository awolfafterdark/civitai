from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Iterator

from . import db


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def open_text(path: Path):
    return gzip.open(path, "rt", encoding="utf-8") if path.suffix == ".gz" else path.open("r", encoding="utf-8")


def unwrap_items(payload: Any) -> list[dict[str, Any]]:
    """Find a conventional Civitai item list without assuming one fragile response envelope."""
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    items = payload.get("items")
    if isinstance(items, list):
        return [x for x in items if isinstance(x, dict)]
    for key in ("json", "data", "result", "response"):
        found = unwrap_items(payload.get(key))
        if found:
            return found
    return []


def find_next_cursor(payload: Any) -> Any | None:
    if isinstance(payload, dict):
        for key in ("nextCursor", "next_cursor"):
            if key in payload and payload[key] is not None:
                return payload[key]
        meta = payload.get("metadata")
        if isinstance(meta, dict) and meta.get("nextCursor") is not None:
            return meta["nextCursor"]
        for key in ("json", "data", "result", "response"):
            found = find_next_cursor(payload.get(key))
            if found is not None:
                return found
    return None


def iter_json_records(path: Path) -> Iterator[dict[str, Any]]:
    with open_text(path) as handle:
        if path.name.endswith((".jsonl", ".ndjson", ".jsonl.gz", ".ndjson.gz")):
            for line_number, line in enumerate(handle, 1):
                if line.strip():
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise ValueError(f"Invalid JSON at {path}:{line_number}: {exc}") from exc
                    if isinstance(record, dict):
                        yield record
            return
        payload = json.load(handle)
    yield from unwrap_items(payload)


def import_images(conn, path: Path, source_name: str, source_kind: str, location: str | None = None,
                  license_note: str | None = None) -> dict[str, int]:
    source_id = db.ensure_source(conn, source_name, source_kind, location, license_note)
    import_id = db.begin_import(conn, source_id, str(path), sha256_file(path))
    counters = {"records": 0, "images": 0, "tags": 0, "memberships": 0}
    with db.transaction(conn):
        for record in iter_json_records(path):
            counters["records"] += 1
            ok, memberships = db.upsert_image(conn, record, source_id, import_id)
            counters["images"] += int(ok)
            counters["memberships"] += memberships
            raw_tags = record.get("tagIds", record.get("tags", []))
            counters["tags"] += len(raw_tags) if isinstance(raw_tags, list) else 0
        db.finish_import(conn, import_id, counters)
    return counters


def import_tags(conn, path: Path, source_name: str, source_kind: str, location: str | None = None,
                license_note: str | None = None) -> dict[str, int]:
    source_id = db.ensure_source(conn, source_name, source_kind, location, license_note)
    import_id = db.begin_import(conn, source_id, str(path), sha256_file(path))
    counters = {"records": 0, "images": 0, "tags": 0, "memberships": 0}
    with db.transaction(conn):
        for record in iter_json_records(path):
            counters["records"] += 1
            counters["tags"] += int(db.upsert_tag(conn, record))
        db.finish_import(conn, import_id, counters)
    return counters


def import_payload(conn, payload: Any, source_name: str, source_kind: str, artifact: str,
                   location: str | None = None) -> dict[str, int]:
    source_id = db.ensure_source(conn, source_name, source_kind, location)
    import_id = db.begin_import(conn, source_id, artifact, db.digest(payload))
    counters = {"records": 0, "images": 0, "tags": 0, "memberships": 0}
    with db.transaction(conn):
        for record in unwrap_items(payload):
            counters["records"] += 1
            ok, memberships = db.upsert_image(conn, record, source_id, import_id)
            counters["images"] += int(ok)
            counters["memberships"] += memberships
            raw_tags = record.get("tagIds", record.get("tags", []))
            counters["tags"] += len(raw_tags) if isinstance(raw_tags, list) else 0
        db.finish_import(conn, import_id, counters)
    return counters
