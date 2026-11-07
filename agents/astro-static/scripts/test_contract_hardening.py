#!/usr/bin/env python3
"""Canonical contracts: editing modes, installed dependency graph and safe handoff."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AGENTS = ROOT.parent if (ROOT.parent / 'schemas').exists() else ROOT.parent / 'agents/astro-static'
COMMANDS = AGENTS.parent.parent / 'commands/astro-static'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


validator = load('contract_validator', ROOT / 'validate-pipeline.py')
regressions = load('contract_fixture_helpers', ROOT / 'test_regressions.py')


class ContractHardeningTests(unittest.TestCase):
    def fixture(self, project, mode='admin-blocks'):
        helper = regressions.AstroStaticRegressionTests()
        helper._write_minimal_tina_project(project)
        path = project / 'pipeline/01-tina-blueprint.json'
        doc = json.loads(path.read_text())
        doc['editing_mode'] = mode
        path.write_text(json.dumps(doc))

    def router_issues(self, router, mode='admin-blocks'):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self.fixture(project, mode)
            config = project / 'tina/config.ts'
            text = config.read_text()
            text = text.replace('router: () => "/"', router)
            config.write_text(text)
            issues, _ = validator.validate_project(project, 'build', False)
            return [i for i in issues if 'router' in i.message]

    def test_admin_blocks_allows_omitted_or_undefined_router(self):
        for router in ('', 'router: undefined'):
            with self.subTest(router=router):
                self.assertEqual(self.router_issues(router), [])

    def test_admin_blocks_rejects_all_router_functions(self):
        for router in ('router: () => "/"', 'router : function () { return "/"; }',
                       'router() { return undefined; }', 'router: routeForDocument',
                       'router: undefined || (() => "/")'):
            with self.subTest(router=router):
                self.assertTrue(self.router_issues(router))

    def test_overlay_keeps_router_and_metadata_requirements(self):
        self.assertTrue(self.router_issues('', 'overlay'))
        self.assertTrue(self.router_issues('router: undefined', 'overlay'))
        self.assertEqual(self.router_issues('router: () => "/"', 'overlay'), [])
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self.fixture(project, 'overlay')
            for path in (project / 'src').rglob('*'):
                if path.is_file():
                    path.write_text(path.read_text().replace('requestWithMetadata', 'removedLoader'))
            issues, _ = validator.validate_project(project, 'build', False)
            self.assertTrue(any('requestWithMetadata' in i.message for i in issues))

    def test_admin_blocks_missing_coverage_is_not_required_at_any_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self.fixture(project)
            (project / 'pipeline/03-tina-coverage.json').unlink()
            for phase, all_ in (('build', False), ('final', False), (None, True)):
                issues, _ = validator.validate_project(project, phase, all_)
                self.assertFalse([i for i in issues if i.artifact == '03-tina-coverage.json'])

    def test_durable_login_source_is_required_at_final_deployment_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self.fixture(project)
            issues, _ = validator.validate_project(project, 'final', False)
            self.assertTrue(any(i.artifact == 'public/admin/login.html' for i in issues))
            login = project / 'public/admin/login.html'
            login.parent.mkdir(parents=True, exist_ok=True)
            login.write_text('<form><input type="password"><script>fetch("/api/tina/login")</script></form>')
            issues, _ = validator.validate_project(project, 'final', False)
            self.assertFalse([i for i in issues if i.artifact == 'public/admin/login.html'])

    def test_video_warning_suppression_requires_explicit_no_and_skipped_phase(self):
        for no_video, state, suppressed in ((False, 'skipped', True), (False, 'not_requested', True),
                                             (None, 'skipped', False), (True, 'skipped', False),
                                             (False, 'failed', False), (False, None, False)):
            with self.subTest(video_backgrounds=no_video, status=state), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp)
                self.fixture(project)
                pipeline = project / 'pipeline'
                brief = json.loads((pipeline / '01-creative-brief.json').read_text())
                brief['motion_direction'] = {'video_backgrounds': no_video}
                (pipeline / '01-creative-brief.json').write_text(json.dumps(brief))
                (pipeline / '00-pipeline-state.json').write_text(json.dumps({
                    'phases': {'3_6_video_generation': {'status': state}}}))
                issues, _ = validator.validate_project(project, 'build', False)
                warnings = [i for i in issues if i.artifact == '02-video-shot-list.json']
                self.assertEqual(not warnings, suppressed)

    def test_installed_graphql_must_satisfy_cli_and_datalayer(self):
        for cli_range, layer_range, version, passes in (
            ('^2.4.11', '^2.4.9', '2.4.11', True),
            ('^2.4.11', '^2.4.9', '2.4.9', False),
            ('^1.0.0', '^2.4.9', '2.4.11', False),
            ('>=2.4.9 <2.4.11', '^2.4.11', '2.4.11', False),
        ):
            with self.subTest(cli=cli_range, datalayer=layer_range, graphql=version), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp)
                self.fixture(project)
                for name, data in {
                    '@tinacms/cli': {'version': '2.7.0', 'dependencies': {'@tinacms/graphql': cli_range}},
                    '@tinacms/datalayer': {'version': '2.0.29', 'dependencies': {'@tinacms/graphql': layer_range}},
                    '@tinacms/graphql': {'version': version},
                }.items():
                    path = project / 'node_modules' / name / 'package.json'
                    path.parent.mkdir(parents=True)
                    path.write_text(json.dumps({'name': name, **data}))
                # Use a local Node installation's semver, never install global dependencies.
                search_paths = [str(ROOT)]
                if os.environ.get('SCAFFOLD_NODE_MODULES'):
                    search_paths.append(os.environ['SCAFFOLD_NODE_MODULES'])
                result = subprocess.run(['node', '-p',
                    'require.resolve("semver/package.json", {paths: ' + json.dumps(search_paths) + '})'],
                                        text=True, capture_output=True)
                if result.returncode:
                    self.skipTest('local Node semver not available')
                (project / 'node_modules/semver').symlink_to(Path(result.stdout.strip()).parent, target_is_directory=True)
                issues = []
                self.assertTrue(hasattr(validator, 'validate_installed_tina_matrix'), 'installed matrix validation is missing')
                validator.validate_installed_tina_matrix(project, issues)
                self.assertEqual(not [i for i in issues if i.level == 'error'], passes, issues)
                asset_issues, _ = validator.validate_project(project, 'assets', False)
                self.assertEqual(not [i for i in asset_issues if i.level == 'error' and 'installed' in i.message], passes)

    def test_decoupled_example_omits_preview_router_and_unsupported_template_item_props(self):
        config = (AGENTS / 'references/decoupled-blocks/tina/config.ts').read_text()
        self.assertNotIn('router:', config)
        template_ui = config.split('templates: [', 1)[0]
        self.assertNotIn('itemProps:', template_ui)

    def test_wizard_skip_is_schema_valid_and_explicit(self):
        text = (COMMANDS / 'new-site.md').read_text()
        self.assertIn('instagram_use: "skip"', text)
        schema = json.loads((AGENTS / 'schemas/00-brief.schema.json').read_text())
        self.assertIn('skip', schema['properties']['instagram_use']['enum'])
        self.assertIn('never invent business facts', text)

    def test_strict_cms_evidence_is_final_only_and_legacy_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self.fixture(project)
            pipeline = project / 'pipeline'
            brief_path = pipeline / '00-brief.json'
            brief = json.loads(brief_path.read_text())
            for required, phase, expected in ((False, 'final', False), (True, 'build', False), (True, 'final', True)):
                brief['validation_requirements'] = {'cms_roundtrip': required}
                brief_path.write_text(json.dumps(brief))
                issues, _ = validator.validate_project(project, phase, False)
                self.assertEqual(any(i.artifact == 'cms-roundtrip-report.json' for i in issues), expected)

    def test_strict_cms_evidence_is_bound_to_source_and_deployment(self):
        self.assertTrue(hasattr(validator, 'cms_source_revision'), 'source-bound CMS evidence validation missing')
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self.fixture(project)
            pipeline = project / 'pipeline'
            brief_path = pipeline / '00-brief.json'
            brief = json.loads(brief_path.read_text())
            revision = validator.cms_source_revision(project)
            brief['validation_requirements'] = {'cms_roundtrip': True, 'cms_source_revision': revision,
                                                 'cms_target_site_url': 'https://site.example.test'}
            brief_path.write_text(json.dumps(brief))
            binding = {'origin': 'https://staging.example.test', 'source_revision': revision}
            report = {'schema_version': 'astro-static-cms-roundtrip/v1', 'status': 'PASS',
                      'environment': 'staging', 'operator_authorized': True, 'recovery_path': None,
                      'mutation_outcome': 'CONFIRMED', **binding,
                      'phases': {phase: {'status': 'PASS'} for phase in (
                          'preflight', 'authenticate', 'baseline', 'backup', 'save', 'persist',
                          'live', 'restore', 'restore_persist', 'restore_live', 'source_revision')},
                      'evidence': {'original_sha256': 'a' * 64, 'saved_sha256': 'b' * 64,
                                   'restored_sha256': 'a' * 64,
                                   'rebuild_proof': 'persisted_settings_and_changed_live_header_html'}}
            attestation = {'schema_version': 'astro-static-cms-staging/v1', 'environment': 'staging',
                           'authorized_by_operator': True, 'site_url': binding['origin'], 'source_revision': revision}
            browser = {'schema_version': 'astro-static-cms-browser/v1', 'status': 'PASS',
                       'origin': 'https://site.example.test', 'source_revision': revision,
                       'authenticated': True, 'document_form': True, 'navigation': True,
                       'browser': 'actual-browser-session-reference'}
            connection_path = pipeline / 'vps-connection.json'
            connection = json.loads(connection_path.read_text())
            connection['site_url'] = 'https://site.example.test'
            connection['deployment'] = {'site_url': connection['site_url'], 'source_revision': revision}
            connection_path.write_text(json.dumps(connection))
            for filename, doc in (('cms-roundtrip-report.json', report), ('cms-staging.json', attestation),
                                  ('cms-browser-evidence.json', browser)):
                (pipeline / filename).write_text(json.dumps(doc))
                (pipeline / filename).chmod(0o600)
            def evidence_errors():
                issues, _ = validator.validate_project(project, 'final', False)
                return [i for i in issues if i.artifact.startswith('cms-')]
            self.assertEqual(evidence_errors(), [])  # synthetic fixtures are not real site evidence
            # Tina may reformat JSON without changing the restored source identity.
            # Raw byte hashes need not match; canonical source_revision must match.
            reformatted = {**report, 'evidence': {**report['evidence'], 'restored_sha256': 'c' * 64}}
            (pipeline / 'cms-roundtrip-report.json').write_text(json.dumps(reformatted))
            self.assertEqual(evidence_errors(), [])
            (pipeline / 'cms-roundtrip-report.json').write_text(json.dumps(report))
            for key, value in (('status', 'UNVERIFIED'), ('source_revision', 'sha256:' + '0' * 64),
                               ('mutation_outcome', 'INDETERMINATE'),
                               ('origin', 'https://elsewhere.example.test'), ('recovery_path', 'pending-recovery')):
                with self.subTest(key=key):
                    (pipeline / 'cms-roundtrip-report.json').write_text(json.dumps({**report, key: value}))
                    self.assertTrue(evidence_errors())
            (pipeline / 'cms-roundtrip-report.json').write_text(json.dumps(report))
            (pipeline / 'cms-roundtrip-report.json').chmod(0o644)
            self.assertTrue(evidence_errors())
            (pipeline / 'cms-roundtrip-report.json').chmod(0o600)
            recovery = pipeline / '.cms-roundtrip-test'
            recovery.mkdir()
            (recovery / 'recovery.json').write_text('{}')
            self.assertTrue(evidence_errors())
            (recovery / 'recovery.json').unlink()
            recovery.rmdir()
            (pipeline / 'cms-browser-evidence.json').unlink()
            self.assertTrue(evidence_errors())
            (pipeline / 'cms-browser-evidence.json').write_text(json.dumps(browser))
            (project / 'src/components/New.astro').write_text('<p>changed source</p>')
            self.assertTrue(evidence_errors())

    def test_agents_require_real_browser_and_staging_evidence(self):
        for name in ('frontend-builder', 'build-deployer', 'orchestrator'):
            text = (AGENTS / (name + '.md')).read_text()
            self.assertIn('real browser', text)
            self.assertIn('CMS persistence UNVERIFIED', text)
            self.assertIn('no production content mutations', text)
        for name in ('build-deployer', 'orchestrator'):
            text = (AGENTS / (name + '.md')).read_text()
            self.assertIn('cms-roundtrip.py --environment staging --allow-write', text)
            self.assertIn('TINA_ADMIN_PASSWORD', text)
            self.assertIn('pipeline/cms-staging.json', text)
            self.assertIn('source_revision', text)
            self.assertIn('authorized_by_operator', text)

    def test_orchestrator_tracks_advisories_and_never_prints_credentials(self):
        text = (AGENTS / 'orchestrator.md').read_text()
        self.assertIn('Warnings/advisories', text)
        self.assertIn('tracked follow-up', text)
        self.assertNotIn('credentials may be shown', text)
        self.assertIn('pbcopy', text)
        self.assertIn('620 seconds', text)

    def test_codegen_preserves_security_and_reference_pins(self):
        frontend = (AGENTS / 'frontend-builder.md').read_text()
        for value in ('session.mjs', 'request-policy.mjs', 'security.allowedDomains',
                      '127.0.0.1', 'no wildcard', 'clientAddress', '12-hour', 'HMAC'):
            self.assertIn(value, frontend)
        reference = (AGENTS / 'references/reference-stack.md').read_text()
        for value in ('astro@7.4.7', 'tinacms@3.15.1', '@tinacms/cli@2.7.0',
                      '@tinacms/datalayer@2.0.29', '@tinacms/graphql@2.4.11', '@emnapi/runtime@1.11.3'):
            self.assertIn(value, reference)


if __name__ == '__main__':
    unittest.main()
