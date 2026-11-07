#!/usr/bin/env python3
"""Gate orchestration tests only: fake Tina + simulated watcher, NOT real E2E.

The fixture follows mount-devil/tina/__generated__/schema.gql (settings,
updateSettings, SettingsMutation.siteName). No real site is contacted.
"""
from __future__ import annotations

import html
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


SCRIPT = Path(__file__).resolve().parent / "phases/cms-roundtrip.py"
PASSWORD = "fixture-password-only"
ORIGINAL = "Private original & <staging>"
COOKIE = "fixture-session-only"
SCHEMA = {"collections": [{
    "name": "settings", "path": "src/content/settings", "format": "json",
    "fields": [{"name": "siteName", "type": "string", "required": True}],
}]}


class FakeTina:
    """HTTP contract fixture; homepage lag simulates a completed rebuild."""

    def __init__(self, project, mode="normal", settings_filename="global.json"):
        self.project = project
        self.relative_path = settings_filename
        self.path = project / "src/content/settings" / settings_filename
        self.mode = mode
        self.mutations = []
        self.requests = []
        self.original = json.loads(self.path.read_text())["siteName"]
        self.visible = self.original
        self.pending = None
        self.home_polls = 0
        self.public_after_write = 0
        self.release_delayed = threading.Event()
        self.delayed_started = threading.Event()
        self.delayed_done = threading.Event()
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def reply(self, status, value, content_type="application/json", headers=None, slow=False):
                raw = (json.dumps(value) if content_type == "application/json" else value).encode()
                if fixture.mode == "slow_headers" and self.path == "/api/tina/login":
                    header = (f"HTTP/1.0 {status} OK\r\nContent-Length: {len(raw)}\r\n"
                              "Content-Type: application/json\r\n\r\n").encode()
                    try:
                        for byte in header:
                            self.wfile.write(bytes([byte]))
                            self.wfile.flush()
                            time.sleep(0.015)
                        self.wfile.write(raw)
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    return
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(raw)))
                for name, text in (headers or {}).items():
                    self.send_header(name, text)
                self.end_headers()
                try:
                    if slow:
                        for byte in raw:
                            self.wfile.write(bytes([byte]))
                            self.wfile.flush()
                            time.sleep(0.025)
                    else:
                        self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # Bounded polling/crash tests intentionally abandon sockets.

            def do_GET(self):
                fixture.requests.append(("GET", self.path))
                if self.path == "/api/tina/auth-check":
                    ok = self.headers.get("Cookie") == f"tina_admin_session={COOKIE}"
                    self.reply(200 if ok else 401, {"authenticated": ok})
                elif self.path.startswith("/"):
                    if fixture.mutations:
                        fixture.public_after_write += 1
                    if fixture.pending is not None:
                        fixture.home_polls += 1
                        if fixture.home_polls >= 2:
                            fixture.visible = fixture.pending
                            fixture.pending = None
                    hidden = " hidden" if fixture.mode == "hidden_live" and fixture.visible != fixture.original else ""
                    if fixture.mode == "script_only" and fixture.visible != fixture.original:
                        page = f"<header>{html.escape(fixture.original)}</header><script>{fixture.visible}</script>"
                    else:
                        page = f"<header><a{hidden}>{html.escape(fixture.visible)}</a></header>"
                    self.reply(200, f"<!doctype html><html><body>{page}</body></html>", "text/html",
                               slow=fixture.mode == "slow_home" and bool(fixture.mutations))

            def do_POST(self):
                fixture.requests.append(("POST", self.path))
                value = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.headers.get("Origin") != fixture.url:
                    self.reply(403, {"error": "wrong origin"})
                    return
                if self.path == "/api/tina/login":
                    if fixture.mode == "redirect_login":
                        self.reply(307, {}, headers={"Location": fixture.url + "/credential-sink"})
                        return
                    if value != {"password": PASSWORD} or fixture.mode == "auth_fail":
                        self.reply(401, {"error": PASSWORD})
                        return
                    headers = {} if fixture.mode == "no_cookie" else {
                        "Set-Cookie": f"tina_admin_session={COOKIE}; HttpOnly; Path=/; SameSite=Strict"
                    }
                    self.reply(200, {"success": True}, headers=headers, slow=fixture.mode == "slow_login")
                    return
                if self.path != "/api/tina/gql":
                    self.reply(404, {})
                    return
                if self.headers.get("Cookie") != f"tina_admin_session={COOKIE}":
                    self.reply(401, {"error": "missing session"})
                    return
                if set(value) != {"query", "variables", "operationName"}:
                    self.reply(400, {"error": "expected GraphQL envelope"})
                    return
                variables = value["variables"]
                if variables.get("relativePath") != fixture.relative_path:
                    self.reply(400, {"error": "wrong relativePath"})
                    return
                if value["operationName"] == "CmsRoundtripRead":
                    if "settings(relativePath: $relativePath)" not in value["query"]:
                        self.reply(400, {})
                        return
                    name = "wrong" if fixture.mode == "query_mismatch" else json.loads(fixture.path.read_text())["siteName"]
                    self.reply(200, {"data": {"settings": {"siteName": name}}})
                    return
                if (value["operationName"] != "CmsRoundtripWrite"
                        or "updateSettings(relativePath: $relativePath, params: $params)" not in value["query"]
                        or "SettingsMutation!" not in value["query"]
                        or set(variables.get("params", {})) != {"siteName"}):
                    self.reply(400, {"error": "wrong mutation contract"})
                    return
                name = variables["params"]["siteName"]
                fixture.mutations.append(name)
                restoring = name == fixture.original
                if not restoring and fixture.mode == "delayed_commit":
                    fixture.delayed_started.set()
                    fixture.release_delayed.wait(4)
                if restoring and fixture.mode == "restore_fail":
                    self.reply(503, {"error": ORIGINAL + PASSWORD + COOKIE})
                    return
                document = json.loads(fixture.path.read_text())
                document["siteName"] = name
                if not restoring and fixture.mode == "mutate_other_field":
                    document["tagline"] = "unexpected backend damage"
                if fixture.mode != "no_persist":
                    fixture.path.write_text(json.dumps(document))
                if fixture.mode != "stale_live" and not (restoring and fixture.mode == "restore_stale"):
                    fixture.pending = name
                    fixture.home_polls = 0
                if not restoring and fixture.mode == "partial_failure":
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    return
                if not restoring and fixture.mode == "graphql_error_after_write":
                    self.reply(200, {"errors": [{"message": ORIGINAL + PASSWORD + COOKIE}]})
                    return
                if not restoring and fixture.mode == "delayed_commit":
                    fixture.delayed_done.set()
                self.reply(200, {"data": {"updateSettings": {"siteName": name}}},
                           slow=(fixture.mode == "slow_save" and not restoring)
                           or (fixture.mode == "slow_restore" and restoring))

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.release_delayed.set()
        if self.delayed_started.is_set():
            self.delayed_done.wait(3)
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


class CmsRoundtripOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.settings = self.project / "src/content/settings/global.json"
        self.settings.parent.mkdir(parents=True)
        self.document = {"siteName": ORIGINAL, "tagline": "untouched", "nav": [{"href": "/"}]}
        self.settings.write_text(json.dumps(self.document))
        self.schema = self.project / "tina/__generated__/_schema.json"
        self.schema.parent.mkdir(parents=True)
        self.schema.write_text(json.dumps(SCHEMA))
        self.attestation = self.project / "pipeline/cms-staging.json"
        self.attestation.parent.mkdir()
        self.revision = self.fingerprint()

    def fingerprint(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--project-root", str(self.project),
                                 "--print-source-revision"], capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 0, "read-only fingerprint mode must succeed")
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)["source_revision"]

    def gate_module(self):
        spec = importlib.util.spec_from_file_location("cms_roundtrip_under_test", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def attest(self, fixture):
        self.attestation.write_text(json.dumps({
            "schema_version": "astro-static-cms-staging/v1",
            "environment": "staging", "site_url": fixture.url,
            "authorized_by_operator": True,
            "source_revision": self.revision,
        }))

    def run_gate(self, fixture, extra=(), password=PASSWORD, attest=True):
        if attest:
            self.attest(fixture)
        args = [sys.executable, str(SCRIPT), "--environment", "staging", "--allow-write",
                "--project-root", str(self.project), "--site-url", fixture.url,
                "--timeout-seconds", "0.25", "--poll-interval", "0.01", "--request-timeout", "0.2"]
        env = dict(os.environ)
        env.pop("TINA_ADMIN_PASSWORD", None)
        if password is not None:
            env["TINA_ADMIN_PASSWORD"] = password
        proc = subprocess.run(args + list(extra), env=env, capture_output=True, text=True, timeout=6)
        self.assertTrue(proc.stdout.strip().startswith("{"), "gate must emit a structured JSON report")
        self.assertEqual(proc.stderr, "")
        self.assertNotIn(ORIGINAL, proc.stdout)
        self.assertNotIn(PASSWORD, proc.stdout)
        self.assertNotIn(COOKIE, proc.stdout)
        return proc.returncode, json.loads(proc.stdout)

    def assert_restored(self, fixture):
        self.assertGreaterEqual(len(fixture.mutations), 2)
        self.assertEqual(fixture.mutations[-1], ORIGINAL)
        self.assertEqual(json.loads(self.settings.read_text()), self.document)

    def test_happy_path_persists_waits_for_render_and_restores(self):
        with FakeTina(self.project) as f:
            code, report = self.run_gate(f)
            self.assertEqual((code, report["status"]), (0, "PASS"))
            self.assert_restored(f)
            self.assertEqual(f.visible, ORIGINAL)
            for phase in ("preflight", "authenticate", "baseline", "backup", "save", "persist", "live", "restore", "restore_persist", "restore_live"):
                self.assertEqual(report["phases"][phase]["status"], "PASS", phase)
            self.assertEqual(report["evidence"]["rebuild_proof"], "persisted_settings_and_changed_live_header_html")
            self.assertNotEqual(report["evidence"]["original_sha256"], report["evidence"]["saved_sha256"])
            self.assertEqual(report["evidence"]["original_sha256"], report["evidence"]["restored_sha256"])
            self.assertEqual(report["source_revision"], self.revision)
            self.assertEqual(report["origin"], f.url)
            self.assertIs(report["operator_authorized"], True)
            report_path = self.project / "pipeline/cms-roundtrip-report.json"
            self.assertEqual(json.loads(report_path.read_text()), report)
            self.assertEqual(stat.S_IMODE(report_path.stat().st_mode), 0o600)
            self.assertNotIn(ORIGINAL, report_path.read_text())
            self.assertNotIn(PASSWORD, report_path.read_text())
            self.assertFalse(list((self.project / "pipeline").glob(".cms-roundtrip-*")))

    def test_stale_homepage_is_not_a_successful_rebuild(self):
        with FakeTina(self.project, "stale_live") as f:
            code, report = self.run_gate(f)
            self.assertEqual((code, report["status"]), (1, "FAIL"))
            self.assertEqual(report["phases"]["live"]["status"], "FAIL")
            self.assert_restored(f)

    def test_canonical_site_document_roundtrip_uses_selected_graphql_path(self):
        site = self.settings.with_name("site.json")
        self.settings.rename(site)
        self.settings = site
        self.revision = self.fingerprint()
        with FakeTina(self.project, settings_filename="site.json") as f:
            code, report = self.run_gate(f)
            self.assertEqual((code, report["status"]), (0, "PASS"))
            self.assertEqual(report["evidence"]["settings_path"], "src/content/settings/site.json")
            self.assert_restored(f)
            self.assertEqual(f.visible, ORIGINAL)
            self.assertFalse(site.with_name("global.json").exists())

    def test_canonical_site_document_recovery_records_selected_filename(self):
        site = self.settings.with_name("site.json")
        self.settings.rename(site)
        self.settings = site
        self.revision = self.fingerprint()
        with FakeTina(self.project, "restore_fail", settings_filename="site.json") as f:
            code, report = self.run_gate(f)
            self.assertEqual((code, report["status"]), (3, "MANUAL_REVIEW"))
            recovery = json.loads(Path(report["recovery_path"]).read_text())
            self.assertEqual(recovery["settings_path"], "src/content/settings/site.json")
            self.assertEqual(recovery["relative_path"], "site.json")
            self.assertEqual(report["evidence"]["settings_path"], recovery["settings_path"])
            self.assertFalse(site.with_name("global.json").exists())

    def test_ambiguous_or_missing_standard_settings_documents_refuse_before_network(self):
        for case in ("ambiguous", "missing"):
            self.settings.write_text(json.dumps(self.document))
            site = self.settings.with_name("site.json")
            if site.exists():
                site.unlink()
            with self.subTest(case=case), FakeTina(self.project) as f:
                if case == "ambiguous":
                    site.write_text(json.dumps({**self.document, "siteName": "another original"}))
                else:
                    self.settings.unlink()
                before = {p: p.read_bytes() for p in self.settings.parent.glob("*.json")}
                code, report = self.run_gate(f)
                self.assertEqual((code, report["status"]), (2, "UNVERIFIED"))
                self.assertEqual(report["phases"]["preflight"]["code"],
                                 "SETTINGS_DOCUMENT_AMBIGUOUS" if case == "ambiguous" else "SETTINGS_DOCUMENT_MISSING")
                self.assertEqual(f.requests, [])
                self.assertEqual(f.mutations, [])
                self.assertEqual({p: p.read_bytes() for p in self.settings.parent.glob("*.json")}, before)

    def test_query_cache_without_file_persistence_is_not_accepted(self):
        with FakeTina(self.project, "no_persist") as f:
            code, report = self.run_gate(f)
            self.assertEqual((code, report["status"]), (1, "FAIL"))
            self.assertEqual(report["phases"]["persist"]["status"], "FAIL")
            self.assert_restored(f)

    def test_network_failure_after_mutation_still_rolls_back(self):
        with FakeTina(self.project, "partial_failure") as f:
            code, report = self.run_gate(f)
            self.assertEqual((code, report["status"]), (3, "MANUAL_REVIEW"))
            self.assert_restored(f)
            self.assertEqual(report["mutation_outcome"], "INDETERMINATE")
            self.assertTrue(Path(report["recovery_path"]).is_file())

    def test_stale_escaped_marker_does_not_prove_restoration_of_name_staging(self):
        self.document["siteName"] = "staging"
        self.settings.write_text(json.dumps(self.document))
        self.revision = self.fingerprint()
        with FakeTina(self.project, "restore_stale") as f:
            code, report = self.run_gate(f)
            self.assertEqual((code, report["status"]), (3, "MANUAL_REVIEW"))
            self.assertEqual(report["phases"]["restore_persist"]["status"], "PASS")
            self.assertEqual(report["phases"]["restore_live"]["status"], "FAIL")
            self.assertIn("&", f.visible)
            self.assertTrue(Path(report["recovery_path"]).is_file())

    def test_header_brand_match_is_complete_but_allows_nested_text_and_navigation(self):
        module = self.gate_module()
        self.assertFalse(module.visible_header(
            '<header><a>CMS acceptance unique &amp; staging</a><nav>Home</nav></header>', "staging"))
        self.assertTrue(module.visible_header(
            '<header><a class="brand">My <span>staging</span></a><nav><a>Home</a></nav></header>',
            "My staging"))

    def test_delayed_save_commit_after_verified_rollback_is_always_manual_review(self):
        with FakeTina(self.project, "delayed_commit") as f:
            code, report = self.run_gate(f, extra=("--request-timeout", "0.1"))
            self.assertTrue(f.delayed_started.is_set())
            self.assertEqual(report["phases"]["restore_persist"]["status"], "PASS")
            self.assertEqual(report["phases"]["restore_live"]["status"], "PASS")
            self.assertEqual(json.loads(self.settings.read_text()), self.document)
            # Commit only AFTER the gate returned and its rollback readbacks looked clean.
            f.release_delayed.set()
            self.assertTrue(f.delayed_done.wait(2))
            self.assertNotEqual(json.loads(self.settings.read_text())["siteName"], ORIGINAL)
            self.assertEqual((code, report["status"]), (3, "MANUAL_REVIEW"))
            self.assertEqual(report["mutation_outcome"], "INDETERMINATE")
            self.assertEqual(report["recovery_reason"], "MUTATION_COMPLETION_UNCONFIRMED")
            self.assertTrue(Path(report["recovery_path"]).is_file())

    def test_slow_drip_login_body_obeys_total_request_deadline(self):
        with FakeTina(self.project, "slow_login") as f:
            start = time.monotonic()
            code, report = self.run_gate(f, extra=("--request-timeout", "0.1"))
            self.assertLess(time.monotonic() - start, 0.9)
            self.assertEqual((code, report["status"]), (1, "FAIL"))
            self.assertEqual(f.mutations, [])
            self.assertEqual(report["phases"]["authenticate"]["code"], "REQUEST_DEADLINE_EXCEEDED")

    def test_slow_drip_headers_obey_total_request_deadline(self):
        with FakeTina(self.project, "slow_headers") as f:
            start = time.monotonic()
            code, report = self.run_gate(f, extra=("--request-timeout", "0.1"))
            self.assertLess(time.monotonic() - start, 0.9)
            self.assertEqual((code, report["status"]), (1, "FAIL"))
            self.assertEqual(f.mutations, [])
            self.assertEqual(report["phases"]["authenticate"]["code"], "REQUEST_DEADLINE_EXCEEDED")

    def test_slow_drip_save_body_is_bounded_and_indeterminate(self):
        with FakeTina(self.project, "slow_save") as f:
            start = time.monotonic()
            code, report = self.run_gate(f, extra=("--request-timeout", "0.1"))
            self.assertLess(time.monotonic() - start, 1.0)
            self.assertEqual((code, report["status"]), (3, "MANUAL_REVIEW"))
            self.assertEqual(report["phases"]["save"]["code"], "REQUEST_DEADLINE_EXCEEDED")
            self.assertEqual(report["mutation_outcome"], "INDETERMINATE")
            self.assertTrue(Path(report["recovery_path"]).is_file())
            self.assert_restored(f)

    def test_slow_drip_restore_body_is_bounded_and_keeps_backup(self):
        with FakeTina(self.project, "slow_restore") as f:
            start = time.monotonic()
            code, report = self.run_gate(f, extra=("--request-timeout", "0.1"))
            self.assertLess(time.monotonic() - start, 1.0)
            self.assertEqual((code, report["status"]), (3, "MANUAL_REVIEW"))
            self.assertEqual(report["phases"]["restore"]["code"], "REQUEST_DEADLINE_EXCEEDED")
            self.assertEqual(report["mutation_outcome"], "INDETERMINATE")
            self.assertTrue(Path(report["recovery_path"]).is_file())
            self.assert_restored(f)

    def test_slow_drip_homepage_cannot_succeed_after_poll_deadline(self):
        with FakeTina(self.project, "slow_home") as f:
            start = time.monotonic()
            code, report = self.run_gate(f, extra=("--request-timeout", "0.1"))
            self.assertLess(time.monotonic() - start, 1.3)
            self.assertEqual((code, report["status"]), (3, "MANUAL_REVIEW"))
            self.assertEqual(report["phases"]["live"]["status"], "FAIL")
            self.assertEqual(report["phases"]["restore_live"]["status"], "FAIL")
            self.assertTrue(Path(report["recovery_path"]).is_file())

    def test_poll_does_not_accept_check_success_after_wallclock_deadline(self):
        module = self.gate_module()
        gate = module.Gate(type("Args", (), {"timeout_seconds": 0.02,
                                            "request_timeout": 0.1, "poll_interval": 0.01})())

        def late_success(_timeout):
            time.sleep(0.04)
            return True

        with self.assertRaises(module.GateError):
            gate.poll(late_success)

    def test_graphql_error_after_write_still_rolls_back_without_leaking_response(self):
        with FakeTina(self.project, "graphql_error_after_write") as f:
            code, report = self.run_gate(f)
            self.assertEqual((code, report["status"]), (1, "FAIL"))
            self.assert_restored(f)

    def test_failed_restore_retains_owner_only_recovery_evidence(self):
        with FakeTina(self.project, "restore_fail") as f:
            code, report = self.run_gate(f)
            self.assertEqual((code, report["status"]), (3, "MANUAL_REVIEW"))
            backup = Path(report["recovery_path"])
            self.assertTrue(backup.is_file())
            self.assertEqual(backup.parent.parent, (self.project / "pipeline").resolve())
            self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(backup.parent.stat().st_mode), 0o700)
            recovery = json.loads(backup.read_text())
            self.assertEqual(recovery["original_document"], self.document)
            self.assertNotIn(PASSWORD, backup.read_text())
            self.assertNotIn(COOKIE, backup.read_text())

    def test_restore_file_alone_without_restored_html_requires_manual_review(self):
        with FakeTina(self.project, "restore_stale") as f:
            code, report = self.run_gate(f)
            self.assertEqual((code, report["status"]), (3, "MANUAL_REVIEW"))
            self.assertEqual(report["phases"]["restore_persist"]["status"], "PASS")
            self.assertEqual(report["phases"]["restore_live"]["status"], "FAIL")
            self.assertTrue(Path(report["recovery_path"]).exists())

    def test_unrelated_content_damage_is_not_silently_overwritten(self):
        with FakeTina(self.project, "mutate_other_field") as f:
            code, report = self.run_gate(f)
            self.assertEqual((code, report["status"]), (3, "MANUAL_REVIEW"))
            self.assertEqual(f.mutations[-1], ORIGINAL)
            self.assertEqual(json.loads(self.settings.read_text())["tagline"], "unexpected backend damage")
            self.assertTrue(Path(report["recovery_path"]).exists())

    def test_hidden_or_script_marker_is_not_visible_proof(self):
        for mode in ("hidden_live", "script_only"):
            with self.subTest(mode=mode), FakeTina(self.project, mode) as f:
                code, report = self.run_gate(f)
                self.assertNotEqual(code, 0)
                self.assertEqual(report["phases"]["live"]["status"], "FAIL")
                self.assertEqual(f.mutations[-1], ORIGINAL)

    def test_authentication_cookie_is_required_before_mutation(self):
        for mode in ("auth_fail", "no_cookie", "query_mismatch", "redirect_login"):
            with self.subTest(mode=mode), FakeTina(self.project, mode) as f:
                code, report = self.run_gate(f)
                self.assertNotEqual(code, 0)
                self.assertEqual(f.mutations, [])
                self.assertNotIn(("POST", "/credential-sink"), f.requests)

    def test_guard_refuses_without_password(self):
        with FakeTina(self.project) as f:
            code, report = self.run_gate(f, password=None)
            self.assertEqual((code, report["status"]), (2, "UNVERIFIED"))
            self.assertEqual(f.requests, [])

    def test_guard_refuses_non_staging_and_unsafe_origins(self):
        for extra in (("--environment", "production"), ("--site-url", "http://example.com"),
                      ("--site-url", "https://user:secret@example.com"),
                      ("--site-url", "https://example.com/admin/"),
                      ("--site-url", "file:///etc/passwd"), ("--timeout-seconds", "nan")):
            with self.subTest(extra=extra), FakeTina(self.project) as f:
                code, report = self.run_gate(f, extra=extra)
                self.assertEqual((code, report["status"]), (2, "UNVERIFIED"))
                self.assertEqual(f.requests, [])

    def test_guard_requires_explicit_write_opt_in(self):
        with FakeTina(self.project) as f:
            self.attest(f)
            args = [sys.executable, str(SCRIPT), "--environment", "staging", "--project-root", str(self.project), "--site-url", f.url]
            p = subprocess.run(args, env={**os.environ, "TINA_ADMIN_PASSWORD": PASSWORD}, text=True, capture_output=True, timeout=3)
            self.assertTrue(p.stdout.startswith("{"), "guard must report JSON")
            self.assertEqual((p.returncode, json.loads(p.stdout)["status"]), (2, "UNVERIFIED"))
            self.assertEqual(f.requests, [])

    def test_staging_metadata_is_required_and_must_match_before_any_network(self):
        for case in ("missing", "malformed", "wrong_version", "production", "wrong_origin", "not_authorized", "truthy_string", "missing_revision", "wrong_revision"):
            with self.subTest(case=case), FakeTina(self.project) as f:
                self.attest(f)
                data = json.loads(self.attestation.read_text())
                if case == "missing":
                    self.attestation.unlink()
                elif case == "malformed":
                    self.attestation.write_text("{")
                elif case == "missing_revision":
                    del data["source_revision"]
                    self.attestation.write_text(json.dumps(data))
                else:
                    key, value = {
                        "wrong_version": ("schema_version", "v0"),
                        "production": ("environment", "production"),
                        "wrong_origin": ("site_url", "https://production.invalid"),
                        "not_authorized": ("authorized_by_operator", False),
                        "truthy_string": ("authorized_by_operator", "true"),
                        "wrong_revision": ("source_revision", "sha256:" + "0" * 64),
                    }[case]
                    data[key] = value
                    self.attestation.write_text(json.dumps(data))
                code, report = self.run_gate(f, attest=False)
                self.assertEqual((code, report["status"]), (2, "UNVERIFIED"))
                self.assertEqual(f.requests, [])

    def test_unresolved_recovery_blocks_a_new_run_before_network(self):
        recovery = self.project / "pipeline/.cms-roundtrip-prior"
        recovery.mkdir(mode=0o700)
        (recovery / "recovery.json").write_text("{}")
        with FakeTina(self.project) as f:
            code, report = self.run_gate(f)
            self.assertEqual((code, report["status"]), (3, "MANUAL_REVIEW"))
            self.assertEqual(f.requests, [])

    def test_signal_after_write_attempt_restores_and_crash_keeps_private_backup(self):
        for sig in (signal.SIGTERM, signal.SIGKILL):
            with self.subTest(signal=sig), FakeTina(self.project, "stale_live") as f:
                self.attest(f)
                command = [sys.executable, str(SCRIPT), "--environment", "staging", "--allow-write",
                           "--project-root", str(self.project), "--site-url", f.url,
                           "--timeout-seconds", "2", "--poll-interval", "0.01"]
                process = subprocess.Popen(command, env={**os.environ, "TINA_ADMIN_PASSWORD": PASSWORD},
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    deadline = time.monotonic() + 3
                    while not f.public_after_write and process.poll() is None and time.monotonic() < deadline:
                        time.sleep(0.01)
                    self.assertTrue(f.public_after_write, "child must acknowledge save and enter live polling before interrupt")
                    process.send_signal(sig)
                    stdout, stderr = process.communicate(timeout=4)
                    self.assertEqual(stderr, "")
                    self.assertNotIn(PASSWORD, stdout)
                    self.assertNotIn(ORIGINAL, stdout)
                    if sig == signal.SIGTERM:
                        self.assertEqual(json.loads(stdout)["status"], "FAIL")
                        self.assert_restored(f)
                        self.assertFalse(list((self.project / "pipeline").glob(".cms-roundtrip-*")))
                    else:
                        backups = list((self.project / "pipeline").glob(".cms-roundtrip-*/recovery.json"))
                        self.assertEqual(len(backups), 1)
                        self.assertEqual(stat.S_IMODE(backups[0].stat().st_mode), 0o600)
                        self.assertEqual(json.loads(backups[0].read_text())["original_document"], self.document)
                        code, report = self.run_gate(f)
                        self.assertEqual((code, report["status"]), (3, "MANUAL_REVIEW"))
                        self.assertEqual(len(f.mutations), 1)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.communicate(timeout=3)

    def test_schema_unsupported_or_duplicate_field_fails_before_login(self):
        schema = json.loads(json.dumps(SCHEMA))
        schema["collections"][0]["fields"].append({"name": "siteName", "type": "object"})
        self.schema.write_text(json.dumps(schema))
        with FakeTina(self.project) as f:
            code, report = self.run_gate(f)
            self.assertEqual((code, report["status"]), (2, "UNVERIFIED"))
            self.assertEqual(f.requests, [])

    def test_standard_defaults_work_without_generated_schema(self):
        self.schema.unlink()
        with FakeTina(self.project) as f:
            code, report = self.run_gate(f)
            self.assertEqual((code, report["status"]), (0, "PASS"))
            self.assertEqual(report["evidence"]["schema_contract"], "standard_settings_defaults")
            self.assert_restored(f)

    def test_source_revision_binds_source_and_ignores_reports_and_generated_builds(self):
        self.assertRegex(self.revision, r"^sha256:[a-f0-9]{64}$")
        (self.project / "pipeline/unrelated.json").write_text("{}")
        (self.project / "dist").mkdir()
        (self.project / "dist/index.html").write_text("built output")
        self.assertEqual(self.fingerprint(), self.revision)
        page = self.project / "src/index.astro"
        page.write_text("<header>changed source</header>")
        self.assertNotEqual(self.fingerprint(), self.revision)
        with FakeTina(self.project) as f:
            code, report = self.run_gate(f)
            self.assertEqual((code, report["status"]), (2, "UNVERIFIED"))
            self.assertEqual(f.requests, [])

    def test_private_report_override_and_unsafe_report_path_guard(self):
        with FakeTina(self.project) as f:
            target = self.project / "pipeline/cms-roundtrip-report-custom.json"
            code, report = self.run_gate(f, extra=("--report", str(target)))
            self.assertEqual((code, report["status"]), (0, "PASS"))
            self.assertEqual(json.loads(target.read_text()), report)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        for target in (self.project / "public/report.json", self.attestation, self.settings):
            with self.subTest(target=target), FakeTina(self.project) as f:
                code, report = self.run_gate(f, extra=("--report", str(target)))
                self.assertEqual((code, report["status"]), (2, "UNVERIFIED"))
                self.assertEqual(f.requests, [])

    def test_report_path_cannot_overwrite_pipeline_artifacts_or_unsafe_names(self):
        names = ("vps-connection.json", "00-brief.json", "custom-cms-report.json",
                 ".cms-roundtrip-report-hidden.json", "cms-roundtrip-report-.json",
                 "cms-roundtrip-report-a*b.json", "cms-roundtrip-report-a.b.json")
        for name in names:
            with self.subTest(name=name), FakeTina(self.project) as f:
                target = self.project / "pipeline" / name
                original = b'{"fixture_artifact":"must remain untouched"}\n'
                target.write_bytes(original)
                before = target.stat()
                self.attest(f)
                pipeline_before = set(self.attestation.parent.iterdir())
                code, report = self.run_gate(f, extra=("--report", str(target)), attest=False)
                self.assertEqual(target.read_bytes(), original, "pipeline artifact must not be overwritten")
                self.assertEqual(target.stat().st_ino, before.st_ino)
                self.assertEqual(target.stat().st_mtime_ns, before.st_mtime_ns)
                self.assertEqual(set(self.attestation.parent.iterdir()), pipeline_before)
                self.assertEqual((code, report["status"]), (2, "UNVERIFIED"))
                self.assertEqual(f.requests, [], "invalid report path must fail before login or mutation")

    def test_report_path_rejects_parent_traversal_even_to_pipeline(self):
        with FakeTina(self.project) as f:
            target = self.project / "pipeline/../pipeline/cms-roundtrip-report-safe.json"
            code, report = self.run_gate(f, extra=("--report", str(target)))
            self.assertEqual((code, report["status"]), (2, "UNVERIFIED"))
            self.assertEqual(f.requests, [])
            self.assertFalse(target.exists())

    def test_report_links_cannot_modify_or_unlink_an_existing_artifact(self):
        artifact = self.project / "pipeline/vps-connection.json"
        original = b'{"fixture_artifact":"not a report"}\n'
        artifact.write_bytes(original)
        original_inode = artifact.stat().st_ino
        for kind in ("symlink", "hardlink"):
            with self.subTest(kind=kind), FakeTina(self.project) as f:
                target = self.project / ("pipeline/cms-roundtrip-report-" + kind + ".json")
                if kind == "symlink":
                    target.symlink_to(artifact)
                else:
                    os.link(artifact, target)
                self.attest(f)
                pipeline_before = set(self.attestation.parent.iterdir())
                code, report = self.run_gate(f, extra=("--report", str(target)), attest=False)
                self.assertEqual(artifact.read_bytes(), original)
                self.assertEqual(artifact.stat().st_ino, original_inode)
                self.assertEqual(target.read_bytes(), original)
                self.assertEqual(set(self.attestation.parent.iterdir()), pipeline_before)
                self.assertEqual((code, report["status"]), (2, "UNVERIFIED"))
                self.assertEqual(f.requests, [])

    def test_guard_refuses_missing_project_settings_and_invalid_schema(self):
        cases = ("missing_project", "missing_file", "bad_json", "bad_schema", "symlink")
        for case in cases:
            with self.subTest(case=case), FakeTina(self.project) as f:
                extra = ()
                if case == "missing_project":
                    extra = ("--project-root", str(self.project / "nonexistent"))
                elif case == "missing_file":
                    self.settings.unlink()
                elif case == "bad_json":
                    self.settings.write_text("{")
                elif case == "bad_schema":
                    self.schema.write_text(json.dumps({"collections": []}))
                elif case == "symlink":
                    target = self.project / "outside.json"
                    target.write_text(json.dumps(self.document))
                    self.settings.unlink()
                    self.settings.symlink_to(target)
                code, report = self.run_gate(f, extra=extra)
                self.assertEqual((code, report["status"]), (2, "UNVERIFIED"))
                self.assertEqual(f.requests, [])
                if self.settings.is_symlink():
                    self.settings.unlink()
                self.settings.write_text(json.dumps(self.document))
                self.schema.write_text(json.dumps(SCHEMA))


if __name__ == "__main__":
    unittest.main()
