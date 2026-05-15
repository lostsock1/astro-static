#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Prefer the real jsonschema library — it supports oneOf/anyOf/allOf, format,
# pattern, additionalProperties:false, $defs refs, etc. The hand-rolled fallback
# below is a strict subset (type, enum, required, properties, items, $ref) that
# is kept only for environments where jsonschema isn't installed.
#
# Debian/Ubuntu: apt install python3-jsonschema
# macOS/pip:     pip install jsonschema
try:
    import jsonschema  # type: ignore
    from jsonschema import Draft202012Validator  # type: ignore
    HAVE_JSONSCHEMA = True
except ImportError:
    HAVE_JSONSCHEMA = False

import os
_BASE = Path(__file__).resolve().parent.parent
_DEFAULT_SCHEMA_DIR = _BASE / 'agents' / 'astro-static' / 'schemas'
SCHEMA_DIR = Path(os.environ.get('ASTRO_STATIC_SCHEMA_DIR', _DEFAULT_SCHEMA_DIR))

# Per-profile artifact maps. The astro-static profile uses vps-connection.json
# (multi-host bootstrap). The astro-ispconfig profile is single-host with
# preflight-result.json instead, and adds the image-shot-list contract.
PROFILES = {
    'astro-static': {
        'schema_dir': _BASE / 'agents' / 'astro-static' / 'schemas',
        'artifacts': {
            '00-brief.json':            '00-brief.schema.json',
            '01-creative-brief.json':   '01-creative-brief.schema.json',
            '02-font-config.json':      '02-font-config.schema.json',
            '02-asset-manifest.json':   '02-asset-manifest.schema.json',
            '02-image-shot-list.json':  '02-image-shot-list.schema.json',
            '02-video-shot-list.json':  '02-video-shot-list.schema.json',
            'vps-connection.json':      'vps-connection.schema.json',
            '00-pipeline-state.json':   '00-pipeline-state.schema.json',
        },
    },
    'ispconfig': {
        'schema_dir': _BASE / 'agents' / 'astro-ispconfig' / 'schemas',
        'artifacts': {
            '00-brief.json':            '00-brief.schema.json',
            '01-creative-brief.json':   '01-creative-brief.schema.json',
            '02-font-config.json':      '02-font-config.schema.json',
            '02-asset-manifest.json':   '02-asset-manifest.schema.json',
            '02-image-shot-list.json':  '02-image-shot-list.schema.json',
            '02-video-shot-list.json':  '02-video-shot-list.schema.json',
            '00-pipeline-state.json':   '00-pipeline-state.schema.json',
        },
    },
}

# Default ARTIFACTS — preserved for backward compat with callers that don't
# pass --profile. Mutated by main() when --profile is supplied.
ARTIFACTS = dict(PROFILES['astro-static']['artifacts'])

OPTIONAL_ARTIFACTS = {
    '00-design-tokens/tokens.json': '00-design-tokens.schema.json',
    'bootstrap-result.json': 'bootstrap-result.schema.json',
}

