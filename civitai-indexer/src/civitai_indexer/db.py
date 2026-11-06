from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Iterable


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS sources (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  kind TEXT NOT NULL,
  location TEXT,
  license_note TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS imports (
  id INTEGER PRIMARY KEY,
  source_id INTEGER NOT NULL REFERENCES sources(id),
  artifact TEXT,
  sha256 TEXT,
  records_seen INTEGER NOT NULL DEFAULT 0,
  images_seen INTEGER NOT NULL DEFAULT 0,
  tags_seen INTEGER NOT NULL DEFAULT 0,
  memberships_seen INTEGER NOT NULL DEFAULT 0,
  started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at TEXT
);
CREATE TABLE IF NOT EXISTS images (
  id TEXT PRIMARY KEY,
  url TEXT,
  created_at TEXT,
  model_version_id TEXT,
  nsfw_level INTEGER,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS tags (
  id TEXT PRIMARY KEY,
  name TEXT,
  type TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS image_tags (
  image_id TEXT NOT NULL REFERENCES images(id) ON DELETE CASCADE,
  tag_id TEXT NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
  PRIMARY KEY(image_id, tag_id)
);
CREATE TABLE IF NOT EXISTS image_tag_sources (
  image_id TEXT NOT NULL,
  tag_id TEXT NOT NULL,
  source_id INTEGER NOT NULL REFERENCES sources(id),
  import_id INTEGER REFERENCES imports(id),
  PRIMARY KEY(image_id, tag_id, source_id),
  FOREIGN KEY(image_id, tag_id) REFERENCES image_tags(image_id, tag_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS image_sources (
  image_id TEXT NOT NULL REFERENCES images(id) ON DELETE CASCADE,
  source_id INTEGER NOT NULL REFERENCES sources(id),
  import_id INTEGER REFERENCES imports(id),
  record_sha256 TEXT,
  has_formal_tags INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(image_id, source_id)
);
CREATE TABLE IF NOT EXISTS checkpoints (
  name TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_image_tags_tag ON image_tags(tag_id, image_id);
CREATE INDEX IF NOT EXISTS idx_image_sources_source ON image_sources(source_id, image_id);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[None]:
    try:
        yield
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def ensure_source(conn: sqlite3.Connection, name: str, kind: str, location: str | None = None,
                  license_note: str | None = None) -> int:
    conn.execute(
        "INSERT INTO sources(name, kind, location, license_note) VALUES(?,?,?,?) "
        "ON CONFLICT(name) DO UPDATE SET kind=excluded.kind, location=COALESCE(excluded.location,sources.location), "
        "license_note=COALESCE(excluded.license_note,sources.license_note)",
        (name, kind, location, license_note),
    )
    return int(conn.execute("SELECT id FROM sources WHERE name=?", (name,)).fetchone()[0])


def begin_import(conn: sqlite3.Connection, source_id: int, artifact: str | None, sha256: str | None) -> int:
    cur = conn.execute("INSERT INTO imports(source_id, artifact, sha256) VALUES(?,?,?)", (source_id, artifact, sha256))
    return int(cur.lastrowid)


def finish_import(conn: sqlite3.Connection, import_id: int, counters: dict[str, int]) -> None:
    conn.execute(
        "UPDATE imports SET records_seen=?, images_seen=?, tags_seen=?, memberships_seen=?, finished_at=CURRENT_TIMESTAMP WHERE id=?",
        (counters["records"], counters["images"], counters["tags"], counters["memberships"], import_id),
    )


def upsert_tag(conn: sqlite3.Connection, tag: dict[str, Any]) -> bool:
    tag_id = str(tag.get("id", tag.get("tagId", ""))).strip()
    if not tag_id:
        return False
    name = tag.get("name") or tag.get("tagName")
    tag_type = tag.get("type") or tag.get("entityType")
    conn.execute(
        "INSERT INTO tags(id,name,type,metadata_json) VALUES(?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET name=COALESCE(excluded.name,tags.name), "
        "type=COALESCE(excluded.type,tags.type), metadata_json=excluded.metadata_json, updated_at=CURRENT_TIMESTAMP",
        (tag_id, str(name) if name is not None else None, str(tag_type) if tag_type is not None else None, canonical_json(tag)),
    )
    return True


def _tag_id(tag: Any) -> tuple[str | None, dict[str, Any] | None]:
    if isinstance(tag, dict):
        value = tag.get("id", tag.get("tagId"))
        return (str(value), tag) if value is not None else (None, None)
    if isinstance(tag, (str, int)):
        return str(tag), {"id": str(tag)}
    return None, None


def upsert_image(conn: sqlite3.Connection, image: dict[str, Any], source_id: int, import_id: int | None) -> tuple[bool, int]:
    image_id = image.get("id", image.get("imageId"))
    if image_id is None:
        return False, 0
    image_id = str(image_id)
    meta = image.get("meta") if isinstance(image.get("meta"), dict) else {}
    url = image.get("url") or image.get("imageUrl") or image.get("download_url") or image.get("page_url") or meta.get("url")
    created_at = image.get("createdAt") or image.get("created_at")
    model_version_id = image.get("modelVersionId") or image.get("model_version_id")
    nsfw_level = image.get("nsfwLevel")
    conn.execute(
        "INSERT INTO images(id,url,created_at,model_version_id,nsfw_level,metadata_json) VALUES(?,?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET url=COALESCE(excluded.url,images.url), "
        "created_at=COALESCE(excluded.created_at,images.created_at), "
        "model_version_id=COALESCE(excluded.model_version_id,images.model_version_id), "
        "nsfw_level=COALESCE(excluded.nsfw_level,images.nsfw_level), metadata_json=excluded.metadata_json, updated_at=CURRENT_TIMESTAMP",
        (image_id, url, created_at, str(model_version_id) if model_version_id is not None else None, nsfw_level, canonical_json(image)),
    )
    raw_tags = image.get("tagIds")
    if raw_tags is None:
        raw_tags = image.get("tags", [])
    if not isinstance(raw_tags, list):
        raw_tags = []
    has_tags = int("tagIds" in image or "tags" in image)
    conn.execute(
        "INSERT INTO image_sources(image_id,source_id,import_id,record_sha256,has_formal_tags) VALUES(?,?,?,?,?) "
        "ON CONFLICT(image_id,source_id) DO UPDATE SET import_id=excluded.import_id, record_sha256=excluded.record_sha256, "
        "has_formal_tags=MAX(image_sources.has_formal_tags,excluded.has_formal_tags)",
        (image_id, source_id, import_id, digest(image), has_tags),
    )
    memberships = 0
    for raw_tag in raw_tags:
        tag_id, tag_record = _tag_id(raw_tag)
        if not tag_id:
            continue
        assert tag_record is not None
        upsert_tag(conn, tag_record)
        conn.execute("INSERT OR IGNORE INTO image_tags(image_id,tag_id) VALUES(?,?)", (image_id, tag_id))
        conn.execute(
            "INSERT OR IGNORE INTO image_tag_sources(image_id,tag_id,source_id,import_id) VALUES(?,?,?,?)",
            (image_id, tag_id, source_id, import_id),
        )
        memberships += 1
    return True, memberships


def set_checkpoint(conn: sqlite3.Connection, name: str, value: Any) -> None:
    conn.execute(
        "INSERT INTO checkpoints(name,value_json) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value_json=excluded.value_json, updated_at=CURRENT_TIMESTAMP",
        (name, canonical_json(value)),
    )


def get_checkpoint(conn: sqlite3.Connection, name: str) -> Any | None:
    row = conn.execute("SELECT value_json FROM checkpoints WHERE name=?", (name,)).fetchone()
    return json.loads(row[0]) if row else None


def coverage(conn: sqlite3.Connection) -> dict[str, Any]:
    scalar = lambda q: int(conn.execute(q).fetchone()[0])
    source_rows = conn.execute(
        "SELECT s.name, s.kind, COUNT(DISTINCT isrc.image_id) AS images, "
        "COUNT(DISTINCT CASE WHEN isrc.has_formal_tags=1 THEN isrc.image_id END) AS tagged_images, "
        "COUNT(DISTINCT its.image_id || ':' || its.tag_id) AS memberships "
        "FROM sources s LEFT JOIN image_sources isrc ON isrc.source_id=s.id "
        "LEFT JOIN image_tag_sources its ON its.source_id=s.id GROUP BY s.id ORDER BY images DESC, s.name"
    ).fetchall()
    return {
        "images": scalar("SELECT COUNT(*) FROM images"),
        "tags": scalar("SELECT COUNT(*) FROM tags"),
        "tagged_images": scalar("SELECT COUNT(DISTINCT image_id) FROM image_tags"),
        "memberships": scalar("SELECT COUNT(*) FROM image_tags"),
        "sources": [dict(row) for row in source_rows],
    }


def search_images(conn: sqlite3.Connection, all_tag_ids: Iterable[str], any_tag_ids: Iterable[str],
                  exclude_tag_ids: Iterable[str], limit: int) -> list[dict[str, Any]]:
    all_ids, any_ids, excluded = list(all_tag_ids), list(any_tag_ids), list(exclude_tag_ids)
    clauses: list[str] = []
    params: list[Any] = []
    if all_ids:
        placeholders = ",".join("?" for _ in all_ids)
        clauses.append(f"i.id IN (SELECT image_id FROM image_tags WHERE tag_id IN ({placeholders}) GROUP BY image_id HAVING COUNT(DISTINCT tag_id)=?)")
        params.extend(all_ids)
        params.append(len(set(all_ids)))
    if any_ids:
        placeholders = ",".join("?" for _ in any_ids)
        clauses.append(f"i.id IN (SELECT image_id FROM image_tags WHERE tag_id IN ({placeholders}))")
        params.extend(any_ids)
    if excluded:
        placeholders = ",".join("?" for _ in excluded)
        clauses.append(f"i.id NOT IN (SELECT image_id FROM image_tags WHERE tag_id IN ({placeholders}))")
        params.extend(excluded)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    rows = conn.execute(
        "SELECT i.id,i.url,i.created_at,i.model_version_id,i.nsfw_level, "
        "GROUP_CONCAT(t.id || ':' || COALESCE(t.name,''), '|') AS tags "
        "FROM images i LEFT JOIN image_tags it ON it.image_id=i.id LEFT JOIN tags t ON t.id=it.tag_id "
        + where + " GROUP BY i.id ORDER BY i.created_at DESC, i.id DESC LIMIT ?", params
    ).fetchall()
    return [dict(row) for row in rows]
