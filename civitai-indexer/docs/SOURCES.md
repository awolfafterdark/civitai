# Source and provenance policy

This project indexes metadata and formal image→tag relationships. It does **not** fetch, persist, thumbnail, hash, or otherwise download image/video media.

## Current source roles

| Source | Role | What may be imported | Important limitation |
|---|---|---|---|
| Civitai `image.getInfinite` | Current public-gallery membership feed | Image IDs, metadata returned in-page, `tagIds`, cursors | Undocumented route; use normal browser Origin/Referer request context and conservative pacing. |
| Civitai `/api/v1/images` | Public image enumeration and audit | JSON metadata and opaque `metadata.nextCursor` | Top-level formal `tagIds` are not relied upon unless present in the actual response. |
| Civitai `tag.getAll` | Tag catalog | Tag IDs, names, types | Does not establish image membership by itself. |
| Civistash sidecars | Historical metadata ledger | JSON sidecar records only | The 2026-06-08/09 shards were observed to omit `tags`/`tagIds`; do not treat them as formal memberships without validating each imported shard. |
| Civ-40M / academic ledgers | Historical completeness ledger | Metadata files only where access and licensing permit | Metadata-only rows must not be treated as tag-complete. |
| `lehduong/civitai-hq` | Public historical metadata ledger | 25 Parquet files (~200 MB, 1.1M rows) | Schema has no formal image tag relation. |
| `AER6/civitai-multimodal-rag-data` | Public, strictly-SFW metadata/semantic ledger | `data/meta.jsonl` (97,965 records); embedding arrays intentionally excluded | No formal image tag relation. |
| `thefcraft/civitai-stable-diffusion-337k` | Public historical prompt/metadata ledger | Two public Parquet exports (327.1k rows; 157.7 MB); no `images/` archive is touched | Schema has prompts and generation fields but no formal image tag relation. |
| `pixelgraple/civitai-image-search` | Design/reference implementation for community indexing | Public source code and schema only | Its catalog is contributor-selected and its worker persists media, so it is neither a complete corpus nor an import source for this media-free project. |

## Non-negotiable data rules

- `image_tags` means a formal relation was actually observed in a source record.
- `image_sources.has_formal_tags` records whether a contributing source carried a formal tag field.
- A metadata-only image is useful for coverage measurement but never for exact AND/NOT tag claims.
- An upstream search service is never treated as a dataset merely because it exposes results. A merge requires an explicit, licensed metadata export with provenance.
- Every import receives a source record, an import record, artifact hash, and per-source contribution counters.
- The schema unions independently verified tag memberships; a later partial response cannot erase an earlier verified relation.

## Confirmed request baseline

The public-facing `image.getInfinite` route previously returned HTTP 200 when the request included:

```text
Origin: https://civitai.com
Referer: https://civitai.com/images
User-Agent: Mozilla/5.0
```

An HTTP 401 after omitting that browser context is an incomplete-request failure, not by itself proof that the route disappeared or needs a token.
