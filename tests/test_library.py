"""Music organization and two-store handoff, using isolated originals only."""
import contextlib
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if sys.platform == "win32":
    import clip
    import clip_library as library


@unittest.skipUnless(sys.platform == "win32", "Win32 application fixture")
class MusicLibrary(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {"CLIP_HOME": str(self.root/"a"), "PROMPT_FABRIC": str(self.root/"fabric")})
        self.env.start(); self.addCleanup(self.env.stop)
        self.clip = clip.ingest("Cinematic piano, 84 BPM, intimate felt keys and silver strings. No vocals.", app="suno")

    @contextlib.contextmanager
    def database(self):
        conn = clip.connect()
        try:
            clip.init_db(conn)
            yield conn
        finally:
            conn.close()

    def packet(self):
        with self.database() as conn:
            group = library.save_collection(conn, {"name":"Rain room", "description":"Personal sketches"})
            library.membership(conn, group, self.clip["id"], True)
            library.set_tags(conn, self.clip["id"], ["Cinematic", "Quiet evening"])
            return library.export_bundle(conn)

    def test_version_two_upgrade_does_not_invent_occurrences(self):
        with self.database() as conn:
            before = conn.execute("SELECT count(*) FROM clip_occurrences").fetchone()[0]
            conn.execute("PRAGMA user_version=2"); conn.commit()
            clip.init_db(conn)
            self.assertEqual(conn.execute("SELECT count(*) FROM clip_occurrences").fetchone()[0], before)
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 3)

    def test_tags_smart_and_manual_collections_keep_original(self):
        with self.database() as conn:
            library.set_tags(conn, self.clip["id"], ["Quiet evening", "PIANO"])
            group = library.save_collection(conn, {"name":"My evenings", "mode":"smart", "query":'tag:"quiet evening" use:suno'})
            self.assertEqual(library.selected_ids(conn, group), [self.clip["id"]])
            self.assertEqual(len(clip.clip_store.query_rows(conn, 'tag:piano tag:"quiet evening"')), 1)
            self.assertEqual(len(clip.clip_store.query_rows(conn, 'tag:piano tag:energetic')), 0)
            manual = library.save_collection(conn, {"name":"Next EP"})
            library.membership(conn, manual, self.clip["id"], True)
            library.membership(conn, manual, self.clip["id"], False)
            self.assertEqual(library.selected_ids(conn, manual), [])
            self.assertIn("84 BPM", library.usable(conn, self.clip["id"])["body"])

    def test_user_provenance_wins_and_suggestions_are_explicit(self):
        with self.database() as conn:
            library.set_tags(conn, self.clip["id"], ["piano"])
            library.set_tags(conn, self.clip["id"], ["piano"], "agent", "A suggestion")
            self.assertEqual(library.snapshot(conn, self.clip["id"])["tags"][0]["source"], "user")
            proposed = library.suggestions(conn, self.clip["id"])
            self.assertTrue(any(x["label"]=="instrumental" for x in proposed))
            self.assertTrue(all(x["source"]=="local-rule" for x in proposed))
            self.assertEqual(len(library.snapshot(conn, self.clip["id"])["tags"]), 1)

    def test_stale_collection_edit_and_recursive_query_refused(self):
        with self.database() as conn:
            group = library.save_collection(conn, {"name":"First"})
            library.save_collection(conn, {"id":group, "version":1, "name":"Second"})
            with self.assertRaises(ValueError):
                library.save_collection(conn, {"id":group, "version":1, "name":"Stale"})
            with self.assertRaises(ValueError):
                library.save_collection(conn, {"name":"Cycle", "mode":"smart", "query":"vibe:"+group})

    def test_two_store_handoff_is_idempotent_and_retains_source_date(self):
        packet = self.packet()
        with patch.dict(os.environ, {"CLIP_HOME":str(self.root/"b")}):
            with self.database() as conn:
                first = library.import_bundle(conn, packet, clip.validate_library_source)
                again = library.import_bundle(conn, packet, clip.validate_library_source)
                self.assertEqual(first["added"], 1); self.assertEqual(again["reused"], 1)
                row = conn.execute("SELECT * FROM clips").fetchone()
                self.assertEqual(row["captured_at"], packet["records"][0]["captured_at"])
                self.assertEqual(row["uid"], packet["records"][0]["uid"])
                self.assertEqual(len(library.snapshot(conn, row["id"])["tags"]), 2)
                exported = library.export_bundle(conn)
                self.assertEqual(exported["records"], packet["records"])

    def test_modified_source_rolls_back_entire_import(self):
        packet = self.packet()
        with self.database() as conn:
            packet["records"][0]["body"] += " Changed"
            before = conn.execute("SELECT count(*) FROM clips").fetchone()[0]
            with self.assertRaises(ValueError):
                library.import_bundle(conn, packet, clip.validate_library_source)
            self.assertEqual(conn.execute("SELECT count(*) FROM clips").fetchone()[0], before)

    def test_concurrent_collection_definitions_remain_as_variants(self):
        packet = self.packet()
        with self.database() as conn:
            target = packet["collections"][0]
            conn.execute("UPDATE library_collections SET description='A local edit' WHERE id=?", (target["id"],)); conn.commit()
            result = library.import_bundle(conn, packet, clip.validate_library_source)
            count = conn.execute("SELECT count(*) FROM library_collections").fetchone()[0]
            library.import_bundle(conn, packet, clip.validate_library_source)
            self.assertEqual(result["collection_variants"], 1)
            self.assertEqual(conn.execute("SELECT count(*) FROM library_collections").fetchone()[0], count)
            self.assertEqual(conn.execute("SELECT description FROM library_collections WHERE id=?", (target["id"],)).fetchone()[0], "A local edit")

    def test_malformed_or_sensitive_handoff_writes_nothing(self):
        original = self.packet()
        for mutation in ("foreign-member", "unknown-field", "secret", "timezone", "duplicate", "bad-kind", "duplicate-tag"):
            packet = copy.deepcopy(original)
            if mutation=="foreign-member": packet["members"][0]["uid"] = []
            if mutation=="unknown-field": packet["records"][0]["path"] = "../outside"
            if mutation=="secret": packet["records"][0]["source_app"] = "Bitwarden.exe"
            if mutation=="timezone": packet["records"][0]["captured_at"] = "2026-10-31T12:00:00"
            if mutation=="duplicate": packet["records"].append(packet["records"][0])
            if mutation=="bad-kind": packet["records"][0]["kind"] = []
            if mutation=="duplicate-tag": packet["tags"].append(packet["tags"][0])
            with patch.dict(os.environ, {"CLIP_HOME":str(self.root/mutation)}):
                with self.database() as conn:
                    with self.assertRaises(ValueError): library.import_bundle(conn, packet, clip.validate_library_source)
                    self.assertEqual(conn.execute("SELECT count(*) FROM clips").fetchone()[0], 0)

    def test_agent_tag_accumulation_keeps_portable_bounds(self):
        with self.database() as conn:
            library.set_tags(conn,self.clip["id"],["tag-"+str(i) for i in range(20)])
            with self.assertRaises(ValueError): library.set_tags(conn,self.clip["id"],["extra"],"agent","A suggestion")
            self.assertEqual(len(library.snapshot(conn,self.clip["id"])["tags"]),20)

    def test_backup_restore_contains_collections_and_tags(self):
        self.packet()
        snapshot = clip.clip_store.backup(self.root/"a")
        restored = clip.clip_store.restore(snapshot, self.root/"restore")
        with patch.dict(os.environ, {"CLIP_HOME":str(restored)}):
            with self.database() as conn:
                self.assertTrue(any(x["name"]=="Rain room" for x in library.snapshot(conn)["collections"]))
                self.assertEqual(len(library.snapshot(conn, self.clip["id"])["tags"]), 2)

    def test_open_success_still_places_and_focuses_its_window(self):
        old = dict(clip.PANEL)
        clip.PANEL["hwnd"] = 123
        try:
            with patch.object(clip,"start_panel_server"), patch.object(clip.user32,"IsWindow",return_value=True), \
                 patch.object(clip,"remember_target"), patch.object(clip,"place_palette") as place, \
                 patch.object(clip,"focus_window") as focus:
                self.assertTrue(clip.show_palette())
                place.assert_called_once_with(123,True)
                focus.assert_called_once_with(123)
        finally:
            clip.PANEL.clear();clip.PANEL.update(old)

    def test_preview_and_authenticated_api_do_not_apply_without_import(self):
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError
        packet = self.packet()
        with patch.dict(os.environ, {"CLIP_HOME":str(self.root/"api-target")}):
            old_panel = dict(clip.PANEL)
            clip.PANEL.update({"server":None,"port":0,"token":""})
            clip.start_panel_server()
            server = clip.PANEL["server"]
            try:
                base = f"http://127.0.0.1:{clip.PANEL['port']}"
                headers = {"Authorization":"Bearer "+clip.PANEL["token"],"Content-Type":"application/json"}
                with self.assertRaises(HTTPError): urlopen(base+"/api/library",timeout=3)
                with self.assertRaises(HTTPError): urlopen(base+"/library.js",timeout=3)
                with urlopen(Request(base+"/library.js",headers=headers),timeout=3) as response:
                    self.assertIn(b"postLibrary",response.read())
                body = json.dumps({"bundle":packet}).encode()
                with urlopen(Request(base+"/api/library/preview",data=body,headers=headers),timeout=3) as response:
                    self.assertEqual(json.load(response)["records"],1)
                with self.database() as conn:
                    self.assertEqual(conn.execute("SELECT count(*) FROM clips").fetchone()[0],0)
                with urlopen(Request(base+"/api/library/import",data=body,headers=headers),timeout=3) as response:
                    self.assertEqual(json.load(response)["added"],1)
                with urlopen(Request(base+"/api/library/export",headers=headers),timeout=3) as response:
                    self.assertEqual(len(json.load(response)["records"]),1)
                with self.assertRaises(HTTPError) as rejected:
                    urlopen(Request(base+"/api/library/preview",data=body,headers={**headers,"Origin":"https://foreign.invalid"}),timeout=3)
                self.assertEqual(rejected.exception.code,404)
                with patch.object(clip,"show_palette",return_value=False):
                    with self.assertRaises(HTTPError) as failed_open:
                        urlopen(Request(base+"/api/raise",headers=headers),timeout=3)
                    self.assertEqual(failed_open.exception.code,503)
                with patch.object(clip,"show_palette",return_value=True):
                    with urlopen(Request(base+"/api/raise?view=suno",headers=headers),timeout=3) as response:
                        self.assertTrue(json.load(response)["ok"])
                    with urlopen(Request(base+"/api/navigation",headers=headers),timeout=3) as response:
                        self.assertEqual(json.load(response)["navigation"]["view"],"suno")
                with urlopen(Request(base+"/",headers=headers),timeout=3) as response:
                    self.assertIn(clip.PANEL["window_title"].encode(),response.read())
            finally:
                server.shutdown();server.server_close();clip.PANEL.clear();clip.PANEL.update(old_panel)


if __name__ == "__main__":
    unittest.main()
