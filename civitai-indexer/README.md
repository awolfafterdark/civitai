# Civitai Indexer

A media-free, provenance-aware local Civitai image/tag database. It exists to make local tag search and coverage measurement possible without downloading image or video content and without treating a 200-item remote response window as a local search limit.

## What is implemented

- SQLite canonical store for image IDs, metadata, tags, exact image→tag memberships, source provenance, import hashes, and cursor checkpoints.
- JSON/JSONL/NDJSON/gzip metadata and sidecar importer that accepts REST-style and nested tRPC-style envelopes.
- Source-aware coverage report that distinguishes all images from those with verified formal tag membership.
- Local AND/OR/NOT tag-ID queries across the entire imported corpus.
- Conservative `image.getInfinite` newest-first collector using the verified browser-context request shape, opaque cursor checkpoints, bounded pages, and no media retrieval.
- Streaming `.tar.gz` sidecar importer: reads only JSON members into SQLite, immediately discards media members, and parallelizes independent archives through temporary metadata-only worker databases.
- Standard-library-only Python implementation and deterministic tests.

## Why this is structured this way

The known Civitai 200 maximum is a page limit, not a total traversal limit. Public collectors and the official API depend on cursor pagination. A local index eliminates that page cap for data already imported, but it must retain provenance so incomplete historical coverage is never mistaken for exact global facet counts.

## Quick start

```bash
python -m pip install -e .
python -m civitai_indexer init
python -m civitai_indexer coverage
python -m unittest discover -s tests -v
```

See [docs/OPERATIONS.md](docs/OPERATIONS.md) for ingestion and sync commands, and [docs/SOURCES.md](docs/SOURCES.md) for source rules.

The current external-data decision is recorded in [docs/DATA_ACQUISITION_STATUS.md](docs/DATA_ACQUISITION_STATUS.md). Civistash's sidecars are valuable historical metadata, but the first observed shards did not carry formal tag fields. The repository streams their JSON sidecars without retaining media and treats their rows as a coverage ledger rather than exact tag membership.

The repository includes a bounded GitHub Actions bootstrap job, `.github/workflows/build-initial-civistash-index.yml`, which streams two shards and publishes a seven-day SQLite artifact plus coverage report. It never writes media members or archive files to the runner disk.

`build-initial-civitai-database.yml` is the combined bootstrap: it imports those historical metadata rows, adds one validated live `image.getInfinite` tag page, and publishes one initial SQLite database with source-aware coverage.

`build-lehduong-hq-ledger.yml` imports the public 1.1M-row `lehduong/civitai-hq` Parquet corpus as a separate metadata-only ledger. It downloads only Parquet metadata partitions and deletes each temporary partition after import.

## Deliberate exclusions

This repository does not download media, attempt to access authenticated search indexes, extract credentials, or bypass access controls. It stores only relevant structured metadata and formal tag relationship records returned by permitted sources.
