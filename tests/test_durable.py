"""Persistence, privacy, recovery and retrieval regressions; no live clipboard reads."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if sys.platform == "win32":
    import clip


@unittest.skipUnless(sys.platform == "win32", "Win32 integration")
class DurableCapture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        env = patch.dict(os.environ, {"CLIP_HOME": str(self.root / "clips"),
            "PROMPT_FABRIC": str(self.root / "fabric"), "STARLIGHT_VAULT": str(self.root / "vault")})
        env.start()
        self.addCleanup(env.stop)

    def rows(self, sql, args=()):
        with contextlib.closing(clip.connect()) as conn:
            return list(conn.execute(sql, args))

    def test_retention_does_not_delete_old_records_or_sidecars(self):
        item = clip.ingest("You are a composer. Return a piano prompt.")
        with contextlib.closing(clip.connect()) as conn:
            conn.execute("UPDATE clips SET captured_at='2000-01-01T00:00:00Z'")
            conn.commit()
            self.assertEqual(clip.prune(conn), 0)
            self.assertEqual(conn.execute("SELECT count(*) FROM clips").fetchone()[0], 1)

    def test_long_original_is_retained(self):
        original = "A long creative note. " * 12000
        item = clip.ingest(original)
        self.assertEqual(self.rows("SELECT body FROM clips WHERE id=?", (item["id"],))[0][0], original)

    def test_partial_redaction_does_not_retain_secret_in_html(self):
        secret = "s" + "k-" + "ab" * 16
        item = clip.ingest("Keep this idea " + secret, html_bytes=("<b>" + secret + "</b>").encode())
        record = self.rows("SELECT body,extra_json FROM clips WHERE id=?", (item["id"],))[0]
        self.assertNotIn(secret, record[0])
        self.assertNotIn("html_b64", record[1] or "")

    def test_password_manager_image_is_excluded(self):
        item = clip.ingest(None, app="Bitwarden.exe", title="Bitwarden", has_image=True,
            png_bytes=b"not-a-picture")
        self.assertEqual(item["kind"], "secret")

    def test_short_music_prompt_is_findable(self):
        item = clip.ingest("Cinematic solo piano, 84 BPM, warm strings, no vocals")
        self.assertEqual(item["kind"], "prompt")
        rows = clip.load_board_rows("use:suno after:2000-01-01")
        self.assertEqual([r["id"] for r in rows], [item["id"]])

    def test_duplicate_payload_keeps_each_occurrence(self):
        first = clip.ingest("A note worth keeping")
        second = clip.ingest("A note worth keeping")
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(self.rows("SELECT * FROM clip_occurrences WHERE clip_id=?", (first["id"],))), 2)

    def test_archive_is_reversible_and_searchable(self):
        item = clip.ingest("An idea to revisit about seagrass")
        clip.set_state(item["id"], "archived")
        self.assertEqual(clip.load_board_rows(""), [])
        self.assertEqual(clip.load_board_rows("state:any seagrass")[0]["id"], item["id"])
        clip.set_state(item["id"], "active")
        self.assertEqual(clip.load_board_rows("")[0]["id"], item["id"])

    def test_invalid_date_is_rejected(self):
        clip.ingest("A test note")
        with self.assertRaises(ValueError):
            clip.load_board_rows("after:2026-99-99")

    def test_calendar_day_includes_exact_midnight_but_excludes_next_day(self):
        import clip_store
        item = clip.ingest("A midnight boundary fixture")
        lower = clip_store.local_day("2026-10-31")
        upper = clip_store.local_day("2026-11-01")
        with contextlib.closing(clip.connect()) as conn:
            conn.execute("UPDATE clip_occurrences SET captured_at=?",(lower,))
            conn.commit()
            self.assertEqual(len(clip_store.query_rows(conn,"on:2026-10-31")),1)
            conn.execute("UPDATE clip_occurrences SET captured_at=?",(upper,))
            conn.commit()
            self.assertEqual(clip_store.query_rows(conn,"on:2026-10-31"),[])

    def test_terminal_repair_does_not_overwrite_a_newer_copy(self):
        with patch.object(clip.user32,"OpenClipboard",return_value=True), \
             patch.object(clip.user32,"CloseClipboard"), \
             patch.object(clip.user32,"EmptyClipboard") as empty, \
             patch.object(clip.user32,"GetClipboardSequenceNumber",return_value=101):
            self.assertFalse(clip.set_clipboard_text("stale repair",expected_sequence=100))
            empty.assert_not_called()

    def test_promotion_is_idempotent_and_pins_original(self):
        item = clip.ingest("You are a composer. Write a short piano study.")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(clip.promote(item["id"], "starlight"), 0)
            self.assertEqual(clip.promote(item["id"], "starlight"), 0)
        self.assertEqual(len(list((self.root / "fabric").glob("books/*/entries/*.md"))), 1)
        self.assertEqual(self.rows("SELECT state,pinned FROM clips")[0][:], ("saved", 1))

    def test_sealed_vault_cannot_receive_memory_export(self):
        item = clip.ingest("A note for the working knowledge inbox")
        with patch.dict(os.environ, {"STARLIGHT_VAULT": str(self.root / "private")}):
            with self.assertRaises(ValueError):
                clip.remember_one(item["id"])
        self.assertFalse((self.root / "private").exists())

    def test_backup_restore_keeps_text_events_and_images(self):
        import clip_store
        item = clip.ingest("An irreplaceable note")
        clip.ingest("An irreplaceable note")
        png = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
                            "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082")
        clip.ingest(None,has_image=True,png_bytes=png)
        snap = clip_store.backup(clip.paths()["root"])
        target = self.root / "restored"
        clip_store.restore(snap, target)
        conn = sqlite3.connect(target / "data" / "clips.sqlite")
        self.addCleanup(conn.close)
        self.assertEqual(conn.execute("SELECT body FROM clips").fetchone()[0], "An irreplaceable note")
        self.assertEqual(conn.execute("SELECT count(*) FROM clip_occurrences").fetchone()[0], 3)
        self.assertEqual(conn.execute("SELECT png FROM clip_images").fetchone()[0],png)
        with self.assertRaises(ValueError):
            clip_store.restore(snap, target)

    def test_failed_sidecar_keeps_committed_capture_and_retry_job(self):
        item = clip.ingest("You are a composer. Write a piano prompt.")
        with patch.object(clip, "write_sidecar", side_effect=OSError("disk unavailable")):
            clip.process_pending()
        self.assertIsNotNone(self.rows("SELECT body FROM clips WHERE id=?", (item["id"],))[0][0])
        job = self.rows("SELECT status,attempts FROM clip_jobs WHERE clip_id=?", (item["id"],))[0]
        self.assertEqual(tuple(job), ("pending", 1))

    def test_tampered_backup_is_rejected_before_creating_target(self):
        import clip_store
        clip.ingest("Backup integrity fixture")
        snapshot = clip_store.backup(clip.paths()["root"])
        with (snapshot / "clips.sqlite").open("ab") as file:
            file.write(b"corrupted")
        with self.assertRaises(ValueError):
            clip_store.restore(snapshot,self.root / "rejected")
        self.assertFalse((self.root / "rejected").exists())

    def test_paste_suppression_does_not_hide_a_new_copy(self):
        with patch.object(clip.user32,"GetClipboardSequenceNumber",return_value=100):
            clip.mark_own_paste()
            self.assertTrue(clip.own_paste_pending())
        with patch.object(clip.user32,"GetClipboardSequenceNumber",return_value=101):
            self.assertFalse(clip.own_paste_pending())

    def test_terminal_repair_preserves_pre_transform_original(self):
        original = "A fixture for terminal source preservation"
        snapshot = {"text":original,"app":"windowsterminal.exe","title":"Terminal",
                    "files":[],"has_image":False,"html":None,"png":None,"dib":None}
        with patch.object(clip,"read_clipboard",return_value=snapshot), \
             patch.object(clip,"own_paste_pending",return_value=False), \
             patch.object(clip,"unwrap_terminal_wrap",return_value="repaired fixture"), \
             patch.object(clip,"set_clipboard_text"), patch.object(clip,"mark_own_paste"):
            item = clip.capture_once()
        self.assertEqual(self.rows("SELECT body FROM clips WHERE id=?",(item["id"],))[0][0],original)

    def test_api_authorization_and_full_preview(self):
        from urllib.request import Request,urlopen
        from urllib.error import HTTPError
        old_panel = dict(clip.PANEL)
        clip.PANEL.update({"server":None,"port":0,"token":""})
        clip.start_panel_server()
        server = clip.PANEL["server"]
        def close_server():
            server.shutdown()
            server.server_close()
            clip.PANEL.clear()
            clip.PANEL.update(old_panel)
        self.addCleanup(close_server)
        url = f"http://127.0.0.1:{clip.PANEL['port']}"
        key = clip.PANEL["token"]
        with self.assertRaises(HTTPError) as denied:
            urlopen(url+"/api/items",timeout=3)
        self.assertEqual(denied.exception.code,404)
        with self.assertRaises(HTTPError) as cross_origin:
            urlopen(Request(url+"/api/items?k="+key,headers={"Origin":"https://untrusted.invalid"}),timeout=3)
        self.assertEqual(cross_origin.exception.code,404)
        original = "Full preview fixture " * 600
        item = clip.ingest(original)
        with urlopen(Request(url+f"/api/detail?id={item['id']}",headers={"Authorization":"Bearer "+key}),timeout=3) as response:
            self.assertEqual(json.load(response)["body"],original)
        request = Request(url+"/api/state",data=json.dumps({"id":item["id"],"state":"invalid"}).encode(),
            headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"})
        with self.assertRaises(HTTPError) as invalid:
            urlopen(request,timeout=3)
        self.assertEqual(invalid.exception.code,400)

    def test_music_hints_do_not_claim_submission_or_invent_tempo(self):
        import clip_store
        hint = clip_store.annotation("Warm piano and cinematic strings, no vocals")
        self.assertEqual(hint["submission"],"unknown")
        self.assertNotIn("bpm",hint)

    def test_export_is_private_and_refuses_overwrite(self):
        import clip_store
        clip.ingest("Export this saved idea")
        clip.ingest("s"+"k-"+"ab"*16)
        path = self.root / "export.jsonl"
        with contextlib.closing(clip.connect()) as conn:
            self.assertEqual(clip_store.export_jsonl(conn,path),1)
            with self.assertRaises(ValueError):
                clip_store.export_jsonl(conn,path)
        self.assertNotIn('"kind": "secret"',path.read_text())

    def test_utility_window_uses_an_isolated_browser_profile(self):
        with patch.dict(clip.PANEL,{"port":12345,"token":"fixture-only"}), \
             patch.object(clip,"edge_path",return_value=Path("fixture-edge.exe")), \
             patch.object(clip,"palette_bounds",return_value=(0,0,960,620)), \
             patch.object(clip,"find_board_window",return_value=1), \
             patch.object(clip,"window_class",return_value="Chrome_WidgetWin_1"), \
             patch.object(clip.subprocess,"Popen") as start:
            self.assertEqual(clip.launch_palette_window(),1)
        args = start.call_args.args[0]
        self.assertIn("--user-data-dir="+str(clip.paths()["root"] / "ui-profile"),args)
        self.assertIn("--disable-sync",args)
        self.assertIn("--disable-extensions",args)


if __name__ == "__main__":
    unittest.main()