def _phases_for(profile: str) -> dict[str, dict[str, Any]]:
    """Phase gate configuration. The astro-static profile requires
    vps-connection.json at every gate (multi-host bootstrap); the ispconfig
    profile is single-host so it uses preflight-result.json (untyped at
    artifact level — covered by preflight.sh writing it directly)."""
    if profile == 'ispconfig':
        connection_required = set()  # no vps-connection in ispconfig profile
        all_artifacts = set(PROFILES['ispconfig']['artifacts'].keys())
        video_shot_list = {'02-video-shot-list.json'}
    else:
        connection_required = {'vps-connection.json'}
        all_artifacts = set(PROFILES['astro-static']['artifacts'].keys())
        video_shot_list = {'02-video-shot-list.json'}
    # Shot lists are produced by Phase 3.5 (images) and Phase 3.6 (videos);
    # they may legitimately be absent on simple builds, so we treat them as
    # optional at every gate. validate_artifact() still runs filesystem checks
    # for any path listed in the manifest's content_images / video_backgrounds.
    return {
        'startup': {
            'required': {'00-brief.json'} | connection_required,
            'optional': {'00-pipeline-state.json'},
            'check_theme': False, 'check_layout': False, 'check_asset_paths': False,
            'strict': False, 'description': 'Initial intake + preflight gate',
        },
        'research': {
            'required': {'00-brief.json', '01-creative-brief.json'} | connection_required,
            'optional': {'00-pipeline-state.json'},
            'check_theme': False, 'check_layout': False, 'check_asset_paths': False,
            'strict': False, 'description': 'Creative brief produced',
        },
        'assets': {
            'required': {'00-brief.json', '01-creative-brief.json',
                         '02-font-config.json', '02-asset-manifest.json'} | connection_required,
            'optional': {'00-pipeline-state.json', '02-image-shot-list.json'} | video_shot_list,
            'check_theme': True, 'check_layout': False, 'check_asset_paths': True,
            'strict': True, 'description': 'Asset generation gate',
        },
        'build': {
            'required': {'00-brief.json', '01-creative-brief.json',
                         '02-font-config.json', '02-asset-manifest.json',
                         '00-pipeline-state.json'} | connection_required,
            'optional': {'02-image-shot-list.json'} | video_shot_list,
            'check_theme': True, 'check_layout': True, 'check_asset_paths': True,
            'strict': True, 'description': 'Frontend build / pre-deploy gate',
        },
        'final': {
            'required': all_artifacts - {'02-image-shot-list.json', '02-video-shot-list.json'},
            'optional': {'02-image-shot-list.json'} | video_shot_list,
            'check_theme': True, 'check_layout': True, 'check_asset_paths': True,
            'strict': True, 'description': 'Full post-build validation',
        },
    }

# Default PHASES (astro-static) — preserved for backward compat. Mutated by
# main() when --profile is supplied.
PHASES = _phases_for('astro-static')


@dataclass
class Issue:
    level: str
    artifact: str
    message: str


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def schema_type_matches(expected: Any, value: Any) -> bool:
    if isinstance(expected, list):
        return any(schema_type_matches(item, value) for item in expected)
    mapping = {
        'object': dict,
        'array': list,
        'string': str,
        'integer': int,
        'number': (int, float),
        'boolean': bool,
        'null': type(None),
    }
    py_type = mapping.get(expected)
    if py_type is None:
        return True
    if expected == 'integer':
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == 'number':
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, py_type)


