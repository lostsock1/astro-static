"""Offline operations regressions: isolated git repositories and fake transports only."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parent
REAL_GIT = shutil.which("git")
REAL_BASH = shutil.which("bash")
TEMP_ROOT = Path(os.environ.get("TMPDIR", tempfile.gettempdir()))


class OperationsHardeningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="astro-ops-test-", dir=TEMP_ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.home = self.root / "home"
        self.home.mkdir()
        self.log = self.root / "calls.jsonl"
        self.env = dict(os.environ, HOME=str(self.home),
                        PATH=f"{self.bin}:{os.environ['PATH']}",
                        GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=str(self.home / "gitconfig"),
                        GIT_TERMINAL_PROMPT="0", REAL_GIT=REAL_GIT, OPS_LOG=str(self.log),
                        ASTRO_STATIC_PUSH_BUDGET_SECONDS="15",
                        ASTRO_STATIC_PUSH_HTTP_SECONDS="4",
                        ASTRO_STATIC_PUSH_FALLBACK_SECONDS="4")
        for key in list(self.env):
            if key.startswith("GIT_") and key not in {
                "GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL", "GIT_TERMINAL_PROMPT"
            }:
                del self.env[key]
        self.fake("bash", f'''#!/usr/bin/env python3
import os, sys
if len(sys.argv) > 2 and sys.argv[1] == '-c' and '/dev/tcp/' in sys.argv[2]:
    sys.exit(0)
os.execv({REAL_BASH!r}, [{REAL_BASH!r}]+sys.argv[1:])
''')
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Offline test")
        self.git("config", "user.email", "offline@localhost")
        self.write("site.txt", "site\n")
        self.git("add", "site.txt")
        self.git("commit", "-qm", "initial")
        self.write("pipeline/vps-connection.json", json.dumps({
            "gitea_url": "http://127.0.0.1:1", "gitea_user": "offline",
            "gitea_pass": "offline-test-password", "project_name": "offline",
            "ssh_port": 2222, "ssh_key": str(self.root / "key"),
            "ssh_user": "offline", "ssh_host": "offline.invalid",
        }))
        (self.root / "key").write_text("not-a-real-key")
        self.fake("curl", "#!/usr/bin/env bash\nif [ -n \"${SLOW_CURL:-}\" ]; then sleep 30; fi\nprintf 200\n")
        # The baseline shell watchdog leaves inherited capture pipes open on
        # macOS. An offline timeout executable keeps unrelated red tests fast.
        self.fake("timeout", '''#!/usr/bin/env python3
import subprocess, sys
try:
    sys.exit(subprocess.run(sys.argv[2:], timeout=float(sys.argv[1])).returncode)
except subprocess.TimeoutExpired:
    sys.exit(124)
''')
        self.fake("git", '''#!/usr/bin/env python3
import json, os, subprocess, sys, time
a=sys.argv[1:]; i=0
while i < len(a):
    if a[i] == '-c': i += 2
    elif a[i] == '--literal-pathspecs': i += 1
    else: break
cmd=a[i] if i < len(a) else ''
with open(os.environ['OPS_LOG'],'a') as f: f.write(json.dumps(['git']+a)+'\\n')
if cmd in ('fetch','pull','push'):
    if os.environ.get('CHECK_CREDENTIALS'):
        p=subprocess.run([os.environ['REAL_GIT']]+a[:i]+['credential','fill'],
            input='protocol=http\\nhost=127.0.0.1:1\\n\\n',text=True,capture_output=True)
        if p.returncode or 'password=offline-test-password' not in p.stdout: sys.exit(88)
    if cmd == 'fetch' and os.environ.get('FAKE_REMOTE_HEAD'):
        subprocess.run([os.environ['REAL_GIT'],'update-ref','refs/remotes/origin/main','HEAD'],check=True)
    if cmd == 'fetch' and os.environ.get('FAKE_REMOTE_REPO'):
        subprocess.run([os.environ['REAL_GIT'],'fetch',os.environ['FAKE_REMOTE_REPO'],
            'main:refs/remotes/origin/main'],check=True,capture_output=True)
    if cmd == 'push':
        if os.environ.get('SLOW_PUSH'): time.sleep(30)
        sys.exit(int(os.environ.get('PUSH_EXIT','0')))
    sys.exit(0)
if cmd == 'add' and os.environ.get('FAIL_ADD'): sys.exit(73)
sys.exit(subprocess.call([os.environ['REAL_GIT']]+a))
''')
        for tool in ("ssh", "scp", "ssh-keygen"):
            self.fake(tool, f'''#!/usr/bin/env python3
import json, os, sys, time
with open(os.environ['OPS_LOG'],'a') as f: f.write(json.dumps(['{tool}']+sys.argv[1:])+'\\n')
if os.environ.get('SLOW_{tool.upper().replace('-', '_')}'): time.sleep(30)
sys.exit(int(os.environ.get('{tool.upper().replace('-', '_')}_EXIT','0')))
''')

    def fake(self, name, body):
        path = self.bin / name
        path.write_text(body)
        path.chmod(0o700)

    def write(self, name, contents):
        path = self.project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
        return path

    def git(self, *args, check=True):
        return subprocess.run([REAL_GIT, *args], cwd=self.project, env=self.env,
                              text=True, capture_output=True, check=check)

    def run_push(self, **env):
        return subprocess.run(["bash", str(ROOT / "phases/push-gitea.sh")],
                              cwd=self.project, env=dict(self.env, **env),
                              text=True, capture_output=True, timeout=20)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    @staticmethod
    def process_running(pid):
        result = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)],
                                text=True, capture_output=True)
        return result.returncode == 0 and bool(result.stdout.strip()) and not result.stdout.strip().startswith("Z")

    def remote_interpreter(self, *, connect_delay=0, clone_seconds=0, push_seconds=0):
        """Run the emitted SSH command, but with only temp paths and fake tools.

        The server driver has its own session, just like an SSH server: killing
        the local fake SSH client cannot substitute for the remote deadline.
        No real sudo, remote git, SSH, network, or system-temp writes are used.
        """
        remote = self.root / "remote"
        remote.mkdir()
        remote_bin = remote / "bin"
        remote_bin.mkdir()
        (remote / "repo.git").mkdir()
        (remote / "bundle").write_text("offline bundle fixture")

        def remote_fake(name, body):
            path = remote_bin / name
            path.write_text(body)
            path.chmod(0o700)

        remote_fake("sudo", '''#!/usr/bin/env python3
import os, pathlib, shutil, sys
a=sys.argv[1:]
if a[:2] == ['-u','git']: a=a[2:]
root=pathlib.Path(os.environ['REMOTE_ROOT']).resolve()
if a[0] in ('chown','chmod','rm'):
    paths=a[2:]
    for name in paths:
        p=pathlib.Path(name).resolve()
        if root not in p.parents: sys.exit(91)
        if a[0] == 'chmod': p.chmod(int(a[1],8))
        if a[0] == 'rm' and p.exists():
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    sys.exit(0)
if a[0] != 'timeout': sys.exit(92)
os.execv(str(root/'bin/timeout'),a)
''')
        remote_fake("timeout", '''#!/usr/bin/env python3
import json, os, subprocess, sys, time
a=sys.argv[1:]
assert a.pop(0) == '--kill-after=1'
seconds=float(a.pop(0))
with open(os.environ['REMOTE_ROOT']+'/events.jsonl','a') as f:
    f.write(json.dumps({'event':'timer','at':time.time(),'seconds':seconds})+'\\n')
p=subprocess.Popen(a)
try:
    sys.exit(p.wait(timeout=seconds))
except subprocess.TimeoutExpired:
    p.terminate()
    time.sleep(1)
    if p.poll() is None: p.kill()
    p.wait()
    sys.exit(124)
''')
        remote_fake("git", '''#!/usr/bin/env python3
import json, os, pathlib, signal, sys, time
root=pathlib.Path(os.environ['REMOTE_ROOT'])
cmd=next(a for a in sys.argv[1:] if a in ('clone','push'))
if cmd == 'push': signal.signal(signal.SIGTERM,signal.SIG_IGN)
with (root/'events.jsonl').open('a') as f:
    f.write(json.dumps({'event':cmd,'at':time.time(),'pid':os.getpid()})+'\\n')
time.sleep(float(os.environ['REMOTE_'+cmd.upper()+'_SECONDS']))
if cmd == 'push': (root/'late-push-sentinel').write_text('fake remote push completed')
''')
        driver_path = remote / "driver.py"
        driver_path.write_text('''import json, os, pathlib, re, subprocess, time
root=pathlib.Path(os.environ['REMOTE_ROOT'])
request=root/'request.json'
while not request.exists(): time.sleep(.02)
command=json.loads(request.read_text())
# Delay command delivery after local transmission, like SSH authentication /
# scheduling delay. The server survives cancellation of the local client.
time.sleep(float(os.environ['REMOTE_CONNECT_DELAY']))
command=command.replace('/home/git/gitea-repositories/offline/offline.git',str(root/'repo.git'))
command=command.replace('/tmp/astro-static-git-push.XXXXXX',str(root/'work.XXXXXX'))
command=re.sub(r'/tmp/astro-static-push-[A-Za-z0-9.-]+\\.bundle',str(root/'bundle'),command)
assert '/tmp/astro-static-' not in command and '/home/git/' not in command
env=dict(os.environ,PATH=str(root/'bin')+os.pathsep+os.environ['PATH'])
rc=subprocess.run([os.environ['REAL_BASH'],'-c',command],cwd=root,env=env).returncode
(root/'response.json').write_text(json.dumps(rc))
''')
        driver_env = dict(self.env, REMOTE_ROOT=str(remote), REAL_BASH=REAL_BASH,
                          REMOTE_CONNECT_DELAY=str(connect_delay),
                          REMOTE_CLONE_SECONDS=str(clone_seconds), REMOTE_PUSH_SECONDS=str(push_seconds))
        with (remote / "driver.log").open("w") as log:
            driver = subprocess.Popen([sys.executable, str(driver_path)], env=driver_env,
                                      stdout=log, stderr=subprocess.STDOUT, start_new_session=True)

        def cleanup():
            # Kill only this test's independently supervised server group,
            # including deliberately resistant children after a red failure.
            try:
                os.killpg(driver.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            driver.wait(timeout=3)

        self.addCleanup(cleanup)
        self.fake("ssh", f'''#!/usr/bin/env python3
import json, os, pathlib, sys, time
root=pathlib.Path({str(remote)!r})
with open(os.environ['OPS_LOG'],'a') as f: f.write(json.dumps(['ssh']+sys.argv[1:])+'\\n')
tmp=root/'request.tmp'
tmp.write_text(json.dumps(sys.argv[-1]))
tmp.replace(root/'request.json')
while not (root/'response.json').exists(): time.sleep(.02)
sys.exit(json.loads((root/'response.json').read_text()))
''')
        return driver, remote

    def remote_events(self, remote):
        path = remote / "events.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_changed_host_key_is_not_removed_and_scp_is_noninteractive(self):
        shutil.copy2(ROOT / "bg-bootstrap.sh", self.project / "pipeline/_bg-bootstrap.sh")
        setup = self.write("setup-fixture.sh", "# offline fixture\n")
        result = subprocess.run(["bash", "pipeline/_bg-bootstrap.sh"], cwd=self.project,
                                env=dict(self.env, ASTRO_STATIC_SETUP_VPS=str(setup), SCP_EXIT="255"),
                                text=True, capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse([call for call in self.calls() if call[0] == "ssh-keygen"])
        calls = [call for call in self.calls() if call[0] == "scp"]
        self.assertEqual(len(calls), 1)
        self.assertIn("BatchMode=yes", calls[0])
        self.assertIn("StrictHostKeyChecking=accept-new", calls[0])

    def test_all_bootstrap_ssh_and_scp_use_batch_mode(self):
        # Every call site, including the long-lived waiter, must be noninteractive.
        text = (ROOT / "bg-bootstrap.sh").read_text()
        import re
        calls = re.findall(r"(?m)^\s*(?:ssh|scp)\s[^\n]*", text.replace("\\\n", " "))
        self.assertEqual(len(calls), 4)
        for call in calls:
            self.assertIn("BatchMode=yes", call)

    def test_stale_inherited_helper_is_reset_for_every_git_network_operation(self):
        marker = self.root / "stale-helper-used"
        stale = self.bin / "stale-helper"
        self.fake("stale-helper", f"#!/usr/bin/env bash\ntouch '{marker}'\nprintf 'username=stale\\npassword=stale\\n'\n")
        subprocess.run([REAL_GIT, "config", "--file", self.env["GIT_CONFIG_GLOBAL"],
                        "credential.helper", str(stale)], env=self.env, check=True)
        original = (self.home / "gitconfig").read_bytes()
        result = self.run_push(CHECK_CREDENTIALS="1", FAKE_REMOTE_HEAD="1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(marker.exists(), "inherited credential helper ran")
        self.assertEqual((self.home / "gitconfig").read_bytes(), original)
        networks = [call for call in self.calls() if any(x in call for x in ("fetch", "pull", "push"))]
        self.assertEqual({next(x for x in call if x in ("fetch", "pull", "push")) for call in networks},
                         {"fetch", "pull", "push"})
        for call in networks:
            self.assertIn("credential.helper=", call)
            self.assertTrue(any(x.startswith("credential.helper=store --file=") for x in call))
        self.assertNotIn("offline-test-password", self.git("config", "--local", "--list").stdout)
        self.assertEqual((self.project / "pipeline/.git-credentials").stat().st_mode & 0o777, 0o600)

    def test_project_credential_store_handles_spaces_in_project_path(self):
        target = self.root / "project with spaces"
        self.project.rename(target)
        self.project = target
        result = self.run_push(CHECK_CREDENTIALS="1", FAKE_REMOTE_HEAD="1", SSH_EXIT="1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("STATUS:PUSH_OK", result.stdout)
        self.assertFalse([call for call in self.calls() if call[0] in ("ssh", "scp")])

    def test_previously_staged_secret_artifacts_are_untracked_without_deleting_originals(self):
        paths = (".env", "pipeline/bootstrap-private.json", "pipeline/RESULT.md", "pipeline/HUMAN_REVIEW.md")
        for name in paths:
            self.write(name, "private")
            self.git("add", "--", name)
        result = self.run_push()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        files = self.git("ls-tree", "-r", "--name-only", "HEAD").stdout.splitlines()
        for name in paths:
            self.assertNotIn(name, files)
            self.assertEqual((self.project / name).read_text(), "private")

    def test_in_progress_git_operations_halt_without_modifying_state(self):
        for state in ("rebase-merge", "rebase-apply", "MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD"):
            with self.subTest(state=state):
                path = self.project / ".git" / state
                if state.startswith("rebase-"):
                    path.mkdir()
                    (path / "sentinel").write_text("operator-owned")
                else:
                    path.write_text(self.git("rev-parse", "HEAD").stdout)
                before = self.git("rev-parse", "HEAD").stdout
                result = self.run_push()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("STATUS:GIT_REBASE_CONFLICT", result.stdout)
                self.assertTrue(path.exists())
                self.assertEqual(self.git("rev-parse", "HEAD").stdout, before)
                if path.is_dir():
                    (path / "sentinel").unlink()
                    path.rmdir()
                else:
                    path.unlink()
        self.assertFalse([call for call in self.calls() if "--abort" in call])

    def test_staging_failure_is_fatal_before_commit_or_push(self):
        self.write("site.txt", "changed\n")
        head = self.git("rev-parse", "HEAD").stdout
        result = self.run_push(FAIL_ADD="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("STATUS:PUSH_FAILED", result.stdout)
        self.assertEqual(self.git("rev-parse", "HEAD").stdout, head)
        self.assertFalse([call for call in self.calls() if "push" in call])

    def test_stage_nonignored_candidates_and_exclude_private_archives(self):
        self.write(".gitignore", "ignored/\n")
        self.write("ignored/do-not-stage.txt", "ignored")
        self.write("normal file.txt", "ok")
        self.write("line\nbreak.txt", "ok")
        self.write(":(glob)literal.txt", "ok")
        self.write(".env", "offline secret")
        for folder in ("archive", "tooling-backup", "cms-roundtrip"):
            path = self.write(f"pipeline/{folder}/private.txt", "private backup")
            self.git("add", "--", str(path.relative_to(self.project)))
        private_reports = ("cms-staging.json", "cms-staging.json.bak", "cms-roundtrip-original.json",
                           "cms-roundtrip-original.json.bak", "03-cms-roundtrip.json", "03-cms-roundtrip-restore.json")
        for name in private_reports:
            self.write(f"pipeline/{name}", "private evidence")
            self.git("add", "--", f"pipeline/{name}")
        self.write("pipeline/public-manifest.json", "{}")
        self.git("commit", "-qm", "previously tracked private backups")
        self.write("pipeline/archive/new-private.txt", "private")
        self.write("site.txt", "changed")
        self.write("delete-me.txt", "old")
        self.git("add", "delete-me.txt")
        self.git("commit", "-qm", "deletion fixture")
        (self.project / "delete-me.txt").unlink()
        result = self.run_push()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        files = self.git("ls-tree", "-r", "--name-only", "-z", "HEAD").stdout.split("\0")
        self.assertIn("normal file.txt", files)
        self.assertIn("line\nbreak.txt", files)
        self.assertIn(":(glob)literal.txt", files)
        self.assertNotIn("delete-me.txt", files)
        self.assertFalse([f for f in files if f.startswith(("pipeline/archive/", "pipeline/tooling-backup/", "pipeline/cms-roundtrip/", "ignored/"))])
        for name in private_reports:
            self.assertNotIn(f"pipeline/{name}", files)
        self.assertIn("pipeline/public-manifest.json", files)
        self.assertNotIn(".env", files)
        self.assertTrue((self.project / "pipeline/archive/private.txt").exists())
        self.assertTrue((self.project / "pipeline/tooling-backup/private.txt").exists())

    def test_cms_gate_private_dotdirs_lock_attestation_and_report_never_published(self):
        private = ("pipeline/.cms-roundtrip-offline/recovery.json", "pipeline/.cms-roundtrip.lock", "pipeline/.cms-report-offline",
                   "pipeline/cms-staging.json", "pipeline/cms-roundtrip-report.json")
        for name in private:
            path = self.write(name, "offline recovery original")
            path.chmod(0o600)
            if name.endswith("/recovery.json"):
                path.parent.chmod(0o700)
            self.git("add", "--", name)
        self.git("commit", "-qm", "previously tracked CMS gate artifacts")
        untracked = self.write("pipeline/.cms-roundtrip-next/recovery.json", "next original")
        report_temp = self.write("pipeline/.cms-report-next", "next private report")
        self.write("pipeline/public-manifest.json", "{}")
        result = self.run_push()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        files = self.git("ls-tree", "-r", "--name-only", "HEAD").stdout.splitlines()
        for name in private:
            self.assertNotIn(name, files)
            self.assertEqual((self.project / name).read_text(), "offline recovery original")
            self.assertEqual((self.project / name).stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.project / private[0]).parent.stat().st_mode & 0o777, 0o700)
        self.assertNotIn(str(untracked.relative_to(self.project)), files)
        self.assertNotIn(str(report_temp.relative_to(self.project)), files)
        self.assertIn("pipeline/public-manifest.json", files)
        for name in (*private, str(untracked.relative_to(self.project)), str(report_temp.relative_to(self.project))):
            self.assertEqual(self.git("check-ignore", "--", name, check=False).returncode, 0)

    def test_bundle_transports_are_noninteractive(self):
        result = self.run_push(PUSH_EXIT="1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("STATUS:PUSH_OK method=remote_bundle_fallback", result.stdout)
        calls = [call for call in self.calls() if call[0] in ("ssh", "scp")]
        self.assertEqual({call[0] for call in calls}, {"ssh", "scp"})
        for call in calls:
            self.assertIn("BatchMode=yes", call)

    def test_bundle_handoff_is_readable_only_by_git_and_remote_git_has_deadline(self):
        result = self.run_push(PUSH_EXIT="1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        remote = next(call[-1] for call in self.calls() if call[0] == "ssh")
        # Both mktemp's 0700 directory and scp's 0600 bundle start SSH-user-owned.
        # The git user cannot clone them without this explicit private handoff.
        self.assertIn('sudo chown git "$TMP"', remote)
        self.assertIn("sudo chown git '/tmp/astro-static-push-", remote)
        self.assertIn("timeout", remote)
        self.assertIn("DEADLINE=", remote)

    def test_fresh_repository_untracks_private_files_after_remote_index_seed(self):
        self.write("pipeline/cms-staging.json", "private")
        self.git("add", "pipeline/cms-staging.json")
        self.git("commit", "-qm", "previous private attestation")
        seed = self.project
        config = (seed / "pipeline/vps-connection.json").read_text()
        self.project = self.root / "fresh-project"
        self.project.mkdir()
        self.write("pipeline/vps-connection.json", config)
        self.write("site.txt", "generated\n")
        result = self.run_push(FAKE_REMOTE_REPO=str(seed))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        files = self.git("ls-tree", "-r", "--name-only", "HEAD").stdout.splitlines()
        self.assertNotIn("pipeline/cms-staging.json", files)

    def test_ignored_tracked_changes_are_not_added(self):
        self.write("keep-local.txt", "original")
        self.git("add", "keep-local.txt")
        self.git("commit", "-qm", "tracked fixture")
        self.write(".gitignore", "keep-local.txt\n")
        self.write("keep-local.txt", "changed locally")
        result = self.run_push()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.git("show", "HEAD:keep-local.txt").stdout, "original")

    def test_overall_budget_also_bounds_preflight(self):
        started = time.monotonic()
        result = self.run_push(SLOW_CURL="1", ASTRO_STATIC_PUSH_BUDGET_SECONDS="2")
        self.assertLess(time.monotonic() - started, 6)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("STATUS:PUSH_TIMEOUT", result.stdout)
        self.assertFalse([call for call in self.calls() if "push" in call])

    def test_overall_budget_bounds_push_and_bundle_fallback(self):
        started = time.monotonic()
        result = self.run_push(SLOW_PUSH="1", SLOW_SCP="1",
                               ASTRO_STATIC_PUSH_BUDGET_SECONDS="5",
                               ASTRO_STATIC_PUSH_HTTP_SECONDS="1",
                               ASTRO_STATIC_PUSH_FALLBACK_SECONDS="1")
        self.assertLess(time.monotonic() - started, 9)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("STATUS:PUSH_TIMEOUT", result.stdout)
        self.assertEqual(len([call for call in self.calls() if "push" in call]), 1)

    def test_supervisor_timeout_terminates_descendants(self):
        helper = ROOT / "phases/operations-timeout.py"
        self.assertTrue(helper.exists(), "portable process-tree timeout helper missing")
        sentinel = self.root / "should-not-exist"
        command = f"(sleep 2; touch '{sentinel}') & wait"
        result = subprocess.run(["python3", str(helper), "1", "bash", "-c", command],
                                text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 124)
        time.sleep(2)
        self.assertFalse(sentinel.exists(), "timed-out descendant survived")

    def test_overall_supervisor_cancels_nested_command_groups(self):
        helper = ROOT / "phases/operations-timeout.py"
        sentinel = self.root / "nested-should-not-exist"
        result = subprocess.run(["python3", str(helper), "1", "python3", str(helper), "30",
                                 REAL_BASH, "-c", f"sleep 2; touch '{sentinel}'"],
                                text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 124)
        time.sleep(2)
        self.assertFalse(sentinel.exists(), "nested command escaped overall deadline")

    def test_cancellation_grace_survives_exiting_intermediate_bash(self):
        helper = ROOT / "phases/operations-timeout.py"
        pidfile = self.root / "resistant-child.pid"
        sentinel = self.root / "resistant-child-sentinel"
        payload = self.root / "resistant-child.py"
        payload.write_text('''import os, pathlib, signal, sys, time
signal.signal(signal.SIGTERM,signal.SIG_IGN)
pathlib.Path(sys.argv[1]).write_text(str(os.getpid()))
time.sleep(2.5)
pathlib.Path(sys.argv[2]).write_text('escaped cancellation')
time.sleep(30)
''')

        def cleanup():
            if pidfile.exists():
                try:
                    os.kill(int(pidfile.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass

        self.addCleanup(cleanup)
        # & wait prevents bash's final-command exec optimization. The inner
        # supervisor remains in bash's group; its resistant child is setsid.
        command = '"$1" "$2" 30 "$1" "$3" "$4" "$5" >/dev/null 2>&1 & wait'
        result = subprocess.run([sys.executable, str(helper), "1", REAL_BASH, "-c", command,
                                 "bash", sys.executable, str(helper), str(payload), str(pidfile), str(sentinel)],
                                text=True, capture_output=True, timeout=6)
        self.assertEqual(result.returncode, 124)
        self.assertTrue(pidfile.exists(), "resistant payload did not start")
        time.sleep(2)
        running = self.process_running(int(pidfile.read_text()))
        self.assertFalse(sentinel.exists() or running,
                         f"nested child escaped: sentinel={sentinel.exists()} running={running}")

    def test_remote_command_deadline_is_capped_by_remaining_overall_budget(self):
        driver, remote = self.remote_interpreter(connect_delay=.7, clone_seconds=.1, push_seconds=10)
        counter = self.root / "preparation-delay-done"
        self.fake("curl", f'''#!/usr/bin/env bash
if [ ! -f '{counter}' ]; then touch '{counter}'; sleep 2; fi
printf 200
''')
        started = time.time()
        result = self.run_push(PUSH_EXIT="1", ASTRO_STATIC_PUSH_BUDGET_SECONDS="7",
                               ASTRO_STATIC_PUSH_FALLBACK_SECONDS="12")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("STATUS:PUSH_TIMEOUT", result.stdout)
        try:
            driver.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.fail("remote command outlived the overall budget and cancellation grace")
        self.assertEqual(driver.returncode, 0, (remote / "driver.log").read_text())
        events = self.remote_events(remote)
        self.assertTrue([e for e in events if e["event"] == "push"], events)
        for timer in (e for e in events if e["event"] == "timer"):
            self.assertLessEqual(timer["at"] + timer["seconds"], started + 8)
        self.assertFalse((remote / "late-push-sentinel").exists())
        for event in (e for e in events if "pid" in e):
            self.assertFalse(self.process_running(event["pid"]), events)
        self.assertEqual(len([call for call in self.calls() if call[0] == "ssh"]), 1)

    def test_remote_connection_delay_consumes_fallback_budget(self):
        # Leave enough headroom for process startup and integer epoch rounding
        # under load. The 6s push exceeds the correct ~5s remaining allowance,
        # but would finish if a fresh 8s budget were started after connecting.
        driver, remote = self.remote_interpreter(connect_delay=3, clone_seconds=.05, push_seconds=6)
        result = self.run_push(PUSH_EXIT="1", ASTRO_STATIC_PUSH_FALLBACK_SECONDS="8")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("STATUS:PUSH_TIMEOUT", result.stdout)
        driver.wait(timeout=4)
        self.assertEqual(driver.returncode, 0, (remote / "driver.log").read_text())
        events = self.remote_events(remote)
        self.assertTrue([e for e in events if e["event"] == "push"], events)
        self.assertFalse((remote / "late-push-sentinel").exists(),
                         "SSH connection delay reset the remote push allowance")
        for event in (e for e in events if "pid" in e):
            self.assertFalse(self.process_running(event["pid"]), events)

    def test_remote_command_delivered_after_deadline_does_not_clone_or_push(self):
        driver, remote = self.remote_interpreter(connect_delay=5)
        result = self.run_push(PUSH_EXIT="1", ASTRO_STATIC_PUSH_BUDGET_SECONDS="4",
                               ASTRO_STATIC_PUSH_FALLBACK_SECONDS="12")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("STATUS:PUSH_TIMEOUT", result.stdout)
        driver.wait(timeout=6)
        self.assertEqual(driver.returncode, 0, (remote / "driver.log").read_text())
        self.assertEqual(self.remote_events(remote), [], "expired remote command still ran git")
        self.assertEqual(json.loads((remote / "response.json").read_text()), 124)

    def test_internal_absolute_deadline_is_validated_before_operations(self):
        for deadline in ("not-a-deadline", str(int(time.time()) + 10000)):
            with self.subTest(deadline=deadline):
                result = subprocess.run(["bash", str(ROOT / "phases/push-gitea.sh"),
                                         "--budget-child", deadline], cwd=self.project,
                                        env=self.env, text=True, capture_output=True, timeout=20)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("STATUS:INVALID_VPS_CONFIG", result.stdout)
        self.assertEqual(self.calls(), [])

    def test_retry_can_check_missing_log_under_errexit_and_pipefail(self):
        result = subprocess.run(["bash", "-euo", "pipefail", "-c",
                                 'source "$1"; should_retry_line phase5 "STATUS:PUSH_TIMEOUT"; echo RETRY_OK',
                                 "bash", str(ROOT / "phases/retry.sh")],
                                cwd=self.project, env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "RETRY_OK")

    def test_invalid_budget_rejected_before_network(self):
        result = self.run_push(ASTRO_STATIC_PUSH_BUDGET_SECONDS="not-a-number")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("STATUS:INVALID_VPS_CONFIG", result.stdout)
        self.assertEqual(self.calls(), [])

    def test_retry_line_helper_owns_portable_signature_and_legacy_api(self):
        # A missing sha256sum is normal on macOS. shasum must be sufficient.
        self.fake("sha256sum", "#!/usr/bin/env bash\nexit 127\n")
        line = "STATUS:PUSH_TIMEOUT after=5"
        signature = hashlib.sha256(line.encode()).hexdigest()[:16]
        script = '''source "$1"
append_retry phase5 "$2" || exit 10
should_retry phase5 "$3" || exit 11
should_retry_line phase5 "$2" || exit 12
append_retry phase5 "$2" || exit 13
if should_retry_line phase5 "$2"; then exit 14; fi
if should_retry phase5 "$3"; then exit 15; fi
'''
        result = subprocess.run(["bash", "-c", script, "bash", str(ROOT / "phases/retry.sh"), line, signature],
                                cwd=self.project, env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([row.split("\t")[3] for row in (self.project / "pipeline/retry.log").read_text().splitlines()],
                         [signature, signature])


if __name__ == "__main__":
    unittest.main()
