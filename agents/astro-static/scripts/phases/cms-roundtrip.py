#!/usr/bin/env python3
"""Authorized staging CMS save/persist/render/restore acceptance gate.

Requires operator-created pipeline/cms-staging.json, never provisions staging.
Metadata: {"schema_version":"astro-static-cms-staging/v1",
"environment":"staging", "site_url":"https://staging.example.test",
"authorized_by_operator":true, "source_revision":"sha256:..."}.
site_url must equal the CLI canonical origin. Obtain source_revision with
--project-root PATH --print-source-revision (read-only, no network/password).
The fingerprint covers src/, public/, tina/ (except __generated__/), package
manifests/lockfiles, astro.config.*, and tsconfig.json. JSON is canonicalized;
pipeline/, dist/, caches and generated output are excluded. Staged configuration
is included, so the orchestrator must record the staged fingerprint explicitly.
This is operator attestation, not independent proof of the hosting environment.

Contract checked read-only against mount-devil/tina/__generated__/schema.gql:
settings(relativePath: String), updateSettings(relativePath: String!,
params: SettingsMutation!), SettingsMutation.siteName: String.
Auto-select exactly one of src/content/settings/global.json or site.json;
refuse missing/ambiguous documents before network access. Only siteName changes.

Recovery: pipeline/.cms-roundtrip-*/recovery.json (0700 directory/0600 file).
Ignore that pattern in version control and never publish pipeline/. An unresolved
backup blocks subsequent runs. SIGKILL/process loss needs operator recovery;
SIGINT/SIGTERM attempt API rollback. No credential is written to disk or report.
Exit: 0 PASS, 1 FAIL (clean rollback), 2 UNVERIFIED, 3 MANUAL_REVIEW.
The JSON report is stdout and pipeline/cms-roundtrip-report.json (0600), or a
--report PATH directly within pipeline/. Never publish reports as public assets.
Only cms-roundtrip-report.json or cms-roundtrip-report-<suffix>.json is allowed;
suffix is 1-64 ASCII alphanumerics/underscores/hyphens, starting alphanumeric.
Parent traversal, symlinks, hardlinks and non-regular report files are refused.
Each request has a total wall-clock deadline, including connection/headers/body.
Transport loss, timeout or interruption of a mutation makes its completion
indeterminate. Rollback is still attempted, but even clean current readbacks
cannot prove ordering against a late server commit: retain the recovery backup
and require MANUAL_REVIEW. Deadline supervision uses daemon threads; it cannot
cancel server-side work (or guarantee immediate interruption of urllib/DNS).
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
from html.parser import HTMLParser
import http.cookiejar
import ipaddress
import json
import math
import os
from pathlib import Path
import queue
import re
import signal
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


READ_QUERY = """query CmsRoundtripRead($relativePath: String!) {
  settings(relativePath: $relativePath) { siteName }
}"""
WRITE_QUERY = """mutation CmsRoundtripWrite($relativePath: String!, $params: SettingsMutation!) {
  updateSettings(relativePath: $relativePath, params: $params) { siteName }
}"""
PHASES = ("preflight", "authenticate", "baseline", "backup", "save", "persist",
          "live", "restore", "restore_persist", "restore_live", "source_revision")


class GateError(Exception):
    """Only fixed, non-sensitive error tokens may cross the reporting boundary."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise GateError("REDIRECT_REFUSED")


