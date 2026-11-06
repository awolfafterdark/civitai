# Operations runbook

## 1. Create a local index

```bash
python -m pip install -e .
civitai-index --db data/civitai.sqlite init
```

## 2. Import only metadata/sidecar files

```bash
civitai-index --db data/civitai.sqlite import-images /path/to/sidecars.jsonl \
  --source civistash-sidecars --kind dataset --location https://huggingface.co/datasets/Hyphonical/Civistash

civitai-index --db data/civitai.sqlite import-tags /path/to/tags.json \
  --source civitai-tag-catalog --kind public-facing-trpc
```

The importer accepts JSON arrays, `{ "items": [...] }` responses, tRPC-style nested JSON envelopes, JSONL, NDJSON, and `.gz` variants. It never requests image URLs.

## 3. Measure before backfilling

```bash
civitai-index --db data/civitai.sqlite coverage
```

Use this report to quantify total images, tagged images, memberships, and source-specific contributions. Do not call an index near-complete until this measurement exists.

## 4. Local exact tag querying

```bash
# image must have both 5772 and 5133, and must not have 3629
civitai-index --db data/civitai.sqlite search --all 5772,5133 --exclude 3629
```

`--all`, `--any`, and `--exclude` implement AND, OR, and NOT over verified local memberships. This removes the gallery's per-request result window from local search; it does not make a partial corpus complete.

## 5. Conservative newest-first sync

```bash
# Deliberately one page by default; no media content is downloaded.
civitai-index --db data/civitai.sqlite sync-trpc

# Explicit finite catch-up run. Resume uses the saved opaque cursor.
civitai-index --db data/civitai.sqlite sync-trpc --pages 50 --delay 2
```

The collector stores only JSON response fields and formal tag IDs. It follows the opaque cursor sequentially, checkpoints after every page, and never uses parallel workers on one cursor chain. A 401 diagnostic explicitly points to the required browser-context baseline.

## 6. Backfill decision

Prioritize raw metadata/sidecar archives first. Only run a historical traversal after measuring the current coverage and confirming the missing membership benefit justifies it. Cursors must be followed until absent; an empty page with a next cursor is not terminal.
