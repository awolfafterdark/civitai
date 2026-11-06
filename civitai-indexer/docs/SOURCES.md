# Source and provenance policy

This project indexes metadata and formal image→tag relationships. It does **not** fetch, persist, thumbnail, hash, or otherwise download image/video media.

## Current source roles

| Source | Role | What may be imported | Important limitation |
|---|---|---|---|
| Civitai `image.getInfinite` | Current public-gallery membership feed | Image IDs, metadata returned in-page, `tagIds`, cursors | Undocumented route; use normal browser Origin/Referer request context and conservative pacing. |
| Civitai `/api/v1/images` | Public image enumeration and audit | JSON metadata and opaque `metadata.nextCursor` | Top-level formal `tagIds` are not relied upon unless present in the actual response. |
| Civitai `tag.getAll` | Tag catalog | Tag IDs, names, types | Does not establish image membership by itself. |
| Civistash sidecars | Historical verified memberships | JSON sidecar records only | Respect the dataset's license/terms; do not download WebDataset image payloads. |
| Civ-40M / academic ledgers | Historical completeness ledger | Metadata files only where access and licensing permit | Metadata-only rows must not be treated as tag-complete. |

## Non-negotiable data rules

- `image_tags` means a formal relation was actually observed in a source record.
- `image_sources.has_formal_tags` records whether a contributing source carried a formal tag field.
- A metadata-only image is useful for coverage measurement but never for exact AND/NOT tag claims.
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
