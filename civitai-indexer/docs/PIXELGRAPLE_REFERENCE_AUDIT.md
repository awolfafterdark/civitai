# Pixelgraple Civitai Image Search: implementation-reference audit

Audited repository: <https://github.com/pixelgraple/civitai-image-search> at its `main` branch on 2026-11-05.

## Correct classification

This is not a downloadable, comprehensive Civitai export. It is a contributor-built, opt-in catalog: a browser extension discovers records from Civitai pages that a contributor chooses to scan; the server receives metadata and then deliberately queues and retains originals and previews. Its README explicitly says its search covers images already indexed by contributors, not every Civitai image.

It therefore must **not** be treated as a corpus source for this repository. Doing so would both create unknown coverage bias and conflict with this project's no-media-persistence rule.

## What we should reuse conceptually

| Reference component | Evidence in reference | Media-free adaptation here |
| --- | --- | --- |
| SQLite FTS5 catalog | `server/schema.sql` defines `images_fts` over prompt, negative prompt, tags, model, and LoRAs. | `image_text_fts` indexes only retained structured metadata. |
| Exact formal-tag filtering | Search first narrows by FTS then preserves exact tag equality using JSON values. | Keep existing `image_tags` AND/OR/NOT relation table as the authoritative formal-tag path. |
| Metadata repair | `server/metadata-page.py` reads bounded, exact-ID hydration data from a public image page; `metadata-backfill.py` uses resumable queues and cooldowns. | Add a bounded, source-policy-approved repair queue only after our archive/API coverage is measured; never fetch media. |
| Long-lived collection state | The extension has separate queues, checkpoints, retries, cooldowns, and deduplication. | Our imports already checkpoint archive and cursor progress; retain per-source checkpoints and immutable import provenance. |
| Precomputed discovery | `discovery-rebuild.php` produces a read-only SQLite cache of normalized model/LoRA/tag/phrase memberships. | Build a separate, regenerable discovery cache after we have a sufficiently large metadata ledger; do not put derived facets in the canonical raw store. |

## Important differences

1. Its `tags_json` is captured *display-name* metadata, whereas this project distinguishes those names from verified Civitai `tagIds`. A text hit in a tag name is useful discovery, but it cannot be advertised as an exact formal facet unless it has an `image_tags` relation with source provenance.
2. Its `download_status='ready'` means an original is locally stored. This project never makes media readiness a condition of indexing or result eligibility.
3. Its collection happens in user browsers against pages they navigate. This project prioritizes permitted bulk metadata sources and a low-rate cursor collector, so it needs source manifests and coverage accounting rather than contributor collection metrics.

## Changes made from this audit

The canonical index now has a separate FTS5 metadata index and `search-text` CLI command. It supports prompt-only, prompt-plus-tag-name, or all-retained-metadata scope. This adds useful search capability to the HQ/AER6/thefcraft/Civistash ledgers without converting their records into tag-membership evidence and without fetching any media.

## Deferred work

- Validate a representative sample of public image-page metadata repair before enabling it at scale; use strict rate, retry, and provenance controls.
- Create a regenerable discovery cache for models, LoRAs, named tags, and prompt phrases once the large ledger artifacts are combined.
- Keep the reference repository as a design input, not a dependency or a source of its shared catalog contents.
