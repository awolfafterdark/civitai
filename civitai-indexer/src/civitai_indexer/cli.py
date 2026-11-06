from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import db
from .collector import sync_trpc
from .importers import import_images, import_parquet, import_tags
from .streaming import stream_many_tar_gz, stream_tar_gz


def comma_values(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="civitai-index", description="Media-free, provenance-aware Civitai metadata index")
    p.add_argument("--db", default="data/civitai.sqlite", help="SQLite database path (default: data/civitai.sqlite)")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="create schema")
    for name, help_text in (("import-images", "import Civitai-shaped image JSON/JSONL"), ("import-tags", "import tag catalog JSON/JSONL")):
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("path", type=Path)
        cmd.add_argument("--source", required=True)
        cmd.add_argument("--kind", default="dataset")
        cmd.add_argument("--location")
        cmd.add_argument("--license-note")
    parquet = sub.add_parser("import-parquet", help="import metadata-only Parquet in bounded batches (requires .[parquet])")
    parquet.add_argument("path", type=Path)
    parquet.add_argument("--source", required=True)
    parquet.add_argument("--kind", default="dataset")
    parquet.add_argument("--location")
    parquet.add_argument("--license-note")
    parquet.add_argument("--batch-size", type=int, default=4096)
    sub.add_parser("coverage", help="show image/tag membership coverage and source provenance")
    search = sub.add_parser("search", help="local AND/OR/NOT tag-ID search")
    search.add_argument("--all", default="", help="comma-separated tag IDs; every tag must match")
    search.add_argument("--any", default="", help="comma-separated tag IDs; at least one must match")
    search.add_argument("--exclude", default="", help="comma-separated tag IDs that must not match")
    search.add_argument("--limit", type=int, default=50)
    text = sub.add_parser("search-text", help="local full-text metadata search; no media access")
    text.add_argument("query", help="words or quoted phrases; all terms must match")
    text.add_argument("--scope", choices=("prompt", "prompt-tags", "all"), default="prompt-tags")
    text.add_argument("--limit", type=int, default=50)
    sub.add_parser("rebuild-text-index", help="rebuild local FTS from retained metadata without network access")
    sync = sub.add_parser("sync-trpc", help="fetch image metadata and tag IDs only; never downloads media")
    sync.add_argument("--pages", type=int, default=1, help="maximum pages to fetch; explicit opt-in for >1 (default: 1)")
    sync.add_argument("--delay", type=float, default=2.0, help="seconds between page requests (default: 2)")
    sync.add_argument("--checkpoint", default="trpc-newest")
    sync.add_argument("--no-resume", action="store_true")
    archive = sub.add_parser("stream-tar-gz", help="stream one .tar.gz; ingest JSON sidecars only and never write media")
    archive.add_argument("url")
    archive.add_argument("--source", required=True)
    archive.add_argument("--kind", default="webdataset-sidecars")
    archive.add_argument("--timeout", type=float, default=90.0)
    batch = sub.add_parser("stream-tar-gz-list", help="concurrently stream independent tar.gz archives; ingest JSON sidecars only")
    batch.add_argument("url_list", type=Path, help="one archive URL per line")
    batch.add_argument("--source", required=True)
    batch.add_argument("--kind", default="webdataset-sidecars")
    batch.add_argument("--workers", type=int, default=4)
    batch.add_argument("--timeout", type=float, default=90.0)
    batch.add_argument("--checkpoint-prefix", default="stream-tar-gz")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    conn = db.connect(args.db)
    if args.command == "init":
        result = {"database": args.db, "status": "ready"}
    elif args.command == "import-images":
        result = import_images(conn, args.path, args.source, args.kind, args.location, args.license_note)
    elif args.command == "import-tags":
        result = import_tags(conn, args.path, args.source, args.kind, args.location, args.license_note)
    elif args.command == "import-parquet":
        result = import_parquet(conn, args.path, args.source, args.kind, args.location, args.license_note, args.batch_size)
    elif args.command == "coverage":
        result = db.coverage(conn)
    elif args.command == "search":
        result = db.search_images(conn, comma_values(args.all), comma_values(args.any), comma_values(args.exclude), args.limit)
    elif args.command == "search-text":
        import re
        terms = [quoted or bare for quoted, bare in re.findall(r'"([^"]+)"|(\S+)', args.query)]
        result = db.text_search(conn, terms, args.scope, args.limit)
    elif args.command == "rebuild-text-index":
        result = {"indexed_images": db.rebuild_text_index(conn)}
    elif args.command == "sync-trpc":
        result = sync_trpc(conn, max_pages=args.pages, checkpoint=args.checkpoint, delay_seconds=args.delay, resume=not args.no_resume)
    elif args.command == "stream-tar-gz":
        result = stream_tar_gz(conn, args.url, args.source, args.kind, timeout=args.timeout)
    elif args.command == "stream-tar-gz-list":
        result = stream_many_tar_gz(conn, args.url_list.read_text(encoding="utf-8").splitlines(), args.source, args.kind,
                                    workers=args.workers, timeout=args.timeout, checkpoint_prefix=args.checkpoint_prefix)
    else:
        raise AssertionError(args.command)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
