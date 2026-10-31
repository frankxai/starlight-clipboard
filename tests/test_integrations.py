"""On-demand integrations: no real memory, credentials, network or backup writes."""
import contextlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import clip_integrations as integration
import clip_store


class FakePlane:
    reads = {}
    writes = 0

    def __init__(self, settings):
        self.settings = settings

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def call(self, name, args):
        if name == "memory_stats":
            return json.dumps({"vaultRoot": self.settings["vault"], "tenant": "frank"})
        if name == "vault_read":
            return self.reads.get(args["memory_id"], "No atom with id.")
        return "No matching memories."


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.row = {"uid": "store:123", "id": 123, "body": "A source-linked idea to retain.",
                    "kind": "text", "captured_at": "2026-10-31T12:00:00Z", "source_app": "fixture"}
        self.settings = {"memory": {"enabled": True, "vault": str(self.root/"vault")}}
        FakePlane.reads = {}
        FakePlane.writes = 0

    def memory(self, writer):
        return integration.remember(self.root, self.row, self.settings,
                                    plane_factory=FakePlane, writer=writer)

    def test_verified_memory_write_is_idempotent(self):
        def writer(settings, summary, content):
            FakePlane.writes += 1
            FakePlane.reads["clipboard-source-abc"] = content
            return "Remembered [clipboard-source-abc] -> atoms/clipboard-source-abc.md"
        first = self.memory(writer)
        second = self.memory(writer)
        self.assertEqual(first["state"], "recall_verified")
        self.assertEqual(second["memory_id"], first["memory_id"])
        self.assertEqual(FakePlane.writes, 1)

    def test_unknown_write_outcome_never_retries_blindly(self):
        def writer(*args):
            raise TimeoutError("unknown outcome")
        with self.assertRaisesRegex(ValueError, "unknown|reconcile"):
            self.memory(writer)
        with self.assertRaisesRegex(ValueError, "unknown|reconcile"):
            self.memory(lambda *args: self.fail("Must not write again"))

    def test_read_failure_preserves_confirmed_write_receipt(self):
        result = self.memory(lambda *args: "Remembered [clipboard-id] -> atoms/clipboard-id.md")
        self.assertEqual(result["state"], "stored_pending_recall")
        again = self.memory(lambda *args: self.fail("Must reuse receipt"))
        self.assertEqual(again["memory_id"], "clipboard-id")

    def test_mismatched_content_cannot_certify_recall(self):
        FakePlane.reads["clipboard-id"] = "clipboard_uid: some-other-record"
        result = self.memory(lambda *args: "Remembered [clipboard-id] -> atoms/clipboard-id.md")
        self.assertEqual(result["state"], "stored_pending_recall")

    def test_secrets_and_sealed_vaults_are_rejected_before_writer(self):
        self.row["kind"] = "secret"
        with self.assertRaises(ValueError):
            self.memory(lambda *args: self.fail("secret writer"))
        self.row["kind"] = "text"
        self.settings["memory"]["vault"] = str(self.root/"private")
        with self.assertRaises(ValueError):
            self.memory(lambda *args: self.fail("sealed writer"))

    def test_read_transport_refuses_remote_and_redirects(self):
        for url in ["https://example.com/mcp", "http://localhost:7317/mcp", "http://127.0.0.1@evil/mcp"]:
            with self.assertRaises(ValueError):
                integration.Plane({"plane_url": url})
        with self.assertRaises(ValueError):
            integration.NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil/")

    def test_sse_parser_matches_request_and_handles_notifications(self):
        import io
        response = io.BytesIO(b'event: message\ndata: {"jsonrpc":"2.0","method":"notice"}\n\ndata: {"id":7,"result":{"ok":true}}\n\n')
        self.assertEqual(integration.read_response(response, 7, True), {"ok": True})

    def test_encrypted_backup_uses_only_existing_repository_and_never_prunes(self):
        snapshot = self.root/"snapshot"
        snapshot.mkdir()
        (snapshot/"manifest.json").write_text('{}')
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            if "cat" in command:
                out = '{"version":2}'
            else:
                out = '{"message_type":"summary","snapshot_id":"abcdef1234567890"}\n'
            return subprocess.CompletedProcess(command, 0, out, '')
        settings = {"backup": {"enabled": True, "executable": "restic.exe",
                    "repository": str(self.root/"restic"), "password_file": str(self.root/"key")}}
        with patch.object(integration, "load_settings", return_value=settings), \
             patch.object(integration, "storage_admitted"), \
             patch.object(integration.subprocess, "run", side_effect=run):
            result = integration.encrypted_backup(self.root, snapshot)
        self.assertEqual(result["snapshot_id"], "abcdef1234567890")
        self.assertEqual(result["state"], "encrypted_local")
        self.assertFalse(any(word in str(calls) for word in ["prune", "forget", "init"]))

    def test_backup_failure_does_not_claim_success(self):
        settings = {"backup": {"enabled": True, "executable": "restic.exe",
                    "repository": str(self.root/"restic"), "password_file": str(self.root/"key")}}
        with patch.object(integration, "load_settings", return_value=settings), \
             patch.object(integration, "storage_admitted"), \
             patch.object(integration.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, '', 'private error')):
            with self.assertRaisesRegex(ValueError, "backup|repository"):
                integration.encrypted_backup(self.root, self.root/"snapshot")
        self.assertFalse((self.root/"data/last-encrypted-backup.json").exists())

    def test_recovery_refuses_existing_destination_before_restic(self):
        with patch.object(integration.subprocess, "run") as run:
            with self.assertRaises(ValueError):
                integration.recover_encrypted(self.root, "abcdef1234567890", self.root)
            run.assert_not_called()

    def test_recovery_restores_leaf_subtree_without_windows_ancestor_acls(self):
        cfg = {"backup": {"enabled": True}}
        calls = []
        def run(settings, command, **kwargs):
            calls.append(command)
            if command[:2] == ["cat", "snapshot"]:
                return json.dumps({"tags":["starlight-clipboard"], "paths":[r"C:\Users\frank\snap"]})
            if command[0] == "stats":
                return '{"total_size":1024}'
            temporary = Path(command[command.index("--target")+1])
            (temporary/"manifest.json").write_text('{}')
            (temporary/"clips.sqlite").write_bytes(b'fixture')
            return ''
        with patch.object(integration,"load_settings",return_value=cfg), \
             patch.object(integration,"storage_admitted"), \
             patch.object(integration,"restic_run",side_effect=run), \
             patch.object(clip_store,"restore",return_value=self.root/"restored"):
            integration.recover_encrypted(self.root,"abcdef1234567890",self.root/"restored")
        self.assertEqual(calls[-1][1], "abcdef1234567890:/C/Users/frank/snap")
        self.assertIn("--verify", calls[-1])

    def test_markers_without_source_body_cannot_verify_memory(self):
        def writer(settings, summary, content):
            FakePlane.reads["clipboard-id"] = content.split("\n\n", 1)[0]
            return "Remembered [clipboard-id] -> atoms/clipboard-id.md"
        self.assertEqual(self.memory(writer)["state"], "stored_pending_recall")

    def test_reader_tenant_mismatch_prevents_write(self):
        class OtherReader(FakePlane):
            def call(inner, name, args):
                if name == "memory_stats":
                    return json.dumps({"vaultRoot":self.settings["memory"]["vault"],"tenant":"another-client"})
                return super().call(name,args)
        with self.assertRaisesRegex(ValueError,"identity"):
            integration.remember(self.root,self.row,self.settings,plane_factory=OtherReader,
                                 writer=lambda *args: self.fail("Tenant mismatch must stop writing"))

    def test_daily_backup_due_is_bounded_and_visible(self):
        self.assertTrue(integration.backup_due(self.root, now=1000000))
        (self.root/"data").mkdir()
        (self.root/"data/backup-cycle.json").write_text(json.dumps({"attempted_at": 999950, "state": "failed"}))
        self.assertFalse(integration.backup_due(self.root, now=1000000))

    def test_backup_preserves_an_existing_writer_lease(self):
        (self.root/"data").mkdir()
        lease = self.root/"data/encrypted-backup.lock"
        lease.write_text('existing owner')
        with patch.object(integration, "_encrypted_backup") as backup:
            with self.assertRaisesRegex(ValueError, "lease"):
                integration.encrypted_backup(self.root)
            backup.assert_not_called()
        self.assertEqual(lease.read_text(), 'existing owner')

    def test_failed_backup_cycle_records_failure_and_keeps_capture_database(self):
        (self.root/"data").mkdir()
        database = self.root/"data/clips.sqlite"
        database.write_bytes(b'preserved source')
        with patch.object(integration,"storage_admitted",side_effect=ValueError('disk floor')):
            result = integration.backup_cycle(self.root)
        self.assertEqual(result["state"],"failed")
        self.assertEqual(database.read_bytes(),b'preserved source')
        self.assertFalse(integration.backup_due(self.root))

    def test_memory_limit_is_explicit_without_truncating_original(self):
        self.row['body'] = 'a' * 12001
        with self.assertRaisesRegex(ValueError,'limit'):
            self.memory(lambda *args: self.fail('overlong writer'))
        self.assertEqual(len(self.row['body']),12001)


if __name__ == "__main__":
    unittest.main()
