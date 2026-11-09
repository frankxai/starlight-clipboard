"""Windows history imports preserve originals and never read the real clipboard."""
import contextlib
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if sys.platform == "win32":
    import clip
    import clip_history as history


@unittest.skipUnless(sys.platform == "win32", "Windows storage fixture")
class HistoryBridge(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, {"CLIP_HOME": temp.name})
        env.start(); self.addCleanup(env.stop)
        self.conn = clip.connect()
        self.addCleanup(self.conn.close)
        clip.init_db(self.conn)
        self.packet = {"schema": history.SCHEMA, "status": "Success", "history_enabled": True,
            "roaming_enabled": True, "available": 1, "skipped": {}, "records": [{"id": "ABC-123",
            "captured_at": "2026-09-01T12:01:02.1234567+00:00", "text": "Cinematic piano and strings, 84 BPM, no vocals.",
            "source_app": "", "protected": False}]}

    def apply(self, packet=None, preview=False):
        return history.apply(self.conn, packet or self.packet, device="test-pc", scrub=clip.redact,
            classify=clip.classify_text, excluded=clip.sensitive_source, preview=preview)

    def count(self, table):
        return self.conn.execute("SELECT count(*) FROM "+table).fetchone()[0]

    def test_source_date_provenance_and_repeat_are_durable(self):
        self.assertEqual(self.apply()["added"], 1)
        row = self.conn.execute("SELECT * FROM clips").fetchone()
        self.assertEqual(row["captured_at"], "2026-09-01T12:01:02.123456Z")
        self.assertEqual(row["body"], self.packet["records"][0]["text"])
        self.assertEqual(row["use_case"], "suno")
        self.assertIn('"origin_device": "unknown"', row["extra_json"])
        self.assertEqual(self.apply()["already_seen"], 1)
        self.assertEqual(self.count("clip_occurrences"), 1)
        self.assertEqual(self.count("clip_jobs"), 1)

    def test_preview_changes_nothing(self):
        self.assertEqual(self.apply(preview=True)["added"], 1)
        self.assertEqual(self.count("clips"), 0)
        self.assertEqual(self.count("clip_history_events"), 0)

    def test_matching_native_event_does_not_double_count_a_copy(self):
        when = "2026-09-01T12:01:02.123456Z"
        with patch.object(clip.clip_store, "now", return_value=when):
            clip.ingest(self.packet["records"][0]["text"], device="test-pc")
        self.assertEqual(self.apply()["matched"], 1)
        self.assertEqual(self.count("clips"), 1)
        self.assertEqual(self.count("clip_occurrences"), 1)

    def test_same_text_on_another_date_retains_a_new_source(self):
        clip.ingest(self.packet["records"][0]["text"], device="test-pc")
        self.assertEqual(self.apply()["added"], 1)
        self.assertEqual(self.count("clips"), 2)

    def test_repeated_native_capture_matches_its_latest_occurrence(self):
        body = self.packet["records"][0]["text"]
        clip.ingest(body, device="test-pc")
        with patch.object(clip.clip_store,"now",return_value="2026-09-01T12:01:02.123456Z"):
            clip.ingest(body, device="test-pc")
        self.assertEqual(self.apply()["matched"],1)
        self.assertEqual(self.count("clips"),1)
        self.assertEqual(self.count("clip_occurrences"),2)

    def test_windows_identity_can_repeat_at_a_new_time_without_replacing_original(self):
        self.apply()
        packet=copy.deepcopy(self.packet)
        packet["records"][0]["captured_at"]="2026-10-01T12:00:00Z"
        self.assertEqual(self.apply(packet)["added"],1)
        self.assertEqual(self.apply(packet)["already_seen"],1)
        self.assertEqual(self.count("clips"),2)
        dates=[row[0] for row in self.conn.execute("SELECT captured_at FROM clips ORDER BY id")]
        self.assertEqual(dates[0],"2026-09-01T12:01:02.123456Z")

    def test_protected_sources_credentials_and_formats_are_skipped(self):
        for change in ({"protected": True}, {"source_app": "bitwarden.exe"},
                       {"text": "api_key="+"x"*40}):
            packet = copy.deepcopy(self.packet)
            packet["records"][0].update(change)
            with self.subTest(change=list(change)):
                self.assertEqual(self.apply(packet)["skipped"], 1)
                self.assertEqual(self.count("clips"), 0)

    def test_conflict_rolls_back_other_entries_in_the_same_batch(self):
        self.apply()
        packet = copy.deepcopy(self.packet)
        new = dict(packet["records"][0], id="new", text="A new idea to retain")
        packet["records"][0]["text"] = "Conflicting source body"
        packet["records"].insert(0, new)
        with self.assertRaises(ValueError): self.apply(packet)
        self.assertEqual(self.count("clips"), 1)
        self.assertEqual(self.count("clip_history_events"), 1)

    def test_denial_does_not_write(self):
        packet = dict(self.packet, status="AccessDenied", records=[])
        self.assertEqual(self.apply(packet)["state"], "AccessDenied")
        self.assertEqual(self.count("clips"), 0)

    def test_invalid_dates_and_bounds_fail_before_writes(self):
        for change in ({"captured_at": "2026-01-01T12:00:00"}, {"protected": "false"}, {"text": "a"*100001}):
            packet = copy.deepcopy(self.packet); packet["records"][0].update(change)
            with self.subTest(change=list(change)), self.assertRaises(ValueError): self.apply(packet)
        self.assertEqual(self.count("clips"), 0)

    def test_version_three_migration_keeps_original_occurrences(self):
        clip.ingest("A retained idea")
        before = self.count("clip_occurrences")
        self.conn.execute("PRAGMA user_version=3"); self.conn.commit()
        clip.init_db(self.conn)
        self.assertEqual(self.count("clip_occurrences"), before)
        self.assertEqual(self.conn.execute("PRAGMA user_version").fetchone()[0], 4)

    def test_enable_and_disable_are_explicit(self):
        self.assertFalse(history.enabled(self.conn))
        history.configure(self.conn, True); self.assertTrue(history.enabled(self.conn))
        history.configure(self.conn, False); self.assertFalse(history.enabled(self.conn))

    def test_background_cycle_defers_without_spawning_under_memory_floor(self):
        history.configure(self.conn,True)
        with patch.object(history,"enough_memory",return_value=False),patch.object(history,"read_native") as native:
            clip.history_cycle()
        native.assert_not_called()
        self.assertEqual(history.status(clip.paths()["root"])["state"],"deferred-memory")
        self.assertEqual(self.count("clips"),0)

    def test_disabling_during_read_prevents_background_import(self):
        history.configure(self.conn,True)
        def read(**kwargs):
            history.configure(self.conn,False)
            return self.packet
        with patch.object(history,"enough_memory",return_value=True),patch.object(history,"read_native",side_effect=read):
            clip.history_cycle()
        self.assertEqual(self.count("clips"),0)
        self.assertFalse(history.enabled(self.conn))

    def test_background_failure_reports_no_private_payload(self):
        history.configure(self.conn,True)
        with patch.object(history,"enough_memory",return_value=True),patch.object(history,"read_native",side_effect=ValueError("private synthetic value")):
            clip.history_cycle()
        result=history.status(clip.paths()["root"])
        self.assertEqual(result["state"],"unavailable")
        self.assertNotIn("private synthetic",str(result))


if __name__ == "__main__": unittest.main()
