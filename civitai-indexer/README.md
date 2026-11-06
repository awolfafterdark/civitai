# Civitai Indexer

A media-free, provenance-aware local Civitai image/tag database. It exists to make local tag search and coverage measurement possible without downloading image or video content and without treating a 200-item remote response window as a local search limit.

## What is implemented

- SQLite canonical store for image IDs, metadata, tags, exact image→tag memberships, source provenance, import hashes, and cursor checkpoints.
- JSON/JSONL/NDJSON/gzip metadata and sidecar importer that accepts REST-style and nested tRPC-style envelopes.
- Source-aware coverage report that distinguishes all images from those with verified formal tag membership.
- Local AND/OR/NOT tag-ID queries across the entire imported corpus.
- Conservative `image.getInfinite` newest-first collector using the verified browser-context request shape, opaque cursor checkpoints, bounded pages, and no media retrieval.
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

The current external-data decision is recorded in [docs/DATA_ACQUISITION_STATUS.md](docs/DATA_ACQUISITION_STATUS.md). Civistash's sidecars are valuable, but they are only distributed inside media-containing WebDataset archives, so this repository intentionally does not download them.

## Deliberate exclusions

This repository does not download media, attempt to access authenticated search indexes, extract credentials, or bypass access controls. It stores only relevant structured metadata and formal tag relationship records returned by permitted sources.
