#!/usr/bin/env python3
"""Execute bootstrap heredocs locally, never the system/VPS bootstrap phases.

Node security tests need TypeScript and GraphQL already installed in a project:
SCAFFOLD_NODE_MODULES=/path/to/project/node_modules python3 test_scaffold_hardening.py
"""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
TEMP = Path(tempfile.gettempdir())
MODULES = Path(os.environ.get("SCAFFOLD_NODE_MODULES", str(ROOT / "node_modules")))
SITE = "https://demo.185.18.221.225.sslip.io"


class ScaffoldHardeningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="scaffold-hardening-", dir=TEMP)
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.setup = (ROOT / "setup-vps.sh").read_text()
        # Execute only the pure project-generation shell section, before install.
        start = self.setup.index("  cat > package.json")
        # Include any scaffold-specific umask preceding the first heredoc.
        start = self.setup.rfind('  cd "${SITE_DIR}"', 0, start)
        end = self.setup.index("  bun install --silent", start)
        self.scaffold = self.setup[start:end]
        self.generate(SITE)

    def generate(self, site, mode='admin-blocks'):
        result = subprocess.run(["bash", "-euc", "umask 077\n" + self.scaffold], cwd=self.project,
                                env={**os.environ, "SITE_DIR": str(self.project), "SITE_URL": site, "TINA_EDITING_MODE": mode},
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def node(self, source):
        result = subprocess.run(["node", "--input-type=module", "-e", source], cwd=self.project,
                                env={**os.environ, "FIXTURE_PROJECT": str(self.project),
                                     "FIXTURE_MODULES": str(MODULES), "FIXTURE_SITE": SITE},
                                text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_default_admin_blocks_scaffold_has_no_preview_router_or_island_endpoint(self):
        self.assertNotIn('router:', (self.project / 'tina/config.ts').read_text())
        self.assertFalse((self.project / 'src/pages/tina-island/[name].ts').exists())

    def test_explicit_overlay_scaffold_retains_router_and_post_endpoint(self):
        self.generate(SITE, 'overlay')
        self.assertIn('router:', (self.project / 'tina/config.ts').read_text())
        route = self.project / 'src/pages/tina-island/[name].ts'
        self.assertTrue(route.exists())
        self.assertIn('export const POST', route.read_text())
        self.assertNotIn('export const ALL', route.read_text())

    def test_resolved_public_site_is_astro_config_site(self):
        for site in [SITE, "https://custom.example.org", "http://192.168.1.10:8081"]:
            with self.subTest(site=site):
                self.generate(site)
                self.node("""
import fs from 'node:fs'; import vm from 'node:vm'; import assert from 'node:assert/strict';
let source = fs.readFileSync('astro.config.mjs', 'utf8').replace(/^import .*;$/gm, '').replace('export default', 'result =');
const stub = () => ({}); const context = { URL, process: {env:{}}, defineConfig: x => x, node: stub, react: stub, mdx: stub, tina: stub, sitemap: stub, tailwindcss: stub, tinaAdminDevRedirect: stub };
vm.runInNewContext(source, context);
assert.equal(context.result.site, """ + json.dumps(site) + ");")

    def test_dependency_matrix_is_pinned_to_observed_project_versions(self):
        package = json.loads((self.project / "package.json").read_text())
        actual = {**package["dependencies"], **package["devDependencies"]}
        expected = {"astro": "7.4.7", "@astrojs/node": "11.1.11", "@astrojs/react": "6.0.6",
                    "@astrojs/mdx": "7.0.8", "@astrojs/check": "0.9.12", "@tinacms/astro": "0.5.1",
                    "@tinacms/cli": "2.7.0", "@tinacms/datalayer": "2.0.29", "@tinacms/graphql": "2.4.11",
                    "@emnapi/runtime": "1.11.3", "graphql": "16.15.0", "tinacms": "3.15.1",
                    "react": "19.3.1", "react-dom": "19.3.1", "tailwindcss": "4.3.5",
                    "@tailwindcss/vite": "4.3.5", "@types/react": "19.3.0", "@types/react-dom": "19.3.0"}
        for name, version in expected.items():
            self.assertEqual(actual.get(name), version, name)
        for name, version in actual.items():
            self.assertRegex(version, r"^\d+\.\d+\.\d+$", name)
        caveat = (self.project / "DEPENDENCY-COMPATIBILITY.md")
        self.assertTrue(caveat.exists(), "scaffold must disclose unsupported Astro 7 Tina peer range")
        self.assertIn("^5.0.0 || ^6.0.0", caveat.read_text())

    def test_staging_origin_can_differ_without_mutating_source(self):
        self.node("""
import fs from 'node:fs'; import vm from 'node:vm'; import assert from 'node:assert/strict';
const source=fs.readFileSync('astro.config.mjs','utf8').replace(/^import .*;$/gm,'').replace('export default','result =');
const stub=()=>({});
const config=env=>{const context={URL,process:{env},defineConfig:x=>x,node:stub,react:stub,mdx:stub,tina:stub,sitemap:stub,tailwindcss:stub,tinaAdminDevRedirect:stub};vm.runInNewContext(source,context);return context.result;};
assert.equal(config({}).site, process.env.FIXTURE_SITE);
assert.equal(config({ASTRO_STAGING_SITE_URL:'https://ignored.invalid'}).site, process.env.FIXTURE_SITE);
const staging=config({ASTRO_DEPLOYMENT_ENVIRONMENT:'staging',ASTRO_STAGING_SITE_URL:'https://approved-staging.example.test'});
assert.equal(staging.site,'https://approved-staging.example.test');
assert.equal(staging.security.allowedDomains[0].hostname,'approved-staging.example.test');
assert.throws(()=>config({ASTRO_DEPLOYMENT_ENVIRONMENT:'staging'}));
""")

    def test_login_source_is_durable_and_public_files_are_readable(self):
        source = self.project / "public/admin/login.html"
        self.assertTrue(source.is_file(), "Tina build must not be the only owner of login.html")
        self.assertEqual(source.read_bytes(), (self.project / "admin/login.html").read_bytes())
        for path in self.project.rglob("*"):
            self.assertEqual(path.stat().st_mode & 0o777, 0o755 if path.is_dir() else 0o644, str(path))

    def test_package_tina_build_restores_the_durable_login(self):
        package = json.loads((self.project / 'package.json').read_text())
        fake = self.project / 'fake-bin'
        fake.mkdir()
        cli = fake / 'tinacms'
        cli.write_text('#!/bin/sh\n# Simulate Tina emptyOutDir in this disposable fixture only.\nfind admin -type f -delete\nprintf "generated" > admin/index.html\n')
        cli.chmod(0o700)
        result = subprocess.run(['sh', '-c', package['scripts']['tinacms:build']], cwd=self.project,
                                env={**os.environ, 'PATH': str(fake) + os.pathsep + os.environ['PATH']},
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.project / 'admin/login.html').is_file())
        self.assertEqual((self.project / 'admin/login.html').read_bytes(), (self.project / 'public/admin/login.html').read_bytes())

    def test_only_the_canonical_proxy_host_enables_distinct_client_addresses(self):
        if not (MODULES / 'astro/package.json').is_file():
            self.skipTest('Set SCAFFOLD_NODE_MODULES for real Astro proxy-address verification')
        self.node("""
import fs from 'node:fs'; import vm from 'node:vm'; import assert from 'node:assert/strict';
import { Socket } from 'node:net'; import { IncomingMessage } from 'node:http';
const { createRequestFromNodeRequest } = await import(process.env.FIXTURE_MODULES + '/astro/dist/core/app/node.js');
const { clientAddressSymbol } = await import(process.env.FIXTURE_MODULES + '/astro/dist/core/constants.js');
let source = fs.readFileSync('astro.config.mjs', 'utf8').replace(/^import .*;$/gm, '').replace('export default', 'result =');
const stub = () => ({}); const context = { URL, process: {env:{}}, defineConfig:x=>x, node:stub, react:stub, mdx:stub, tina:stub, sitemap:stub, tailwindcss:stub, tinaAdminDevRedirect:stub };
vm.runInNewContext(source, context);
const allowedDomains = context.result.security?.allowedDomains || [];
assert.equal(allowedDomains.length, 1);
assert.equal(allowedDomains[0].hostname, new URL(process.env.FIXTURE_SITE).hostname);
const request = (ip, host) => { const req = new IncomingMessage(new Socket()); req.method='GET'; req.url='/api/tina/auth-check'; req.headers={host,'x-forwarded-host':host,'x-forwarded-proto':'https','x-forwarded-for':ip}; Object.defineProperty(req.socket,'remoteAddress',{value:'127.0.0.1'}); return createRequestFromNodeRequest(req,{skipBody:true,allowedDomains}); };
const host = new URL(process.env.FIXTURE_SITE).hostname;
assert.equal(request('198.51.100.10',host)[clientAddressSymbol], '198.51.100.10');
assert.equal(request('198.51.100.11',host)[clientAddressSymbol], '198.51.100.11');
assert.equal(request('198.51.100.10','hostile.invalid')[clientAddressSymbol], '127.0.0.1');
""")

    def test_sessions_reject_all_malformed_tampered_expired_and_future_tokens(self):
        self.assertTrue((self.project / "src/lib/tina/session.mjs").exists(), "signed nonce-bearing session module missing")
        self.node("""
import assert from 'node:assert/strict'; import { createHmac } from 'node:crypto';
const { createSession, validSession, sessionCookie, SESSION_COOKIE, SESSION_MAX_AGE_SECONDS } = await import(process.env.FIXTURE_PROJECT + '/src/lib/tina/session.mjs');
const secret = 'fixture-only-password'; const now = 1700000000000;
const raw = createSession(secret, now); const cookie = value => `${SESSION_COOKIE}=${value}`;
assert.notEqual(raw, createSession(secret, now));
assert.equal(validSession(cookie(raw), secret, now), true);
assert.equal(validSession(cookie(encodeURIComponent(raw)), secret, now), true);
assert.equal(validSession(cookie(raw), 'wrong', now), false);
assert.equal(validSession(cookie(raw), '', now), false);
assert.equal(validSession(cookie(raw), secret, now - 1), false);
assert.equal(validSession(cookie(raw), secret, now + SESSION_MAX_AGE_SECONDS * 1000 + 1), false);
for (const value of [raw + '0', raw + '.', raw + '.extra', '%invalid', '', 'NaN.nonce.sig', 'Infinity.x.y']) assert.equal(validSession(cookie(value), secret, now), false, value);
const signed = payload => payload + '.' + createHmac('sha256', secret).update(payload).digest('hex');
for (const payload of [`${now}.`, `${now}.not-a-random-nonce`, `1e3.${'a'.repeat(48)}`, `0${now}.${'a'.repeat(48)}`]) assert.equal(validSession(cookie(signed(payload)), secret, now), false, payload);
assert.equal(validSession(cookie(raw) + '; ' + cookie(raw), secret, now), false);
assert.throws(() => createSession(''));
assert.match(sessionCookie(raw, true), /; HttpOnly; SameSite=Lax; Secure$/);
assert.match(sessionCookie('', true), /Max-Age=0; HttpOnly; SameSite=Lax; Secure$/);
assert.doesNotMatch(sessionCookie(raw, false), /; Secure/);
""")

    def test_policy_uses_trusted_origin_not_forwarded_or_internal_transport(self):
        self.assertTrue((self.project / "src/lib/tina/request-policy.mjs").exists(), "trusted-origin policy module missing")
        self.node("""
import assert from 'node:assert/strict';
const { requestPolicy } = await import(process.env.FIXTURE_PROJECT + '/src/lib/tina/request-policy.mjs');
const site = process.env.FIXTURE_SITE;
const req = (origin, extra = {}, url = 'http://127.0.0.1:4321/api/tina/gql') => new Request(url, { method: 'POST', headers: { ...(origin === undefined ? {} : { origin }), ...extra } });
assert.deepEqual(requestPolicy(req(site), site, false), { error: undefined, secure: true });
assert.equal(requestPolicy(req(undefined), site, false).error, undefined);
for (const origin of ['null', 'https://hostile.invalid', 'http://127.0.0.1:4321', site + '.hostile.invalid']) assert.ok(requestPolicy(req(origin, { 'x-forwarded-host': 'hostile.invalid', 'x-forwarded-proto': 'https', forwarded: 'host=hostile.invalid;proto=https' }), site, false).error);
assert.ok(requestPolicy(req(site, { 'sec-fetch-site': 'cross-site' }), site, false).error);
for (const invalid of ['', undefined, 'null', 'file:///path', 'https://user:password@example.org']) assert.equal(requestPolicy(req(undefined), invalid, false).error, 'Editor origin not configured');
const local = req('http://localhost:4321', {}, 'http://localhost:4321/api/tina/login');
assert.deepEqual(requestPolicy(local, site, true), { error: undefined, secure: false });
assert.ok(requestPolicy(local, site, false).error);
assert.ok(requestPolicy(req('http://hostile.invalid', {}, 'http://hostile.invalid/api/tina/login'), site, true).error);
assert.equal(requestPolicy(req('http://192.168.1.10:8081'), 'http://192.168.1.10:8081', false).secure, false);
""")

    def test_actual_auth_handler_security_and_graphql_dispatch(self):
        # Only database execution is isolated. Real generated TS, GraphQL parser,
        # session/policy modules and Node HTTP adapter run in Node.
        if not (MODULES / 'typescript/package.json').is_file() or not (MODULES / 'graphql/package.json').is_file():
            self.skipTest('Set SCAFFOLD_NODE_MODULES to installed scaffold dependencies for endpoint execution')
        self.node("""
import fs from 'node:fs'; import vm from 'node:vm'; import { createRequire } from 'node:module'; import assert from 'node:assert/strict';
const require = createRequire(process.env.FIXTURE_MODULES + '/fixture.cjs');
const realTinaBackend = await import(process.env.FIXTURE_MODULES + '/@tinacms/datalayer/dist/index.js');
const ts = require('typescript'); const project = process.env.FIXTURE_PROJECT; const site = process.env.FIXTURE_SITE;
const helpers = {};
for (const name of ['session', 'request-policy']) if (fs.existsSync(`${project}/src/lib/tina/${name}.mjs`)) helpers[name] = await import(`${project}/src/lib/tina/${name}.mjs`);
const source = fs.readFileSync(`${project}/src/pages/api/tina/[...routes].ts`, 'utf8').replaceAll('import.meta.env.SITE', JSON.stringify(site)).replaceAll('import.meta.env.DEV', 'false');
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } });
const exports = {}; let dispatched = 0;
const environment = { TINA_ADMIN_PASSWORD: 'fixture-only-password' };
vm.runInNewContext(outputText, { exports, Buffer, URL, Headers, Response, setTimeout, clearTimeout, console, process: { env: environment }, require: name => {
  if (name.endsWith('/session.mjs')) return helpers.session;
  if (name.endsWith('/request-policy.mjs')) return helpers['request-policy'];
  if (name.endsWith('/databaseClient')) return { __esModule: true, default: { request: async () => { dispatched++; return { data: { __typename: 'Query' } }; } } };
  if (name === '@tinacms/datalayer') return realTinaBackend;
  return require(name);
} });
const send = (path, { method = 'POST', origin = site, body, cookie, headers = {}, address = 'fixture' } = {}) => exports.ALL({ clientAddress: address, request: new Request('http://127.0.0.1:4321/api/tina/' + path, { method, headers: { ...(origin === undefined ? {} : { origin }), 'Content-Type': 'application/json', ...(cookie ? { cookie } : {}), ...headers }, ...(body === undefined ? {} : { body: typeof body === 'string' ? body : JSON.stringify(body) }) }) });
const login = await send('login', { body: { password: environment.TINA_ADMIN_PASSWORD } });
assert.equal(login.status, 200); assert.match(login.headers.get('set-cookie'), /; Secure$/);
assert.equal(login.headers.get('cache-control'), 'no-store');
const cookie = login.headers.get('set-cookie').split(';')[0];
assert.equal((await send('auth-check', { method: 'GET', cookie })).status, 200);
assert.equal((await send('auth-check', { method: 'GET' })).status, 401);
assert.equal((await send('gql', { body: { query: '{ __typename }' } })).status, 400);
assert.equal((await send('gql', { body: { query: '{ __typename }', variables: {} } })).status, 200);
assert.equal((await send('gql?query=%7B__typename%7D', { method: 'GET' })).status, 405);
assert.equal((await send('gql', { body: { query: 'mutation { updatePage { id } }' } })).status, 401);
assert.equal((await send('gql', { body: { query: 'query Read { __typename } mutation Write { updatePage { id } }', operationName: 'Write' } })).status, 401);
assert.equal((await send('gql', { body: { query: 'fragment F on Query { __typename }' } })).status, 401);
assert.equal((await send('gql?query=mutation%20%7BupdatePage%7Bid%7D%7D', { method: 'GET', cookie })).status, 405);
assert.equal((await send('gql', { body: { query: 'mutation { updatePage { id } }', variables: {} }, cookie })).status, 200);
const before = dispatched;
for (const path of ['login', 'logout', 'gql']) {
  assert.equal((await send(path, { origin: 'https://hostile.invalid', body: {}, cookie, headers: { 'x-forwarded-host': 'hostile.invalid', 'x-forwarded-proto': 'https' } })).status, 403);
  assert.equal((await send(path, { body: {}, cookie, headers: { 'sec-fetch-site': 'cross-site' } })).status, 403);
}
assert.equal(dispatched, before);
assert.equal((await send('login', { body: '{invalid' })).status, 400);
assert.equal((await send('login', { body: { password: 'x'.repeat(5000) } })).status, 413);
assert.equal((await send('gql', { body: {}, headers: { 'content-length': '1048577' } })).status, 413);
for (let i = 0; i < 10; i++) assert.equal((await send('login', { body: { password: 'wrong' }, address: 'limited', headers: { 'x-forwarded-for': String(i) } })).status, 401);
assert.equal((await send('login', { body: { password: environment.TINA_ADMIN_PASSWORD }, address: 'limited' })).status, 429);
const logout = await send('logout'); assert.equal(logout.status, 200); assert.match(logout.headers.get('set-cookie'), /Max-Age=0; HttpOnly; SameSite=Lax; Secure$/);
environment.TINA_ADMIN_PASSWORD = '';
assert.equal((await send('login', { body: { password: '' } })).status, 401);
""")

    def test_private_ip_routing_does_not_claim_https(self):
        start = self.setup.index('_is_public_ip()')
        end = self.setup.index('SITE_DIR="/var/www/sites/', start)
        script = self.setup[start:end] + '\nprintf "%s\\n" "$SITE_URL" "$USE_TLS"\n'
        result = subprocess.run(["bash", "-euc", script], text=True, capture_output=True,
                                env={**os.environ, "DOMAIN": "auto", "SERVER_IP": "192.168.1.10",
                                     "PROJECT_PORT": "8081", "PROJECT_NAME": "fixture"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["http://192.168.1.10:8081", "false"])


if __name__ == "__main__":
    unittest.main()
