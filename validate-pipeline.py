#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
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
_HERE = Path(__file__).resolve().parent
_BASE = _HERE if (_HERE / 'agents' / 'astro-static' / 'schemas').exists() else _HERE.parent
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
        'instagram': {
            'required': set(),
            'optional': set(),
            'check_theme': False, 'check_layout': False, 'check_asset_paths': False,
            'strict': False, 'description': 'Instagram extraction gate (00-instagram/)',
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


SOURCE_SUFFIXES = ('.astro', '.ts', '.tsx', '.js', '.jsx')
TEXT_NODE_TAGS = {
    'a', 'button', 'figcaption', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'label', 'legend', 'li', 'p', 'small', 'span', 'strong', 'summary',
}
COPY_WORD_RE = re.compile(r'[A-Za-zÀ-ÖØ-öø-ÿ]{3,}')
MEDIA_LITERAL_RE = re.compile(
    r'\b(?:src|poster|videoSrc|posterPath|image|bgImage)\s*=\s*["\'](?P<path>/(?:assets|images|media|uploads|videos)/[^"\']+)["\']'
)
MEDIA_DEFAULT_RE = re.compile(
    r'\b(?:src|poster|videoSrc|posterPath|image|bgImage)\s*[:=]\s*["\'](?P<path>/(?:assets|images|media|uploads|videos)/[^"\']+)["\']'
)
SERVICE_BULLET_ARRAY_RE = re.compile(
    r'\b(?:serviceBullets|bullets)\s*[:=]\s*\[[^\]]*["\'][^"\']*\s+[^"\']*["\']',
    re.DOTALL,
)
# Matches <img ...> (including self-closing) so we can require data-tina-field
# or data-static-media on every rendered image in Tina-enabled projects.
IMG_TAG_RE = re.compile(r'<img\b(?P<attrs>[^>]*?)/?>', re.IGNORECASE)
# Detects contentImages[...] usage — the asset-generator import index. Components
# that use it MUST also accept a Tina image field prop and resolve Tina-first.
CONTENT_IMAGES_USAGE_RE = re.compile(r'contentImages\s*\[')


def line_number(text: str, offset: int) -> int:
    return text.count('\n', 0, offset) + 1


def source_files(src_root: Path) -> list[Path]:
    if not src_root.exists():
        return []
    return [path for path in src_root.rglob('*') if path.is_file() and path.suffix in SOURCE_SUFFIXES]


def strip_astro_frontmatter(text: str) -> tuple[str, str]:
    if text.startswith('---'):
        end = text.find('\n---', 3)
        if end != -1:
            return text[: end + 4], text[end + 4:]
    return '', text


def strip_non_visible_blocks(markup: str) -> str:
    for pattern in [
        r'<!--.*?-->',
        r'<script\b.*?</script>',
        r'<style\b.*?</style>',
        r'<svg\b.*?</svg>',
    ]:
        markup = re.sub(pattern, '', markup, flags=re.DOTALL | re.IGNORECASE)
    return markup


def strip_tags(text: str) -> str:
    return re.sub(r'<[^>]+>', '', text)


def looks_like_copy(text: str) -> bool:
    compact = re.sub(r'\s+', ' ', text).strip()
    if not compact or compact.startswith('{') and compact.endswith('}'):
        return False
    return COPY_WORD_RE.search(compact) is not None


def snippet(text: str, limit: int = 80) -> str:
    compact = re.sub(r'\s+', ' ', text).strip()
    return compact if len(compact) <= limit else compact[: limit - 1] + '…'


def has_static_escape(attrs: str) -> bool:
    return any(flag in attrs for flag in ('data-static-copy', 'data-static-media', 'aria-hidden="true"', "aria-hidden='true'"))


def validate_tina_editable_surfaces(project_root: Path, files: list[Path], issues: list[Issue]) -> None:
    """Guard Tina-enabled builds against slipping visible copy/media back into source.

    The validator cannot prove semantic editability perfectly without compiling the
    Astro component tree, but it catches the high-risk regressions that break
    Tina visual editing in practice: literal marketing copy in markup, visible
    typewriter nodes without click-to-edit metadata, source-level media literals,
    and hardcoded service bullet arrays.
    """
    for source_path in files:
        try:
            content = source_path.read_text()
        except UnicodeDecodeError:
            continue
        rel = str(source_path.relative_to(project_root))
        frontmatter, markup = strip_astro_frontmatter(content)
        visible_markup = strip_non_visible_blocks(markup)
        is_astro = source_path.suffix == '.astro'

        # ── Markup-level checks (.astro files only) ───────────────────
        # .ts/.tsx files are data/logic modules; they don't render <img> or
        # text nodes directly, so scanning them for markup patterns produces
        # false positives.
        if is_astro:
            text_tag_pattern = '|'.join(sorted(TEXT_NODE_TAGS))
            for match in re.finditer(
                rf'<(?P<tag>{text_tag_pattern})(?P<attrs>[^>]*)>(?P<body>.*?)</(?P=tag)>',
                visible_markup,
                flags=re.DOTALL,
            ):
                tag = match.group('tag').lower()
                if tag not in TEXT_NODE_TAGS:
                    continue
                attrs = match.group('attrs')
                body = match.group('body')
                if has_static_escape(attrs) or 'data-tina-field' in attrs:
                    continue
                plain_body = strip_tags(body)
                if 'data-typewriter' in attrs and ('{' in plain_body or looks_like_copy(plain_body)):
                    issues.append(Issue(
                        'error', rel,
                        f'line {line_number(visible_markup, match.start())}: data-typewriter text node is missing data-tina-field; bind this text to Tina metadata or mark it data-static-copy if intentionally static',
                    ))
                elif '{' not in plain_body and looks_like_copy(plain_body):
                    issues.append(Issue(
                        'error', rel,
                        f'line {line_number(visible_markup, match.start())}: hardcoded visible text not backed by Tina field: "{snippet(plain_body)}"',
                    ))

            # Every <img> must be Tina-backed or explicitly static.
            for match in IMG_TAG_RE.finditer(visible_markup):
                attrs = match.group('attrs')
                if has_static_escape(attrs) or 'data-tina-field' in attrs:
                    continue
                issues.append(Issue(
                    'error', rel,
                    f'line {line_number(visible_markup, match.start())}: img element missing data-tina-field; wire it to a Tina image field or mark data-static-media if decorative',
                ))

        # ── Source-level checks (all Tina-enabled source files) ───────
        for match in MEDIA_LITERAL_RE.finditer(visible_markup):
            line_start = visible_markup.rfind('\n', 0, match.start()) + 1
            line_end = visible_markup.find('\n', match.start())
            if line_end == -1:
                line_end = len(visible_markup)
            line = visible_markup[line_start:line_end]
            if 'data-tina-field' in line or 'data-static-media' in line:
                continue
            issues.append(Issue(
                'error', rel,
                f'line {line_number(visible_markup, match.start())}: hardcoded media path must be Tina/content/manifest-backed: {match.group("path")}',
            ))

        for match in MEDIA_DEFAULT_RE.finditer(frontmatter):
            issues.append(Issue(
                'error', rel,
                f'line {line_number(frontmatter, match.start())}: hardcoded media path must be Tina/content/manifest-backed: {match.group("path")}',
            ))

        if SERVICE_BULLET_ARRAY_RE.search(frontmatter):
            issues.append(Issue(
                'error', rel,
                'hardcoded service bullet array found; move list copy into Tina-backed content and render with data-tina-field indexes',
            ))

        # contentImages[] usage requires a Tina image field override prop so
        # editors can replace the asset-generator default from the admin.
        if CONTENT_IMAGES_USAGE_RE.search(content):
            has_tina_override = (
                'bgImage' in frontmatter
                or 'image' in frontmatter and 'fields' in frontmatter
                or 'Astro.props' in frontmatter and ('bgImage' in frontmatter or 'image' in frontmatter)
                or re.search(r'\b(?:bgImage|heroImage|cardImage)\b.*Astro\.props', frontmatter) is not None
                or 'bgImage ??' in content
                or 'image ??' in content
            )
            if not has_tina_override:
                issues.append(Issue(
                    'error', rel,
                    'contentImages[] usage found without Tina image field override; add an optional image/bgImage prop, resolve Tina-first (tinaField ?? contentImages[...]), and render data-tina-field on the <img>',
                ))


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
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
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


SECRET_ARTIFACTS = {'vps-connection.json', 'bootstrap-result.json'}


def validate_secret_permissions(artifact_path: Path, artifact_name: str, issues: list[Issue]) -> None:
    """Secret-bearing pipeline artifacts must never be group/world-readable."""
    try:
        mode = artifact_path.stat().st_mode & 0o777
    except OSError as exc:
        issues.append(Issue('error', artifact_name, f'cannot stat secret file permissions: {exc}'))
        return
    if mode != 0o600:
        issues.append(Issue(
            'error', artifact_name,
            f'secret file permissions must be 0600, got {mode:04o}; chmod 0600 {artifact_name}',
        ))


def validate_safe_relative_artifact_path(
    project_root: Path,
    artifact_name: str,
    logical_path: str,
    path_value: str,
    issues: list[Issue],
) -> Path | None:
    """Return resolved target when path stays inside project_root; otherwise emit an error."""
    candidate = Path(path_value)
    if candidate.is_absolute():
        issues.append(Issue(
            'error', artifact_name,
            f'unsafe artifact path at {logical_path}: absolute paths are not allowed: {path_value}',
        ))
        return None
    if '..' in candidate.parts:
        issues.append(Issue(
            'error', artifact_name,
            f'unsafe artifact path at {logical_path}: path traversal is not allowed: {path_value}',
        ))
        return None
    try:
        target = (project_root / candidate).resolve()
        target.relative_to(project_root.resolve())
    except ValueError:
        issues.append(Issue(
            'error', artifact_name,
            f'unsafe artifact path at {logical_path}: resolved path escapes project root: {path_value}',
        ))
        return None
    return target


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

    if artifact_name in SECRET_ARTIFACTS:
        validate_secret_permissions(artifact_path, artifact_name, issues)

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
                logical_path = '.'.join(key_path)
                target = validate_safe_relative_artifact_path(project_root, artifact_name, logical_path, node, issues)
                if target is not None and not target.exists():
                    issues.append(Issue('error', artifact_name, f'{".".join(key_path)} points to missing file: {target}'))
        font_config = data.get('font_config')
        if isinstance(font_config, str):
            font_target = validate_safe_relative_artifact_path(project_root, artifact_name, 'font_config', font_config, issues)
            if font_target is not None and not font_target.exists():
                issues.append(Issue('error', artifact_name, f'font_config points to missing file: {font_target}'))

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
        if og_path and isinstance(og_path, str) and og_path.lower().endswith('.svg'):
            issues.append(Issue('warning', artifact_name,
                f'og_image path is {og_path} — prefer public/og-image.png for social preview compatibility'))

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
                    target = validate_safe_relative_artifact_path(
                        project_root,
                        artifact_name,
                        f'content_images[{img.get("id", "?")}].path',
                        path_value,
                        issues,
                    )
                    if target is not None and not target.exists():
                        status = img.get('status', '')
                        if status != 'failed':
                            issues.append(Issue('warning', artifact_name,
                                f'content image missing: {path_value} (status={status or "unknown"})'))

        # Video backgrounds check: generated videos must be public MP4 assets,
        # and poster_path must be a real still image. A prior run accidentally
        # used the MP4 as its own poster, which caused static artifacts behind
        # the clip and poor first paint in browsers.
        video_backgrounds = data.get('video_backgrounds', [])
        if isinstance(video_backgrounds, list):
            for video in video_backgrounds:
                if not isinstance(video, dict):
                    continue
                status = video.get('status', '')
                output_path = video.get('output_path')
                poster_path = video.get('poster_path')
                if isinstance(output_path, str) and status == 'generated':
                    video_target = validate_safe_relative_artifact_path(
                        project_root,
                        artifact_name,
                        f'video_backgrounds[{video.get("id", "?")}].output_path',
                        output_path,
                        issues,
                    )
                    if not output_path.startswith('public/videos/'):
                        issues.append(Issue('error', artifact_name,
                            f'generated video must live under public/videos/: id={video.get("id", "?")} output_path={output_path}'))
                    if video_target is None:
                        pass
                    elif not video_target.exists():
                        issues.append(Issue('error', artifact_name,
                            f'generated video missing: id={video.get("id", "?")} output_path={output_path}'))
                    elif video_target.stat().st_size <= 100 * 1024:
                        issues.append(Issue('error', artifact_name,
                            f'generated video too small: id={video.get("id", "?")} output_path={output_path}'))
                if isinstance(poster_path, str) and poster_path:
                    lower_poster = poster_path.lower()
                    if isinstance(output_path, str) and poster_path == output_path:
                        issues.append(Issue('error', artifact_name,
                            f'video poster_path must be a still image, not the MP4 output_path: id={video.get("id", "?")}'))
                    if lower_poster.endswith(('.mp4', '.mov', '.m4v', '.webm')):
                        issues.append(Issue('error', artifact_name,
                            f'video poster_path must not be a video file: id={video.get("id", "?")} poster_path={poster_path}'))
                    poster_target = validate_safe_relative_artifact_path(
                        project_root,
                        artifact_name,
                        f'video_backgrounds[{video.get("id", "?")}].poster_path',
                        poster_path,
                        issues,
                    )
                    if status == 'generated' and poster_target is not None and not poster_target.exists():
                        issues.append(Issue('error', artifact_name,
                            f'video poster_path points to missing file: id={video.get("id", "?")} poster_path={poster_path}'))

        # HyperFrames hero video check: generated by Phase 3.8 (default-on, zero-cost).
        # Must exist at public/videos/hero-intro.mp4 and be a valid MP4 over 100 KB.
        hf_hero = data.get('hyperframes_hero')
        if isinstance(hf_hero, dict):
            hf_path = hf_hero.get('path')
            if isinstance(hf_path, str):
                hf_target = validate_safe_relative_artifact_path(project_root, artifact_name, 'hyperframes_hero.path', hf_path, issues)
                if not hf_path.startswith('public/videos/'):
                    issues.append(Issue('error', artifact_name,
                        f'hyperframes_hero video must live under public/videos/: path={hf_path}'))
                if hf_target is None:
                    pass
                elif not hf_target.exists():
                    issues.append(Issue('warning', artifact_name,
                        f'hyperframes_hero video missing (Phase 3.8 may have been skipped): path={hf_path}'))
                elif hf_target.stat().st_size <= 100 * 1024:
                    issues.append(Issue('error', artifact_name,
                        f'hyperframes_hero video too small (< 100 KB): path={hf_path} size={hf_target.stat().st_size}'))
                elif not hf_path.lower().endswith('.mp4'):
                    issues.append(Issue('error', artifact_name,
                        f'hyperframes_hero video must be MP4: path={hf_path}'))
            hf_template = hf_hero.get('template')
            if hf_template and isinstance(hf_template, str) and hf_template not in (
                'kinetic-type', 'swiss-grid', 'warm-grain', 'blank',
            ):
                issues.append(Issue('warning', artifact_name,
                    f'hyperframes_hero template unknown: {hf_template} (expected one of kinetic-type, swiss-grid, warm-grain, blank)'))
            hf_intensity = hf_hero.get('intensity')
            if hf_intensity and isinstance(hf_intensity, str) and hf_intensity not in ('subtle', 'moderate'):
                issues.append(Issue('warning', artifact_name,
                    f'hyperframes_hero intensity unknown: {hf_intensity} (expected subtle or moderate)'))



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

    # ── Instagram extraction validation ───────────────────────────────
    if phase_name == 'instagram':
        ig_dir = pipeline_dir / '00-instagram'
        if ig_dir.exists():
            # profile.json must exist and parse
            profile_file = ig_dir / 'profile.json'
            if profile_file.exists():
                try:
                    profile_data = json.loads(profile_file.read_text())
                    if not isinstance(profile_data, dict):
                        issues.append(Issue('error', '00-instagram/profile.json', 'root must be a JSON object'))
                    else:
                        for field in ['schema_version', 'profile', 'extraction_metadata']:
                            if field not in profile_data:
                                issues.append(Issue('error', '00-instagram/profile.json', f'missing required field: {field}'))
                        profile = profile_data.get('profile', {})
                        if isinstance(profile, dict):
                            if not profile.get('username'):
                                issues.append(Issue('error', '00-instagram/profile.json', 'profile.username is empty'))
                            if not profile.get('display_name'):
                                issues.append(Issue('warning', '00-instagram/profile.json', 'profile.display_name is empty'))
                        posts = profile_data.get('posts', [])
                        if isinstance(posts, list) and len(posts) == 0:
                            issues.append(Issue('warning', '00-instagram/profile.json', 'no posts extracted'))
                        extraction = profile_data.get('extraction_metadata', {})
                        if isinstance(extraction, dict) and not extraction.get('stealth_used', True):
                            issues.append(Issue('warning', '00-instagram/profile.json', 'extraction did not use stealth — data may be incomplete'))
                except (json.JSONDecodeError, OSError) as exc:
                    issues.append(Issue('error', '00-instagram/profile.json', f'cannot parse: {exc}'))
            else:
                issues.append(Issue('error', '00-instagram/', 'profile.json missing — Instagram extraction did not complete'))

            # Check downloaded assets exist
            assets_dir = ig_dir / 'assets'
            if assets_dir.exists():
                asset_files = list(assets_dir.glob('*'))
                if not asset_files:
                    issues.append(Issue('warning', '00-instagram/assets/', 'no downloaded images'))
                else:
                    for f in asset_files:
                        if f.stat().st_size < 1024:
                            issues.append(Issue('warning', str(f.relative_to(pipeline_dir)), f'image too small ({f.stat().st_size} bytes) — may be an error page'))
            else:
                issues.append(Issue('warning', '00-instagram/', 'assets/ directory missing — no images downloaded'))

            # Check extraction report
            report = ig_dir / 'extraction-report.md'
            if not report.exists():
                issues.append(Issue('warning', '00-instagram/', 'extraction-report.md missing'))
        else:
            issues.append(Issue('error', '00-instagram/', 'directory missing — Instagram extraction phase did not run'))

    theme_css = project_root / 'src/styles/theme.css'
    if check_theme:
        if theme_css.exists():
            content = theme_css.read_text()
            if '@theme' not in content:
                issues.append(Issue('error', 'src/styles/theme.css', 'missing @theme block'))
            global_css = project_root / 'src/styles/global.css'
            global_content = global_css.read_text() if global_css.exists() else ''
            theme_has_tailwind_import = re.search(r'@import\s+["\']tailwindcss["\']', content) is not None
            global_has_tailwind_entry = (
                re.search(r'@import\s+["\']tailwindcss["\']', global_content) is not None
                and ('theme.css' in global_content or '@theme' in global_content)
            )
            if not theme_has_tailwind_import and not global_has_tailwind_entry:
                issues.append(Issue('error', 'src/styles/theme.css',
                    'Tailwind v4 entry missing: add @import "tailwindcss" to theme.css, or import tailwindcss + theme.css from src/styles/global.css'))
            for match in re.finditer(r'oklch\(\s*([0-9]+(?:\.[0-9]+)?)\s+', content):
                try:
                    lightness = float(match.group(1))
                except ValueError:
                    continue
                if lightness > 1:
                    issues.append(Issue('error', 'src/styles/theme.css',
                        f'invalid oklch() lightness {match.group(1)} — use 0–1 fractions or append % for percentage lightness'))
        else:
            issues.append(Issue('error', 'src/styles/theme.css', f'missing file: {theme_css}'))

    base_layout = project_root / 'src/layouts/BaseLayout.astro'
    if check_layout:
        if base_layout.exists():
            content = base_layout.read_text()
            if 'styles/global.css' not in content and 'styles/theme.css' not in content:
                issues.append(Issue('error', 'src/layouts/BaseLayout.astro',
                    'BaseLayout must import the Tailwind CSS entry from src/styles/global.css or src/styles/theme.css'))
        else:
            issues.append(Issue('error', 'src/layouts/BaseLayout.astro', f'missing file: {base_layout}'))

    package_json = project_root / 'package.json'
    if package_json.exists():
        try:
            package_data = json.loads(package_json.read_text())
        except json.JSONDecodeError as exc:
            issues.append(Issue('error', 'package.json', f'invalid JSON: {exc}'))
            package_data = {}
        deps = {**package_data.get('dependencies', {}), **package_data.get('devDependencies', {})}
        has_tina = '@tinacms/astro' in deps or 'tinacms' in deps
        if has_tina:
            tina_config = project_root / 'tina/config.ts'
            astro_config = project_root / 'astro.config.mjs'
            island_route = project_root / 'src/pages/tina-island/[name].ts'
            api_route = project_root / 'src/pages/api/tina/[...routes].ts'
            if not tina_config.exists():
                issues.append(Issue('error', 'tina/config.ts', 'TinaCMS dependency present but tina/config.ts is missing'))
            else:
                tina_content = tina_config.read_text()
                if 'contentApiUrlOverride' not in tina_content:
                    issues.append(Issue('error', 'tina/config.ts', 'self-hosted TinaCMS config must set contentApiUrlOverride'))
                if 'LocalAuthProvider' in tina_content:
                    issues.append(Issue('error', 'tina/config.ts', 'LocalAuthProvider is not allowed in production astro-static; use the PasswordAuthProvider contract'))
                if 'authProvider' not in tina_content or 'PasswordAuthProvider' not in tina_content:
                    issues.append(Issue('error', 'tina/config.ts', 'self-hosted TinaCMS config must set authProvider with PasswordAuthProvider'))
                if 'router:' not in tina_content:
                    issues.append(Issue('error', 'tina/config.ts', 'maximum TinaCMS visual editing requires collection ui.router entries that open the live preview route'))
                # Check build config — publicFolder must be "." so admin SPA
                # lands at ./admin/ (project root), not inside dist/client/
                # which gets wiped by astro build.
                if 'publicFolder' in tina_content and 'dist/client' in tina_content:
                    issues.append(Issue('error', 'tina/config.ts', 'build.publicFolder must be "." not "dist/client" — admin SPA must live at project root to survive astro build'))
                # Check that collection paths match Astro content directories
                tina_paths = re.findall(r'path:\s*["\']src/content/(\w+)["\']', tina_content)
                for tina_path in tina_paths:
                    content_dir = project_root / 'src' / 'content' / tina_path
                    if not content_dir.exists():
                        issues.append(Issue('error', 'tina/config.ts', f'TinaCMS collection path "src/content/{tina_path}" does not exist — directory missing'))
            if not astro_config.exists():
                issues.append(Issue('error', 'astro.config.mjs', 'TinaCMS dependency present but astro.config.mjs is missing'))
            else:
                astro_content = astro_config.read_text()
                for needle, label in [
                    ('@tinacms/astro/integration', 'Tina Astro integration'),
                    ('@tinacms/astro/vite', 'Tina admin dev redirect'),
                    ('@astrojs/node', 'Astro Node adapter'),
                    ('tina()', 'tina() integration call'),
                ]:
                    if needle not in astro_content:
                        issues.append(Issue('error', 'astro.config.mjs', f'missing {label}'))
            if not island_route.exists():
                issues.append(Issue('error', 'src/pages/tina-island/[name].ts', 'missing Tina visual editing island route'))
            if not api_route.exists():
                issues.append(Issue('error', 'src/pages/api/tina/[...routes].ts', 'missing Tina self-hosted GraphQL route'))
            else:
                api_content = api_route.read_text()
                required_route_markers = [
                    ('POST /api/tina/login', '/api/tina/login'),
                    ('POST /api/tina/logout', '/api/tina/logout'),
                    ('GET /api/tina/auth-check', '/api/tina/auth-check'),
                    ('tina_admin_session cookie', 'tina_admin_session'),
                    ('PasswordBackendAuthProvider', 'PasswordBackendAuthProvider'),
                ]
                for label, marker in required_route_markers:
                    if marker not in api_content:
                        issues.append(Issue('error', 'src/pages/api/tina/[...routes].ts', f'missing Tina password auth backend contract: {label}'))
            project_source_files = []
            source_texts = []
            src_root = project_root / 'src'
            if src_root.exists():
                project_source_files = source_files(src_root)
                for source_path in project_source_files:
                    try:
                        source_texts.append(source_path.read_text())
                    except UnicodeDecodeError:
                        continue
            all_source = '\n'.join(source_texts)
            if 'requestWithMetadata' not in all_source:
                issues.append(Issue('error', 'src/lib/tina', 'maximum TinaCMS visual editing requires requestWithMetadata() data loaders'))
            if 'tinaField' not in all_source or 'data-tina-field' not in all_source:
                issues.append(Issue('error', 'src/components', 'maximum TinaCMS visual editing requires tinaField() + data-tina-field click-to-edit markers on visible editable DOM nodes'))
            validate_tina_editable_surfaces(project_root, project_source_files, issues)

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