class HeaderText(HTMLParser):
    """Extract header text, excluding non-rendered markup, not a browser/CSS audit."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.text = []
        self.visible_text = []
        self.candidates = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        hidden = (tag in {"script", "style", "template", "noscript"}
                  or "hidden" in attrs or attrs.get("aria-hidden") == "true"
                  or any(x in (attrs.get("style") or "").replace(" ", "").lower()
                         for x in ("display:none", "visibility:hidden")))
        inherited = bool(self.stack and self.stack[-1]["hidden"])
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input",
                       "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append({"tag": tag, "hidden": hidden or inherited,
                               "header": tag == "header" or bool(self.stack and self.stack[-1]["header"]),
                               "text": []})

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                for node in self.stack[index:]:
                    if node["header"] and not node["hidden"]:
                        self.candidates.append(normalized_text("".join(node["text"])))
                del self.stack[index:]
                break

    def handle_data(self, data):
        if self.stack and not self.stack[-1]["hidden"]:
            self.visible_text.append(data)
            if self.stack[-1]["header"]:
                self.text.append(data)
                for node in self.stack:
                    if node["header"] and not node["hidden"]:
                        node["text"].append(data)


def normalized_text(value):
    return " ".join(value.split())


def parsed_header(page):
    parser = HeaderText()
    parser.feed(page)
    parser.close()
    return parser


def visible_header(page, expected):
    return normalized_text(expected) in parsed_header(page).candidates


def canonical_origin(value):
    if not value or any(ord(c) <= 32 for c in value) or "\\" in value:
        raise GateError("UNSAFE_ORIGIN")
    try:
        parsed = urllib.parse.urlsplit(value)
        host, port = parsed.hostname, parsed.port
        if (not host or parsed.username is not None or parsed.password is not None
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment
                or parsed.scheme not in ("http", "https") or host.endswith(".")):
            raise ValueError()
        loopback = host == "localhost"
        try:
            loopback = loopback or ipaddress.ip_address(host).is_loopback
        except ValueError:
            pass
        if parsed.scheme == "http" and not loopback:
            raise ValueError()
        host = host.encode("idna").decode("ascii").lower()
        if ":" in host:
            host = f"[{host}]"
        default = 443 if parsed.scheme == "https" else 80
        authority = host if port in (None, default) else f"{host}:{port}"
        return f"{parsed.scheme}://{authority}"
    except (ValueError, UnicodeError):
        raise GateError("UNSAFE_ORIGIN") from None


def local_path(root, relative):
    path = root
    for part in Path(relative).parts:
        path = path / part
        if path.is_symlink():
            raise GateError("SYMLINK_REFUSED")
    if not path.resolve().is_relative_to(root):
        raise GateError("PATH_OUTSIDE_PROJECT")
    return path


def read_document(path):
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError()
        return value, hashlib.sha256(raw).hexdigest()
    except (OSError, ValueError):
        raise GateError("INVALID_OR_MISSING_LOCAL_JSON") from None


def validate_report_target(path, pipeline):
    if (".." in path.parts or path.parent.resolve() != pipeline
            or not re.fullmatch(r"cms-roundtrip-report(?:-[A-Za-z0-9][A-Za-z0-9_-]{0,63})?\.json", path.name)
            or path.is_symlink()
            or (path.exists() and (not path.is_file() or path.stat().st_nlink != 1))):
        raise GateError("PRIVATE_PIPELINE_REPORT_PATH_REQUIRED")


def source_revision(root):
    """Content identity for the staged source tree, not a claim about git HEAD."""
    if not root.is_dir() or not (root / "src").is_dir():
        raise GateError("LOCAL_SOURCE_TREE_REQUIRED")
    paths = []
    for name in ("src", "public", "tina"):
        base = local_path(root, name)
        if not base.exists():
            continue
        for directory, dirs, files in os.walk(base, followlinks=False):
            parent = Path(directory)
            for child in dirs + files:
                if (parent / child).is_symlink():
                    raise GateError("SOURCE_SYMLINK_REFUSED")
            dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "node_modules")
                       and not (parent == root / "tina" and d == "__generated__")]
            paths.extend(parent / f for f in files if f != ".DS_Store")
    for pattern in ("package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
                    "bun.lock", "bun.lockb", "astro.config.*", "tsconfig.json"):
        paths.extend(root.glob(pattern))
    entries = []
    for path in sorted(set(paths)):
        if path.is_symlink() or not path.is_file():
            raise GateError("SOURCE_FILE_REQUIRED")
        data = path.read_bytes()
        if path.suffix == ".json":
            try:
                data = json.dumps(json.loads(data), sort_keys=True, separators=(",", ":"),
                                  ensure_ascii=False).encode()
            except (ValueError, UnicodeError):
                pass  # Malformed content still has a deterministic identity.
        entries.append([path.relative_to(root).as_posix(), hashlib.sha256(data).hexdigest()])
    digest = hashlib.sha256(json.dumps(entries, separators=(",", ":")).encode()).hexdigest()
    return "sha256:" + digest


class Client:
    def __init__(self, origin, request_timeout, relative_path):
        self.origin = origin
        self.timeout = request_timeout
        self.relative_path = relative_path
        self.cookies = http.cookiejar.CookieJar()
        self.uncertain_write = False
        # Never route credentials through environment-configured proxies.
        self.api = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                              urllib.request.HTTPCookieProcessor(self.cookies))
        self.public = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, path, body=None, public=False, timeout=None, mutation=False):
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        cancelled = threading.Event()
        result = queue.Queue(maxsize=1)

        def exchange():
            try:
                value = self._exchange(path, body, public, deadline, cancelled)
                result.put((True, value))
            except Exception as error:
                # Never move raw exception/response/header text into the report.
                token = str(error) if isinstance(error, GateError) else "REQUEST_FAILED"
                result.put((False, token))

        try:
            # No executor/context manager: a stuck DNS/header read must not join
            # indefinitely at timeout or interpreter shutdown.
            threading.Thread(target=exchange, daemon=True).start()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise GateError("REQUEST_DEADLINE_EXCEEDED")
            try:
                ok, value = result.get(timeout=remaining)
            except queue.Empty:
                raise GateError("REQUEST_DEADLINE_EXCEEDED") from None
            if time.monotonic() >= deadline:
                raise GateError("REQUEST_DEADLINE_EXCEEDED")
            if not ok:
                raise GateError(value)
            return value
        except BaseException:
            if mutation:
                self.uncertain_write = True  # Sticky: later readbacks cannot prove ordering.
            raise
        finally:
            cancelled.set()

    def _exchange(self, path, body, public, deadline, cancelled):
        headers = {"Origin": self.origin, "Cache-Control": "no-cache, no-store",
                   "Accept": "text/html" if public else "application/json"}
        payload = None
        if body is not None:
            payload = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.origin + path, data=payload, headers=headers)
        remaining = deadline - time.monotonic()
        if cancelled.is_set() or remaining <= 0:
            raise GateError("REQUEST_DEADLINE_EXCEEDED")
        with (self.public if public else self.api).open(req, timeout=remaining) as response:
            if response.status != 200:
                raise GateError("HTTP_STATUS_NOT_OK")
            raw = bytearray()
            while True:
                if cancelled.is_set() or time.monotonic() >= deadline:
                    raise GateError("REQUEST_DEADLINE_EXCEEDED")
                part = response.read1(min(65536, 8 * 1024 * 1024 + 1 - len(raw)))
                if cancelled.is_set() or time.monotonic() >= deadline:
                    raise GateError("REQUEST_DEADLINE_EXCEEDED")
                raw.extend(part)
                if len(raw) > 8 * 1024 * 1024:
                    raise GateError("RESPONSE_TOO_LARGE")
                if not part:
                    break
            if public:
                if "text/html" not in response.headers.get("Content-Type", ""):
                    raise GateError("HOMEPAGE_NOT_HTML")
                return raw.decode("utf-8")
            return json.loads(raw)

    def authenticate(self, password):
        response = self.request("/api/tina/login", {"password": password})
        if not isinstance(response, dict) or response.get("success") is not True:
            raise GateError("LOGIN_NOT_CONFIRMED")
        if not any(cookie.name == "tina_admin_session" for cookie in self.cookies):
            raise GateError("SESSION_COOKIE_MISSING")
        response = self.request("/api/tina/auth-check")
        if not isinstance(response, dict) or response.get("authenticated") is not True:
            raise GateError("COOKIE_AUTH_NOT_CONFIRMED")

    def graphql(self, name=None):
        write = name is not None
        variables = {"relativePath": self.relative_path}
        if write:
            variables["params"] = {"siteName": name}
        response = self.request("/api/tina/gql", {
            "query": WRITE_QUERY if write else READ_QUERY,
            "operationName": "CmsRoundtripWrite" if write else "CmsRoundtripRead",
            "variables": variables,
        }, mutation=write)
        try:
            if response.get("errors"):
                raise ValueError()
            result = response["data"]["updateSettings" if write else "settings"]["siteName"]
            if not isinstance(result, str) or (write and result != name):
                raise ValueError()
            return result
        except (AttributeError, KeyError, TypeError, ValueError):
            raise GateError("GRAPHQL_NOT_CONFIRMED") from None


class Gate:
    def __init__(self, args):
        self.args = args
        self.report = {"schema_version": "astro-static-cms-roundtrip/v1", "status": "UNVERIFIED",
                       "environment": "staging", "verification_scope": "operator_attested_staging_roundtrip",
                       "attestation_is_operator_supplied": True,
                       "operator_authorized": False, "origin": None, "source_revision": None,
                       "mutation_outcome": "NOT_ATTEMPTED",
                       "phases": {phase: {"status": "SKIPPED"} for phase in PHASES},
                       "evidence": {}, "recovery_path": None, "report_path": None}
        self.phase = "preflight"
        self.backup = None
        self.lock = None
        self.attempted = False
        self.report_target = None

    def step(self, phase, work):
        self.phase = phase
        try:
            result = work()
        except BaseException as error:
            token = str(error) if isinstance(error, GateError) else "LOCAL_OPERATION_FAILED"
            self.report["phases"][phase] = {"status": "FAIL", "code": token}
            raise GateError(token) from None
        self.report["phases"][phase] = {"status": "PASS"}
        return result

    def preflight(self):
        a = self.args
        if a.environment != "staging" or not a.allow_write:
            raise GateError("EXPLICIT_STAGING_WRITE_AUTHORIZATION_REQUIRED")
        if not os.environ.get("TINA_ADMIN_PASSWORD"):
            raise GateError("PASSWORD_ENV_REQUIRED")
        for value, limit in ((a.timeout_seconds, 600), (a.poll_interval, 30), (a.request_timeout, 60)):
            if not math.isfinite(value) or not 0 < value <= limit:
                raise GateError("INVALID_POLL_BOUNDS")
        self.origin = canonical_origin(a.site_url)
        self.report["origin"] = self.origin
        self.root = Path(a.project_root).expanduser().resolve()
        if not self.root.is_dir() or self.root == Path(self.root.anchor):
            raise GateError("LOCAL_PROJECT_REQUIRED")
        self.pipeline = local_path(self.root, "pipeline")
        report_target = Path(a.report).expanduser() if a.report else self.pipeline / "cms-roundtrip-report.json"
        if not report_target.is_absolute():
            report_target = self.root / report_target
        validate_report_target(report_target, self.pipeline)
        metadata, _ = read_document(local_path(self.root, "pipeline/cms-staging.json"))
        if (metadata.get("schema_version") != "astro-static-cms-staging/v1"
                or metadata.get("environment") != "staging"
                or metadata.get("site_url") != self.origin
                or metadata.get("authorized_by_operator") is not True):
            raise GateError("STAGING_ATTESTATION_INVALID")
        self.report["operator_authorized"] = True
        lock_path = local_path(self.root, "pipeline/.cms-roundtrip.lock")
        self.lock = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise GateError("ANOTHER_GATE_IS_RUNNING") from None
        self.report_target = report_target
        self.report["report_path"] = str(report_target)
        # Check recovery before reading the possibly still-mutated source tree.
        prior = sorted(self.pipeline.glob(".cms-roundtrip-*"))
        if prior:
            self.report["recovery_path"] = str(prior[0] / "recovery.json")
            self.report["status"] = "MANUAL_REVIEW"
            raise GateError("UNRESOLVED_RECOVERY_EXISTS")
        candidates = [local_path(self.root, "src/content/settings/" + name)
                      for name in ("global.json", "site.json")]
        present = [path for path in candidates if path.exists()]
        if not present:
            raise GateError("SETTINGS_DOCUMENT_MISSING")
        if len(present) != 1:
            raise GateError("SETTINGS_DOCUMENT_AMBIGUOUS")
        self.settings = present[0]
        self.relative_path = self.settings.name
        self.settings_relative = self.settings.relative_to(self.root).as_posix()
        self.revision = source_revision(self.root)
        self.report["source_revision"] = self.revision
        if metadata.get("source_revision") != self.revision:
            raise GateError("STAGING_SOURCE_REVISION_MISMATCH")
        self.original, self.original_sha = read_document(self.settings)
        self.original_name = self.original.get("siteName")
        if not isinstance(self.original_name, str) or not self.original_name.strip():
            raise GateError("SITE_NAME_STRING_REQUIRED")
        schema_path = local_path(self.root, "tina/__generated__/_schema.json")
        self.report["evidence"]["schema_contract"] = "standard_settings_defaults"
        if schema_path.exists():
            schema, _ = read_document(schema_path)
            collections = schema.get("collections")
            if not isinstance(collections, list):
                raise GateError("SETTINGS_SCHEMA_INVALID")
            settings = [c for c in collections if isinstance(c, dict) and c.get("name") == "settings"]
            if len(settings) != 1:
                raise GateError("SETTINGS_SCHEMA_INVALID")
            collection = settings[0]
            fields = collection.get("fields", [])
            names = [f for f in fields if isinstance(f, dict) and f.get("name") == "siteName"] if isinstance(fields, list) else []
            if (collection.get("path") != "src/content/settings" or collection.get("format") != "json"
                    or len(names) != 1 or names[0].get("type") != "string" or names[0].get("list")):
                raise GateError("SETTINGS_SCHEMA_INVALID")
            self.report["evidence"]["schema_contract"] = "local_generated_schema"
        self.client = Client(self.origin, a.request_timeout, self.relative_path)
        self.marker = "CMS acceptance " + uuid.uuid4().hex + " & staging"
        self.report["evidence"]["original_sha256"] = self.original_sha
        self.report["evidence"]["settings_path"] = self.settings_relative
        self.report["evidence"]["field"] = "siteName"

    def homepage(self, timeout=None):
        # Public, cookie-free fetch: proof is rendered HTML, never GraphQL cache.
        return self.client.request("/?cms_roundtrip=" + uuid.uuid4().hex, public=True, timeout=timeout)

    def baseline(self):
        if self.client.graphql() != self.original_name:
            raise GateError("API_LOCAL_SETTINGS_MISMATCH")
        self.baseline_html = self.homepage()
        if not visible_header(self.baseline_html, self.original_name):
            raise GateError("ORIGINAL_HEADER_NOT_RENDERED")

    def backup_original(self):
        document, sha = read_document(self.settings)
        if sha != self.original_sha or document != self.original:
            raise GateError("SETTINGS_CHANGED_BEFORE_SAVE")
        directory = Path(tempfile.mkdtemp(prefix=".cms-roundtrip-", dir=self.pipeline))
        directory.chmod(0o700)
        self.backup = directory / "recovery.json"
        payload = {"schema_version": "astro-static-cms-recovery/v1", "environment": "staging",
                   "site_url": self.origin, "settings_path": self.settings_relative,
                   "relative_path": self.relative_path, "field": "siteName", "marker": self.marker,
                   "original_document": self.original, "original_sha256": self.original_sha,
                   "source_revision": self.revision,
                   "rollback_required": True}
        fd = os.open(self.backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(payload, handle)
            handle.flush()
            os.fsync(handle.fileno())
        # Make the recovery directory entries durable before attempting a write.
        for path in (directory, self.pipeline):
            fd = os.open(path, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

    def save(self):
        self.attempted = True  # Before transport: a lost response can still commit.
        self.client.graphql(self.marker)

    def poll(self, check):
        deadline = time.monotonic() + self.args.timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise GateError("VERIFICATION_TIMEOUT")
            try:
                success = check(min(self.args.request_timeout, remaining))
                if time.monotonic() >= deadline:
                    raise GateError("VERIFICATION_TIMEOUT")
                if success:
                    return
            except GateError:
                pass  # Rebuild can briefly replace files or restart the HTTP server.
            time.sleep(min(self.args.poll_interval, max(0, deadline - time.monotonic())))

    def persisted(self, name, evidence_key):
        expected = {**self.original, "siteName": name}

        def check(_timeout):
            document, sha = read_document(local_path(self.root, self.settings_relative))
            if document != expected:
                return False
            self.report["evidence"][evidence_key] = sha
            return True

        self.poll(check)

    def rendered(self, name, restoring=False):
        def check(timeout):
            page = self.homepage(timeout)
            parsed = parsed_header(page)
            return (normalized_text(name) in parsed.candidates
                    and (not restoring or normalized_text(self.marker)
                         not in normalized_text("".join(parsed.visible_text)))
                    and (restoring or page != self.baseline_html))

        self.poll(check)

    def rollback(self):
        clean = True
        for phase, work in (
            ("restore", lambda: self.client.graphql(self.original_name)),
            ("restore_persist", lambda: self.persisted(self.original_name, "restored_sha256")),
            ("restore_live", lambda: self.rendered(self.original_name, restoring=True)),
        ):
            try:
                self.step(phase, work)
            except GateError:
                clean = False
        return clean

    def run(self):
        passed = False
        clean = True
        try:
            self.step("preflight", self.preflight)
            self.step("authenticate", lambda: self.client.authenticate(os.environ["TINA_ADMIN_PASSWORD"]))
            self.step("baseline", self.baseline)
            self.step("backup", self.backup_original)
            self.step("save", self.save)
            self.step("persist", lambda: self.persisted(self.marker, "saved_sha256"))
            self.step("live", lambda: self.rendered(self.marker))
            self.report["evidence"]["rebuild_proof"] = "persisted_settings_and_changed_live_header_html"
            passed = True
        except GateError:
            pass
        finally:
            if self.attempted:
                # A second interrupt must not interrupt the mandatory recovery attempt.
                for sig in (signal.SIGINT, signal.SIGTERM):
                    signal.signal(sig, signal.SIG_IGN)
                clean = self.rollback()
                if clean:
                    try:
                        self.step("source_revision", self.verify_source_revision)
                    except GateError:
                        clean = False
                self.report["mutation_outcome"] = "INDETERMINATE" if self.client.uncertain_write else "CONFIRMED"
                if self.client.uncertain_write:
                    clean = False
                    self.report["recovery_reason"] = "MUTATION_COMPLETION_UNCONFIRMED"
            if self.backup:
                if clean:
                    try:
                        self.backup.unlink()
                        self.backup.parent.rmdir()
                    except OSError:
                        clean = False
                if not clean:
                    self.report["recovery_path"] = str(self.backup)
        if not clean:
            self.report["status"] = "MANUAL_REVIEW"
        elif self.attempted:
            self.report["status"] = "PASS" if passed else "FAIL"
        elif self.report["phases"]["preflight"]["status"] == "PASS":
            self.report["status"] = "FAIL"
        try:
            if self.report_target:
                try:
                    self.persist_report()
                except (GateError, OSError, ValueError):
                    self.report["status"] = "MANUAL_REVIEW"
                    self.report["report_error"] = "PRIVATE_REPORT_WRITE_FAILED"
        finally:
            if self.lock is not None:
                os.close(self.lock)
        return {"PASS": 0, "FAIL": 1, "UNVERIFIED": 2, "MANUAL_REVIEW": 3}[self.report["status"]]

    def verify_source_revision(self):
        if source_revision(self.root) != self.revision:
            raise GateError("SOURCE_CHANGED_DURING_ROUNDTRIP")

    def persist_report(self):
        validate_report_target(self.report_target, self.pipeline)
        fd, name = tempfile.mkstemp(prefix=".cms-report-", dir=self.pipeline)
        temporary = Path(name)
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump(self.report, handle, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.report_target)
            directory_fd = os.open(self.pipeline, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if temporary.exists():
                temporary.unlink()


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise GateError("INVALID_ARGUMENTS")


def interrupted(_signum, _frame):
    raise GateError("INTERRUPTED")


def main():
    parser = Parser(description=__doc__)
    parser.add_argument("--environment")
    parser.add_argument("--allow-write", action="store_true")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--site-url")
    parser.add_argument("--print-source-revision", action="store_true")
    parser.add_argument("--report", help="pipeline/cms-roundtrip-report.json or cms-roundtrip-report-<safe-suffix>.json")
    parser.add_argument("--timeout-seconds", type=float, default=90)
    parser.add_argument("--poll-interval", type=float, default=1)
    parser.add_argument("--request-timeout", type=float, default=10)
    try:
        args = parser.parse_args()
        if args.print_source_revision:
            root = Path(args.project_root).expanduser().resolve()
            print(json.dumps({"schema_version": "astro-static-cms-source/v1",
                              "source_revision": source_revision(root)}))
            return 0
        if args.environment is None or args.site_url is None:
            raise GateError("INVALID_ARGUMENTS")
    except (GateError, OSError):
        print(json.dumps({"schema_version": "astro-static-cms-roundtrip/v1", "status": "UNVERIFIED",
                          "phases": {"preflight": {"status": "FAIL", "code": "INVALID_ARGUMENTS"}},
                          "recovery_path": None}))
        return 2
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, interrupted)
    gate = Gate(args)
    code = gate.run()
    print(json.dumps(gate.report, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
