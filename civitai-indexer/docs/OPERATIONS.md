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

## 7. Large WebDataset archives: stream and discard media

For an ordinary `.tar.gz`, gzip must be read in order. This command never saves an archive or image/video member: it reads each tar member from the network stream, imports only `*.json` sidecars, and skips media bytes immediately.

```bash
# Optional, only for a dataset that requires it. Keep this token out of shell history and source files.
export HF_TOKEN='temporary-read-token'

python -m civitai_indexer --db data/civitai.sqlite stream-tar-gz \
  'https://example.org/archive.tar.gz' --source metadata-sidecars
```

For speed, parallelize **separate archives**, not arbitrary ranges of one gzip file:

```bash
python -m civitai_indexer --db data/civitai.sqlite stream-tar-gz-list shards.txt \
  --source civistash-sidecars --workers 4
```

`shards.txt` contains one direct archive URL per line. Each worker uses a temporary SQLite database for structured records only; the coordinator merges it into the canonical database and checkpoints each completed URL. A failed URL remains uncheckpointed and is retried on the next run. The command reports media member count and uncompressed media bytes discarded, but retains neither.
