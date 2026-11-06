# Data acquisition status

Observed on 2026-11-05 from the public Hugging Face repository metadata for `Hyphonical/Civistash`.

## What was safely acquired

- `dataset_infos.json` (586 bytes), retained under `data/source_snapshots/` as a provenance snapshot.
- The dataset card/schema, used to verify the archive layout.
- Two streamed Civistash shards, from which only JSON sidecars were written into an SQLite artifact; archive and media member files were never persisted.

The stream necessarily traversed media bytes over the network because a gzip tar archive is sequential, but those members were consumed and discarded without being written to runner disk or included in the artifact.

The Hugging Face Dataset Viewer was also checked as a potential metadata-only escape hatch. It reported no Parquet exports and a failed dataset-generation job (HTTP 500), so it currently cannot serve the JSON sidecar column separately from the archive shards.

An initial two-shard, media-free streaming run completed successfully: it produced 1,927 image metadata records in a 12.5 MB SQLite artifact. Inspection of stored records found no `tags`, `tagIds`, or `tagNames` fields in those actual sidecars. Civistash is therefore currently classified as a metadata coverage ledger, not a verified image→tag source, regardless of the example schema in its dataset card.

## Why complete Civistash coverage is deferred

The repository contains daily `.tar.gz` WebDataset shards. Each shard holds paired media files and `<image-id>.json` metadata sidecars, but does **not** publish sidecars as separate downloadable files. The observed daily shards range from approximately 1.1 GB to 7.5 GB. Downloading a shard would necessarily transfer media bytes even if the extractor ignored them after receipt.

The indexer can process a gzip tar as a forward-only stream and discard non-JSON members, which makes small validation runs possible without media persistence. It is still unsuitable as the primary route to 113 daily shards: every byte of every media member must traverse the runner, while observed early sidecars did not even carry formal tag memberships. A metadata-only sidecar export remains the preferred route.

## Source utility

| Source | Current role | Status |
|---|---|---|
| Civistash | Historical popular-content metadata coverage | Streams without media persistence, but observed shards did not contain formal tag memberships. |
| Public Civitai `image.getInfinite` | Preferred live metadata/tag relationship collector | Code implemented; direct access blocked in this environment. |
| Public Civitai `/api/v1/images` | Coverage ledger and public-image enumeration | Pending a permitted collection environment. |
| Civ-40M / academic sources | Historical ledger and optional metadata import | Needs a metadata-only distribution plus license review before ingestion. |
| `pixelgraple/civitai-image-search` | Reference implementation | Audited: local SQLite + FTS, durable metadata queues, source reactions and repair jobs. Its published service is contributor-selected and stores image originals, so no corpus is imported from it. |

## Next data milestone

Obtain one of the following without media payloads:

1. a metadata-only export from Civistash's maintainer;
2. an official/public Civitai JSON traversal using the included checkpointed collector; or
3. a licensed metadata-only research release.

Once a source is present, run `import-images`, then `coverage`; the report will distinguish records with formal tags from metadata-only ledger rows.