def resolve_ref(root: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith('#/'):
        raise ValueError(f'Only local refs supported, got: {ref}')
    node: Any = root
    for part in ref[2:].split('/'):
        node = node[part]
    if not isinstance(node, dict):
        raise ValueError(f'Ref did not resolve to object schema: {ref}')
    return node


def _format_jsonschema_path(absolute_path: Any) -> str:
    """Turn a jsonschema error's deque path into $.a.b[0].c style for parity with the fallback."""
    parts = ['$']
    for segment in absolute_path:
        if isinstance(segment, int):
            parts.append(f'[{segment}]')
        else:
            # jsonschema uses '' for root, skip
            if segment == '':
                continue
            parts.append(f'.{segment}')
    return ''.join(parts) or '$'


def validate_with_jsonschema(value: Any, schema: dict[str, Any], issues: list[Issue], artifact: str) -> None:
    """Full jsonschema validation — supports oneOf/anyOf/allOf, format, pattern, additionalProperties:false."""
    validator = Draft202012Validator(schema)
    for err in sorted(validator.iter_errors(value), key=lambda e: e.path):
        path = _format_jsonschema_path(err.absolute_path)
        # err.message already contains enough detail (e.g. "None is not of type 'string'")
        issues.append(Issue('error', artifact, f'{path}: {err.message}'))


def validate_with_fallback(value: Any, schema: dict[str, Any], root: dict[str, Any], path: str, issues: list[Issue], artifact: str) -> None:
    """Hand-rolled subset validator. Used only when jsonschema isn't installed.

    Strict subset — recognizes: type, enum, required, properties, items, $ref.
    Does NOT recognize: oneOf, anyOf, allOf, additionalProperties:false, format, pattern.
    If you need those, install jsonschema.
    """
    if '$ref' in schema:
        validate_with_fallback(value, resolve_ref(root, schema['$ref']), root, path, issues, artifact)
        return

    if 'type' in schema and not schema_type_matches(schema['type'], value):
        issues.append(Issue('error', artifact, f'{path}: expected type {schema["type"]}, got {type(value).__name__}'))
        return

    if 'enum' in schema and value not in schema['enum']:
        issues.append(Issue('error', artifact, f'{path}: value {value!r} not in enum {schema["enum"]}'))

    if isinstance(value, dict):
        for key in schema.get('required', []):
            if key not in value:
                issues.append(Issue('error', artifact, f'{path}.{key}: missing required field'))
        for key, subschema in schema.get('properties', {}).items():
            if key in value and isinstance(subschema, dict):
                validate_with_fallback(value[key], subschema, root, f'{path}.{key}', issues, artifact)
    elif isinstance(value, list):
        item_schema = schema.get('items')
        if isinstance(item_schema, dict):
            for idx, item in enumerate(value):
                validate_with_fallback(item, item_schema, root, f'{path}[{idx}]', issues, artifact)


def validate_value(value: Any, schema: dict[str, Any], root: dict[str, Any], path: str, issues: list[Issue], artifact: str) -> None:
    """Dispatch to jsonschema library when available, hand-rolled fallback otherwise."""
    if HAVE_JSONSCHEMA:
        validate_with_jsonschema(value, schema, issues, artifact)
    else:
        validate_with_fallback(value, schema, root, path, issues, artifact)


def validate_artifact(project_root: Path, pipeline_dir: Path, artifact_name: str, schema_name: str, issues: list[Issue], missing_is_error: bool, check_asset_paths: bool) -> None:
    artifact_path = pipeline_dir / artifact_name
    schema_path = SCHEMA_DIR / schema_name

    if not schema_path.exists():
        issues.append(Issue('error', artifact_name, f'missing schema file: {schema_path}'))
        return

    if not artifact_path.exists():
        issues.append(Issue('error' if missing_is_error else 'warning', artifact_name, f'artifact missing: {artifact_path}'))
        return

    try:
        data = load_json(artifact_path)
    except Exception as exc:
        issues.append(Issue('error', artifact_name, f'invalid JSON: {exc}'))
        return

    try:
        schema = load_json(schema_path)
    except Exception as exc:
        issues.append(Issue('error', artifact_name, f'invalid schema JSON: {exc}'))
        return

    validate_value(data, schema, schema, '$', issues, artifact_name)

    if artifact_name == '02-asset-manifest.json' and isinstance(data, dict) and check_asset_paths:
        for key_path in [
            ('logo', 'primary_path'),
            ('logo', 'svg'),
            ('logo', 'png'),
            ('favicon', 'ico'),
            ('favicon', 'png_32'),
            ('favicon', 'png_16'),
            ('favicon', 'apple_touch'),
            ('og_image', 'path'),
            ('theme', 'css'),
        ]:
            node = data
            for key in key_path:
                if not isinstance(node, dict) or key not in node:
                    node = None
                    break
                node = node[key]
            if isinstance(node, str):
                target = project_root / node
                if not target.exists():
                    issues.append(Issue('error', artifact_name, f'{".".join(key_path)} points to missing file: {target}'))
        font_config = data.get('font_config')
        if isinstance(font_config, str) and not (project_root / font_config).exists():
            issues.append(Issue('error', artifact_name, f'font_config points to missing file: {project_root / font_config}'))

    if artifact_name == '01-creative-brief.json' and isinstance(data, dict):
        if data.get('_requires_human_confirmation') is True:
            issues.append(Issue('warning', artifact_name, 'brief is flagged for human confirmation'))

    if artifact_name == '02-asset-manifest.json' and isinstance(data, dict) and check_asset_paths:
        # OG image path check: warn if in src/ instead of public/
        og_path = None
        if isinstance(data.get('og_image'), dict):
            og_path = data['og_image'].get('path')
        if og_path and isinstance(og_path, str) and og_path.startswith('src/'):
            issues.append(Issue('warning', artifact_name,
                f'og_image path is {og_path} — should be in public/ for static serving'))

        # Content images check: verify every manifest entry's file exists.
        # Canonical key is `path` (orchestrator Phase 3.5 normalizes from the
        # shot list's `output_path`). The legacy `output_path` key is still
        # accepted here, but the orchestrator should not be writing it any
        # more — flag it as a warning when seen so drift is visible.
        content_images = data.get('content_images', [])
        if isinstance(content_images, list):
            for img in content_images:
                if not isinstance(img, dict):
                    continue
                path_value = img.get('path')
                if path_value is None and 'output_path' in img:
                    path_value = img.get('output_path')
                    issues.append(Issue('warning', artifact_name,
                        f'content_images entry uses legacy `output_path` key; rename to `path`: id={img.get("id", "?")}'))
                if isinstance(path_value, str):
                    target = project_root / path_value
                    if not target.exists():
                        status = img.get('status', '')
                        if status != 'failed':
                            issues.append(Issue('warning', artifact_name,
                                f'content image missing: {path_value} (status={status or "unknown"})'))



def validate_project(project_root: Path, phase_name: str | None, require_all: bool, pipeline_dir: Path | None = None) -> tuple[list[Issue], str]:
    issues: list[Issue] = []
    # Support split layout: pipeline/ may live outside project_root (e.g. at /home/openclaw/pipeline/
    # while the website is at /home/openclaw/websites/<project>/). If not explicitly provided,
    # check both project_root/pipeline/ and the parent-directory pipeline/ pattern.
    if pipeline_dir is None:
        pipeline_dir = project_root / 'pipeline'
        if not pipeline_dir.exists():
            # Try parent-directory pattern: /home/openclaw/websites/drone → /home/openclaw/pipeline/
            parent_pipeline = project_root.parent.parent / 'pipeline'
            if parent_pipeline.exists():
                pipeline_dir = parent_pipeline
    if not pipeline_dir.exists():
        return [Issue('error', 'pipeline', f'missing pipeline directory: {pipeline_dir}')], phase_name or 'custom'

    if phase_name:
        config = PHASES[phase_name]
        required = set(config['required'])
        optional = set(config['optional'])
        strict = bool(config['strict']) or require_all
        check_theme = bool(config['check_theme'])
        check_layout = bool(config['check_layout'])
        check_asset_paths = bool(config['check_asset_paths'])
    else:
        required = set(ARTIFACTS.keys()) if require_all else {'00-brief.json'}
        optional = set()
        strict = require_all
        check_theme = require_all
        check_layout = require_all
        check_asset_paths = require_all

    for artifact, schema in ARTIFACTS.items():
        if artifact in required:
            validate_artifact(project_root, pipeline_dir, artifact, schema, issues, missing_is_error=True, check_asset_paths=check_asset_paths)
        elif artifact in optional:
            validate_artifact(project_root, pipeline_dir, artifact, schema, issues, missing_is_error=False, check_asset_paths=check_asset_paths)
        elif require_all:
            validate_artifact(project_root, pipeline_dir, artifact, schema, issues, missing_is_error=True, check_asset_paths=check_asset_paths)

    for artifact, schema in OPTIONAL_ARTIFACTS.items():
        if (pipeline_dir / artifact).exists():
            validate_artifact(project_root, pipeline_dir, artifact, schema, issues, missing_is_error=True, check_asset_paths=False)

    theme_css = project_root / 'src/styles/theme.css'
    if check_theme:
        if theme_css.exists():
            content = theme_css.read_text()
            if '@theme' not in content:
                issues.append(Issue('error', 'src/styles/theme.css', 'missing @theme block'))
        else:
            issues.append(Issue('error', 'src/styles/theme.css', f'missing file: {theme_css}'))

    base_layout = project_root / 'src/layouts/BaseLayout.astro'
    if check_layout:
        if base_layout.exists():
            content = base_layout.read_text()
            if 'global.css' not in content:
                issues.append(Issue('warning', 'src/layouts/BaseLayout.astro', 'BaseLayout does not appear to import global.css'))
        else:
            issues.append(Issue('error', 'src/layouts/BaseLayout.astro', f'missing file: {base_layout}'))

    # Check that gallery/content pages reference images or have fallback
    gallery_page = project_root / 'src/pages/galerie.astro'
    gallery_page_alt = project_root / 'src/pages/gallery.astro'
    for gp in [gallery_page, gallery_page_alt]:
        if gp.exists():
            content = gp.read_text()
            if 'image' not in content.lower() and 'img' not in content.lower() and 'Image' not in content:
                issues.append(Issue('warning', str(gp.relative_to(project_root)),
                    'gallery page has no image rendering — content images from Phase 3.5 will not appear'))

    return issues, phase_name or ('strict' if require_all else 'default')


def main() -> int:
    global ARTIFACTS, SCHEMA_DIR, PHASES
    parser = argparse.ArgumentParser(description='Validate an astro-static project pipeline against local schema contracts.')
    parser.add_argument('project', help='Project directory to validate, e.g. /home/openclaw/websites/my-site')
    parser.add_argument('--require-all', action='store_true', help='Treat all known artifacts as required and run full filesystem checks')
    parser.add_argument('--phase', choices=sorted(PHASES.keys()), help='Validate a specific workflow phase gate: startup, research, assets, build, final')
    parser.add_argument('--pipeline-dir', type=Path, help='Explicit pipeline directory (overrides auto-detection).')
    parser.add_argument('--profile', choices=sorted(PROFILES.keys()), default='astro-static',
                        help='Pipeline profile: astro-static (multi-host bootstrap) or ispconfig (single-host)')
    args = parser.parse_args()

    # Wire profile selection into module globals so existing helpers see the
    # right artifact map / schema dir without a function-signature shuffle.
    ARTIFACTS = dict(PROFILES[args.profile]['artifacts'])
    if 'ASTRO_STATIC_SCHEMA_DIR' not in os.environ and 'ASTRO_ISPCONFIG_SCHEMA_DIR' not in os.environ:
        SCHEMA_DIR = Path(PROFILES[args.profile]['schema_dir'])
    elif args.profile == 'ispconfig' and 'ASTRO_ISPCONFIG_SCHEMA_DIR' in os.environ:
        SCHEMA_DIR = Path(os.environ['ASTRO_ISPCONFIG_SCHEMA_DIR'])
    PHASES = _phases_for(args.profile)

    project_root = Path(args.project).expanduser().resolve()
    if not project_root.exists():
        print(f'ERROR: project directory does not exist: {project_root}', file=sys.stderr)
        return 2

    pipeline_dir = args.pipeline_dir.expanduser().resolve() if args.pipeline_dir else None
    issues, mode = validate_project(project_root, phase_name=args.phase, require_all=args.require_all, pipeline_dir=pipeline_dir)
    errors = [i for i in issues if i.level == 'error']
    warnings = [i for i in issues if i.level == 'warning']

    engine = 'jsonschema' if HAVE_JSONSCHEMA else 'fallback-subset'
    if not issues:
        print(f'VALIDATION_OK [{mode}] engine={engine}: {project_root}')
        return 0

    for issue in issues:
        print(f'{issue.level.upper():7} {issue.artifact}: {issue.message}')

    print(f'\nSummary [{mode}] engine={engine}: {len(errors)} error(s), {len(warnings)} warning(s)')
    if not HAVE_JSONSCHEMA:
        print('NOTE: jsonschema library not installed — running subset validator. '
              'Install python3-jsonschema for oneOf/anyOf/format/additionalProperties support.',
              file=sys.stderr)
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
