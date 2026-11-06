from __future__ import annotations

import json
import io
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from civitai_indexer import db
from civitai_indexer.collector import TRPC_HEADERS, sync_trpc, trpc_url
from civitai_indexer.importers import find_next_cursor, import_images, import_parquet, unwrap_items
from civitai_indexer.streaming import stream_tar_gz


class IndexerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.conn = db.connect(self.root / "index.sqlite")

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_merges_memberships_and_preserves_source_provenance(self):
        source_a = db.ensure_source(self.conn, "dataset-a", "dataset")
        source_b = db.ensure_source(self.conn, "dataset-b", "dataset")
        with db.transaction(self.conn):
            db.upsert_image(self.conn, {"id": 1, "tagIds": [10, 20], "createdAt": "2025-01-01"}, source_a, None)
            db.upsert_image(self.conn, {"id": 1, "tagIds": [20, 30]}, source_b, None)
        report = db.coverage(self.conn)
        self.assertEqual(report["images"], 1)
        self.assertEqual(report["memberships"], 3)
        self.assertEqual(report["tagged_images"], 1)
        self.assertEqual(len(report["sources"]), 2)

    def test_boolean_search_uses_and_or_not(self):
        source = db.ensure_source(self.conn, "test", "test")
        with db.transaction(self.conn):
            db.upsert_image(self.conn, {"id": "a", "tagIds": [1, 2]}, source, None)
            db.upsert_image(self.conn, {"id": "b", "tagIds": [1, 3]}, source, None)
            db.upsert_image(self.conn, {"id": "c", "tagIds": [2, 3]}, source, None)
        found = db.search_images(self.conn, ["1"], ["2", "3"], ["3"], 10)
        self.assertEqual([row["id"] for row in found], ["a"])

    def test_trpc_envelope_and_cursor_are_normalized(self):
        payload = {"result": {"data": {"json": {"items": [{"id": 7, "tagIds": [9]}], "nextCursor": "opaque"}}}}
        self.assertEqual(unwrap_items(payload), [{"id": 7, "tagIds": [9]}])
        self.assertEqual(find_next_cursor(payload), "opaque")

    def test_sync_uses_proven_browser_context_and_checkpoint(self):
        seen = []
        responses = [
            {"result": {"data": {"json": {"items": [{"id": 1, "tagIds": [11]}], "nextCursor": "two"}}}},
            {"result": {"data": {"json": {"items": [{"id": 2, "tagIds": [12]}]}}}},
        ]
        def fetcher(url, headers, timeout):
            seen.append((url, headers, timeout))
            return responses.pop(0)
        totals = sync_trpc(self.conn, max_pages=2, delay_seconds=0, fetcher=fetcher)
        self.assertEqual(totals["images"], 2)
        self.assertEqual(seen[0][1], TRPC_HEADERS)
        self.assertEqual(db.get_checkpoint(self.conn, "trpc-newest")["cursor"], None)
        self.assertIn("cursor%22%3A%22two", seen[1][0])

    def test_trpc_url_has_limit_and_tagids_without_media_url(self):
        input_value = parse_qs(urlparse(trpc_url()).query)["input"][0]
        body = json.loads(input_value)["json"]
        self.assertEqual(body["limit"], 200)
        self.assertEqual(body["include"], ["tagIds"])
        self.assertNotIn("url", body)

    def test_jsonl_import(self):
        path = self.root / "sample.jsonl"
        path.write_text('{"id":1,"tagIds":[7]}\n{"id":2,"tagIds":[7,8]}\n', encoding="utf-8")
        result = import_images(self.conn, path, "fixture", "fixture")
        self.assertEqual(result["images"], 2)
        self.assertEqual(result["tags"], 3)
        self.assertEqual(result["memberships"], 3)

    def test_download_url_is_normalized_for_metadata_only_sources(self):
        source = db.ensure_source(self.conn, "aer6", "dataset")
        with db.transaction(self.conn):
            db.upsert_image(self.conn, {"id": 99, "download_url": "https://example.invalid/image.webp"}, source, None)
        self.assertEqual(
            self.conn.execute("SELECT url FROM images WHERE id='99'").fetchone()[0],
            "https://example.invalid/image.webp",
        )

    def test_text_search_indexes_prompts_tags_models_and_loras_without_media(self):
        source = db.ensure_source(self.conn, "metadata", "fixture")
        with db.transaction(self.conn):
            db.upsert_image(self.conn, {
                "id": "a", "meta": {"prompt": "golden hour beach portrait", "tags": ["sunset"],
                "modelName": "Krea2", "loras": ["film grain"]},
            }, source, None)
            db.upsert_image(self.conn, {"id": "b", "meta": {"prompt": "studio portrait"}}, source, None)
        self.assertEqual([row["id"] for row in db.text_search(self.conn, ["golden", "beach"], "prompt", 10)], ["a"])
        self.assertEqual([row["id"] for row in db.text_search(self.conn, ["sunset"], "prompt-tags", 10)], ["a"])
        self.assertEqual([row["id"] for row in db.text_search(self.conn, ["Krea2"], "all", 10)], ["a"])

    def test_rebuild_text_index_migrates_existing_metadata_without_network(self):
        source = db.ensure_source(self.conn, "metadata", "fixture")
        with db.transaction(self.conn):
            db.upsert_image(self.conn, {"id": "a", "prompt": "before rebuild"}, source, None)
            self.conn.execute("DELETE FROM image_text_fts")
        self.assertEqual(db.rebuild_text_index(self.conn), 1)
        self.assertEqual([row["id"] for row in db.text_search(self.conn, ["before"], "prompt", 10)], ["a"])

    def test_stream_tar_gz_ingests_sidecars_and_discards_media(self):
        payload = io.BytesIO()
        with tarfile.open(fileobj=payload, mode="w:gz") as archive:
            image_bytes = b"not persisted" * 100
            image_info = tarfile.TarInfo("123.jpg")
            image_info.size = len(image_bytes)
            archive.addfile(image_info, io.BytesIO(image_bytes))
            sidecar = json.dumps({"id": 123, "tags": [{"id": 7, "name": "landscape"}]}).encode()
            sidecar_info = tarfile.TarInfo("123.json")
            sidecar_info.size = len(sidecar)
            archive.addfile(sidecar_info, io.BytesIO(sidecar))
        def opener(url, headers, timeout):
            self.assertNotIn("Authorization", headers)
            return io.BytesIO(payload.getvalue())
        result = stream_tar_gz(self.conn, "https://example.invalid/day.tar.gz", "fixture", opener=opener)
        self.assertEqual(result["images"], 1)
        self.assertEqual(result["memberships"], 1)
        self.assertEqual(result["skipped_media"], 1)
        self.assertEqual(result["discarded_media_bytes"], len(image_bytes))
        self.assertEqual(db.coverage(self.conn)["images"], 1)

    def test_stream_tar_gz_appends_captured_filename_to_github_summary(self):
        payload = io.BytesIO()
        with tarfile.open(fileobj=payload, mode="w:gz") as archive:
            sidecar = json.dumps({"id": 456, "tagIds": [8]}).encode()
            info = tarfile.TarInfo("456.json")
            info.size = len(sidecar)
            archive.addfile(info, io.BytesIO(sidecar))
        summary = self.root / "summary.md"
        old_summary = os.environ.get("GITHUB_STEP_SUMMARY")
        os.environ["GITHUB_STEP_SUMMARY"] = str(summary)
        try:
            stream_tar_gz(self.conn, "https://example.invalid/progress.tar.gz", "fixture",
                          opener=lambda *_: io.BytesIO(payload.getvalue()))
        finally:
            if old_summary is None:
                os.environ.pop("GITHUB_STEP_SUMMARY", None)
            else:
                os.environ["GITHUB_STEP_SUMMARY"] = old_summary
        self.assertIn("`456.json`", summary.read_text(encoding="utf-8"))

    def test_parquet_import_explains_optional_dependency_when_unavailable(self):
        try:
            import pyarrow  # noqa: F401
        except ImportError:
            with self.assertRaisesRegex(RuntimeError, "\\[parquet\\]"):
                import_parquet(self.conn, self.root / "missing.parquet", "fixture", "fixture")


if __name__ == "__main__":
    unittest.main()
