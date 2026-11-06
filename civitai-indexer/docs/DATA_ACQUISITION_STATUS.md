# Data acquisition status

Observed on 2026-11-05 from the public Hugging Face repository metadata for `Hyphonical/Civistash`.

## What was safely acquired

- `dataset_infos.json` (586 bytes), retained under `data/source_snapshots/` as a provenance snapshot.
- The dataset card/schema, used to verify the archive layout and that formal tags are present in each JSON sidecar.

No media and no archive shard was downloaded.

## Why the archive was deliberately not downloaded

The repository contains daily `.tar.gz` WebDataset shards. Each shard holds paired media files and `<image-id>.json` metadata sidecars, but does **not** publish sidecars as separate downloadable files. The observed daily shards range from approximately 1.1 GB to 7.5 GB. Downloading a shard would necessarily transfer media bytes even if the extractor ignored them after receipt.

That is incompatible with this project's media-free rule. The indexer therefore accepts sidecars only when they are available separately, already legally present on disk, or exported by an upstream provider as metadata-only files.

## Source utility

| Source | Current role | Status |
|---|---|---|
| Civistash | Validates sidecar schema and historical popular-content coverage | Cannot be directly ingested without transferring media-containing archives. |
| Public Civitai `image.getInfinite` | Preferred live metadata/tag relationship collector | Code implemented; direct access blocked in this environment. |
| Public Civitai `/api/v1/images` | Coverage ledger and public-image enumeration | Pending a permitted collection environment. |
| Civ-40M / academic sources | Historical ledger and optional metadata import | Needs a metadata-only distribution plus license review before ingestion. |

## Next data milestone

Obtain one of the following without media payloads:

1. a metadata-only export from Civistash's maintainer;
2. an official/public Civitai JSON traversal using the included checkpointed collector; or
3. a licensed metadata-only research release.

Once a source is present, run `import-images`, then `coverage`; the report will distinguish records with formal tags from metadata-only ledger rows.
