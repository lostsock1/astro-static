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
Draft202012Validator: Any = None
try:
    from jsonschema import Draft202012Validator as _Draft202012Validator  # type: ignore
    Draft202012Validator = _Draft202012Validator
    HAVE_JSONSCHEMA = True
except ImportError:
    HAVE_JSONSCHEMA = False

import os
_HERE = Path(__file__).resolve().parent
_CONFIG_ROOT = _HERE if (_HERE / 'agents').exists() else _HERE.parent
if (_HERE / 'agents' / 'astro-static' / 'schemas').exists():
    _DEFAULT_SCHEMA_DIR = _HERE / 'agents' / 'astro-static' / 'schemas'
elif (_HERE.parent / 'schemas').exists():
    _DEFAULT_SCHEMA_DIR = _HERE.parent / 'schemas'
else:
    _DEFAULT_SCHEMA_DIR = _HERE.parent / 'agents' / 'astro-static' / 'schemas'
SCHEMA_DIR = Path(os.environ.get('ASTRO_STATIC_SCHEMA_DIR', _DEFAULT_SCHEMA_DIR))

# Per-profile artifact maps. The astro-static profile uses vps-connection.json
# (multi-host bootstrap). The astro-ispconfig profile is single-host with
# preflight-result.json instead, and adds the image-shot-list contract.
PROFILES = {
    'astro-static': {
        'schema_dir': _DEFAULT_SCHEMA_DIR,
        'artifacts': {
            '00-brief.json':            '00-brief.schema.json',
            '01-creative-brief.json':   '01-creative-brief.schema.json',
            '01-tina-blueprint.json':   '01-tina-blueprint.schema.json',
            '03-tina-coverage.json':    '03-tina-coverage.schema.json',
            '02-font-config.json':      '02-font-config.schema.json',
            '02-asset-manifest.json':   '02-asset-manifest.schema.json',
            '02-image-shot-list.json':  '02-image-shot-list.schema.json',
            '02-video-shot-list.json':  '02-video-shot-list.schema.json',
            'vps-connection.json':      'vps-connection.schema.json',
            '00-pipeline-state.json':   '00-pipeline-state.schema.json',
        },
    },
    'ispconfig': {
        'schema_dir': _CONFIG_ROOT / 'agents' / 'astro-ispconfig' / 'schemas',
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
        'blueprint': {
            'required': {'01-creative-brief.json', '01-tina-blueprint.json'},
            'optional': {'00-pipeline-state.json'},
            'check_theme': False, 'check_layout': False, 'check_asset_paths': False,
            'strict': True, 'description': 'Tina blueprint contract produced',
        },
        'assets': {
            'required': {'00-brief.json', '01-creative-brief.json',
                         '01-tina-blueprint.json',
                         '02-font-config.json', '02-asset-manifest.json'} | connection_required,
            'optional': {'00-pipeline-state.json', '02-image-shot-list.json'} | video_shot_list,
            'check_theme': True, 'check_layout': False, 'check_asset_paths': True,
            'strict': True, 'description': 'Asset generation gate',
        },
        'build': {
            'required': {'00-brief.json', '01-creative-brief.json',
                          '01-tina-blueprint.json',
                          '03-tina-coverage.json',
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
    r'\b(?:src|poster|videoSrc|posterPath|image|bgImage)\s*[:=]\s*["\'](?P<path>(?:/(?:assets|images|media|uploads|videos)/|(?:\.\./)*src/assets/)[^"\']+)["\']'
)
CONTENT_SRC_ASSETS_RE = re.compile(
    r'\b(?:src|poster|videoSrc|posterPath|image|bgImage)\s*[:=]\s*["\'](?P<path>(?:\.\./)*src/assets/[^"\']+)["\']'
)
BACKGROUND_IMAGE_LITERAL_RE = re.compile(
    r'(?:background(?:-image)?\s*:\s*url\(\s*["\']?|bg-\[url\(\s*["\']?)'
    r'(?P<path>(?:/(?:assets|images|media|uploads|videos)/|(?:\.\./)*src/assets/)[^"\'\)\]\s]+)',
    re.IGNORECASE,
)
STRING_ASSIGNMENT_RE = re.compile(
    r'\b(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*(?P<quote>["\'`])(?P<value>[^"\'`\n]{8,})(?P=quote)'
)
OBJECT_COPY_FIELD_RE = re.compile(
    r'\b(?P<name>title|subtitle|heading|headline|eyebrow|description|desc|intro|caption|copy|quote|label|note|value|outlet|day|event|time|loc|location|ctaText|placeholderText)\s*:\s*(?P<quote>["\'`])(?P<value>[^"\'`\n]{3,})(?P=quote)'
)
VISIBLE_COMPONENT_PROP_RE = re.compile(
    r'(?<![-\w])(?P<name>brandName|tagline|foundedLabel|locationText|mapsLinkText|copyrightText|label|placeholderText|ctaText|mobileCtaText)\s*=\s*(?P<quote>["\'])(?P<value>[^"\'\n]{3,})(?P=quote)'
)
ALLOWED_STATIC_COPY_RE = re.compile(
    r'\bdata-static-copy\s*=\s*(?P<quote>["\'])(?:ui|chrome|control|decorative|legal)(?P=quote)'
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
    return (
        'data-static-media' in attrs
        or 'aria-hidden="true"' in attrs
        or "aria-hidden='true'" in attrs
        or ALLOWED_STATIC_COPY_RE.search(attrs) is not None
    )


def has_unqualified_static_copy(attrs: str) -> bool:
    return 'data-static-copy' in attrs and ALLOWED_STATIC_COPY_RE.search(attrs) is None


def looks_like_copy_variable_name(name: str) -> bool:
    lower = name.lower().replace('_', '').replace('-', '')
    exact_names = {
        'title', 'subtitle', 'heading', 'headline', 'eyebrow', 'description',
        'intro', 'caption', 'copy', 'text', 'label', 'quote', 'ctalabel',
        'ctatext', 'buttonlabel', 'buttontext',
    }
    semantic_suffixes = (
        'title', 'subtitle', 'heading', 'headline', 'eyebrow', 'description',
        'intro', 'caption', 'copy', 'quote', 'label',
    )
    return lower in exact_names or lower.endswith(semantic_suffixes)


def looks_like_utility_or_field_literal(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return True
    if stripped.startswith(('/', './', '../', '#')) or stripped.startswith(('http://', 'https://')):
        return True
    if re.fullmatch(r'[A-Za-z0-9_.:-]+', stripped) and '.' in stripped:
        # Tina field references like page.title or collection.entry.field.
        return True
    utility_tokens = ('text-', 'bg-', 'px-', 'py-', 'mx-', 'my-', 'mt-', 'mb-', 'grid', 'flex', 'rounded', 'w-', 'h-', 'md:', 'lg:')
    return any(token in stripped for token in utility_tokens)


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
                plain_body = strip_tags(body)
                if has_unqualified_static_copy(attrs) and looks_like_copy(plain_body):
                    issues.append(Issue(
                        'error', rel,
                        f'line {line_number(visible_markup, match.start())}: data-static-copy must be reserved for non-marketing UI chrome with an explicit reason such as data-static-copy="ui"; move visible site copy into Tina content: "{snippet(plain_body)}"',
                    ))
                    continue
                if has_static_escape(attrs) or 'data-tina-field' in attrs:
                    continue
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
            if has_static_escape(line):
                continue
            issues.append(Issue(
                'error', rel,
                f'line {line_number(visible_markup, match.start())}: hardcoded media path must be Tina/content/manifest-backed: {match.group("path")}',
            ))

        for match in BACKGROUND_IMAGE_LITERAL_RE.finditer(content):
            line_start = content.rfind('\n', 0, match.start()) + 1
            line_end = content.find('\n', match.start())
            if line_end == -1:
                line_end = len(content)
            line = content[line_start:line_end]
            if has_static_escape(line):
                continue
            issues.append(Issue(
                'error', rel,
                f'line {line_number(content, match.start())}: hardcoded background image must be Tina/content/manifest-backed with an editable image field: {match.group("path")}',
            ))

        for match in MEDIA_DEFAULT_RE.finditer(frontmatter):
            issues.append(Issue(
                'error', rel,
                f'line {line_number(frontmatter, match.start())}: hardcoded media path must be Tina/content/manifest-backed: {match.group("path")}',
            ))

        for match in STRING_ASSIGNMENT_RE.finditer(frontmatter):
            name = match.group('name')
            value = match.group('value')
            if not looks_like_copy_variable_name(name):
                continue
            if looks_like_utility_or_field_literal(value) or not looks_like_copy(value):
                continue
            issues.append(Issue(
                'error', rel,
                f'line {line_number(frontmatter, match.start())}: hardcoded copy variable "{name}" not backed by Tina content: "{snippet(value)}"',
            ))

        for match in OBJECT_COPY_FIELD_RE.finditer(frontmatter):
            name = match.group('name')
            value = match.group('value')
            if looks_like_utility_or_field_literal(value) or not looks_like_copy(value):
                continue
            issues.append(Issue(
                'error', rel,
                f'line {line_number(frontmatter, match.start())}: hardcoded copy object field "{name}" not backed by Tina content: "{snippet(value)}"',
            ))

        for match in VISIBLE_COMPONENT_PROP_RE.finditer(visible_markup):
            name = match.group('name')
            value = match.group('value')
            if looks_like_utility_or_field_literal(value) or not looks_like_copy(value):
                continue
            issues.append(Issue(
                'error', rel,
                f'line {line_number(visible_markup, match.start())}: hardcoded visible component prop "{name}" must come from Tina/settings content: "{snippet(value)}"',
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


def _find_matching_brace(text: str, start: int) -> int:
    depth = 0
    in_string: str | None = None
    escape = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == in_string:
                in_string = None
            continue
        if ch in {'"', "'", '`'}:
            in_string = ch
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return idx
    return -1


def _collection_block_for_path(tina_content: str, path_offset: int) -> str:
    start = tina_content.rfind('{', 0, path_offset)
    while start != -1:
        end = _find_matching_brace(tina_content, start)
        if end != -1 and end >= path_offset:
            block = tina_content[start:end + 1]
            if 'path:' in block and 'src/content/' in block:
                return block
        start = tina_content.rfind('{', 0, start)
    window_start = max(0, path_offset - 500)
    window_end = min(len(tina_content), path_offset + 800)
    return tina_content[window_start:window_end]


def _extract_tina_collections(tina_content: str) -> list[dict[str, str]]:
    collections: list[dict[str, str]] = []
    for match in re.finditer(r'path:\s*["\']src/content/(?P<path>[^"\']+)["\']', tina_content):
        block = _collection_block_for_path(tina_content, match.start())
        name_match = re.search(r'name:\s*["\'](?P<name>[\w-]+)["\']', block)
        format_match = re.search(r'format:\s*["\'](?P<format>\w+)["\']', block)
        collections.append({
            'name': name_match.group('name') if name_match else match.group('path'),
            'path': match.group('path'),
            'format': (format_match.group('format') if format_match else 'md').lower(),
        })
    return collections


def _content_frontmatter(path: Path) -> str:
    try:
        text = path.read_text()
    except UnicodeDecodeError:
        return ''
    if path.suffix in {'.md', '.mdx'} and text.startswith('---'):
        end = text.find('\n---', 3)
        if end != -1:
            return text[: end + 4]
    if path.suffix == '.json':
        return text
    return ''


def validate_tina_content_contracts(project_root: Path, tina_content: str, issues: list[Issue]) -> None:
    """Validate Tina collection contracts against file-backed content.

    Tina's FilesystemBridge indexes files by collection format. If a collection
    says `format: "mdx"` but the files are `.md`, the admin silently appears
    empty even though Astro's content loader may still render the site. Content
    image fields also cannot point at raw `src/assets/**` paths because those
    are Vite module inputs, not public URLs or Tina media entries.
    """
    for collection in _extract_tina_collections(tina_content):
        content_dir = project_root / 'src' / 'content' / collection['path']
        if not content_dir.exists():
            continue
        expected_suffix = f".{collection['format']}"
        if collection['format'] in {'md', 'mdx', 'json'}:
            for content_file in content_dir.rglob('*'):
                if not content_file.is_file() or content_file.name.startswith('.'):
                    continue
                if content_file.suffix not in {'.md', '.mdx', '.json'}:
                    continue
                rel = str(content_file.relative_to(project_root))
                if content_file.suffix != expected_suffix:
                    issues.append(Issue(
                        'error', 'tina/config.ts',
                        f'TinaCMS collection "{collection["name"]}" declares format "{collection["format"]}" but {rel} has extension "{content_file.suffix}"; align collection format with file extensions so the admin indexes documents',
                    ))
        for content_file in content_dir.rglob('*'):
            if not content_file.is_file() or content_file.suffix not in {'.md', '.mdx', '.json'}:
                continue
            frontmatter = _content_frontmatter(content_file)
            for match in CONTENT_SRC_ASSETS_RE.finditer(frontmatter):
                rel = str(content_file.relative_to(project_root))
                issues.append(Issue(
                    'error', rel,
                    f'line {line_number(frontmatter, match.start())}: Tina content image fields must not store raw src/assets paths; copy media to public/images or resolve through a generated contentImages map: {match.group("path")}',
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
    if Draft202012Validator is None:
        issues.append(Issue('error', artifact, 'jsonschema library required but Draft202012Validator is unavailable'))
        return
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


FALLBACK_UNSUPPORTED_KEYWORDS = {
    'allOf', 'anyOf', 'oneOf', 'if', 'then', 'else', 'not', 'const',
    'format', 'pattern', 'minLength', 'maxLength', 'minItems', 'maxItems',
    'minProperties', 'maxProperties', 'minimum', 'maximum', 'exclusiveMinimum',
    'exclusiveMaximum', 'multipleOf', 'uniqueItems', 'contains',
}


def schema_keywords_requiring_jsonschema(schema: Any, path: str = '$') -> list[str]:
    """Return advanced JSON Schema keywords the fallback validator cannot safely enforce."""
    found: list[str] = []
    if isinstance(schema, dict):
        for key, value in schema.items():
            if key in FALLBACK_UNSUPPORTED_KEYWORDS:
                found.append(f'{path}.{key}')
            elif key == 'additionalProperties' and value is False:
                found.append(f'{path}.additionalProperties=false')
            if isinstance(value, (dict, list)):
                found.extend(schema_keywords_requiring_jsonschema(value, f'{path}.{key}'))
    elif isinstance(schema, list):
        for idx, item in enumerate(schema):
            found.extend(schema_keywords_requiring_jsonschema(item, f'{path}[{idx}]'))
    return found


def validate_value(value: Any, schema: dict[str, Any], root: dict[str, Any], path: str, issues: list[Issue], artifact: str) -> None:
    """Dispatch to jsonschema library when available, hand-rolled fallback otherwise."""
    if HAVE_JSONSCHEMA:
        validate_with_jsonschema(value, schema, issues, artifact)
    else:
        unsupported = schema_keywords_requiring_jsonschema(schema)
        if unsupported:
            preview = ', '.join(unsupported[:8])
            if len(unsupported) > 8:
                preview += f', ... ({len(unsupported)} total)'
            issues.append(Issue('error', artifact, f'jsonschema library required for schema keywords unsupported by fallback subset: {preview}'))
            return
        validate_with_fallback(value, schema, root, path, issues, artifact)


def validate_tina_blueprint_contract(data: dict[str, Any], issues: list[Issue]) -> None:
    """Semantic checks for the Tina-first editable content contract.

    The JSON Schema covers structure; these checks produce stable, actionable
    messages even when the fallback schema validator is in use.
    """
    settings = data.get('settings')
    if not isinstance(settings, dict):
        issues.append(Issue('error', '01-tina-blueprint.json', 'settings must be an object with siteName, nav, footerLinks, copyrightText, and seo'))
    else:
        for key in ('siteName', 'nav', 'footerLinks', 'copyrightText', 'seo'):
            if key not in settings:
                issues.append(Issue('error', '01-tina-blueprint.json', f'settings missing required {key}'))
        nav = settings.get('nav')
        if not isinstance(nav, list) or not nav:
            issues.append(Issue('error', '01-tina-blueprint.json', 'settings.nav must contain at least one navigation item'))
        footer_links = settings.get('footerLinks')
        if not isinstance(footer_links, list):
            issues.append(Issue('error', '01-tina-blueprint.json', 'settings.footerLinks must be an array of footer-owned editable links'))
        if not isinstance(settings.get('copyrightText'), str) or not settings.get('copyrightText'):
            issues.append(Issue('error', '01-tina-blueprint.json', 'settings.copyrightText must be a non-empty editable string'))

    pages = data.get('pages')
    if isinstance(pages, list):
        seen_page_ids: set[str] = set()
        for page_idx, page in enumerate(pages):
            if not isinstance(page, dict):
                continue
            page_id = str(page.get('id') or '')
            if page_id and page_id in seen_page_ids:
                issues.append(Issue('error', '01-tina-blueprint.json', f'pages[{page_idx}] duplicate id {page_id}'))
            if page_id:
                seen_page_ids.add(page_id)
            seen_section_ids: set[str] = set()
            sections = page.get('sections')
            if not isinstance(sections, list):
                continue
            for section_idx, section in enumerate(sections):
                if not isinstance(section, dict):
                    continue
                section_id = str(section.get('id') or '')
                if section_id and section_id in seen_section_ids:
                    issues.append(Issue('error', '01-tina-blueprint.json', f'pages[{page_idx}].sections[{section_idx}] duplicate id {section_id}'))
                if section_id:
                    seen_section_ids.add(section_id)

    surfaces = data.get('editable_surface_map')
    if not isinstance(surfaces, list) or not surfaces:
        issues.append(Issue('error', '01-tina-blueprint.json', 'editable_surface_map must contain every visible/editable field'))
        surfaces = []
    for idx, surface in enumerate(surfaces):
        if not isinstance(surface, dict):
            issues.append(Issue('error', '01-tina-blueprint.json', f'editable_surface_map[{idx}] must be an object'))
            continue
        for key in ('field_ref', 'field_type', 'owner', 'source_default', 'tina_field_path', 'content_path', 'render_intent', 'required_marker'):
            if key not in surface or surface.get(key) in ('', None):
                issues.append(Issue('error', '01-tina-blueprint.json', f'editable_surface_map[{idx}] missing required {key}'))
        if surface.get('required_marker') == 'static-exempt' and not surface.get('static_exemption_reason'):
            issues.append(Issue('error', '01-tina-blueprint.json', f'editable_surface_map[{idx}] static-exempt field missing static_exemption_reason'))
    for key in ('field_ref', 'tina_field_path', 'content_path'):
        seen_values: set[str] = set()
        for idx, surface in enumerate(surfaces):
            if not isinstance(surface, dict):
                continue
            value = surface.get(key)
            if not isinstance(value, str) or not value:
                continue
            if value in seen_values:
                issues.append(Issue('error', '01-tina-blueprint.json', f'editable_surface_map[{idx}] duplicate {key}: {value}'))
            seen_values.add(value)

    media_fields = data.get('media_fields')
    if not isinstance(media_fields, list):
        issues.append(Issue('error', '01-tina-blueprint.json', 'media_fields must be an array'))
        media_fields = []
    for idx, media in enumerate(media_fields):
        if not isinstance(media, dict):
            issues.append(Issue('error', '01-tina-blueprint.json', f'media_fields[{idx}] must be an object'))
            continue
        for key in ('field_ref', 'field_type', 'source_default', 'tina_field_path', 'content_path', 'render_intent', 'required_marker', 'surface_kind'):
            if key not in media or media.get(key) in ('', None):
                issues.append(Issue('error', '01-tina-blueprint.json', f'media_fields[{idx}] missing required {key}'))
    seen_media_refs: set[str] = set()
    for idx, media in enumerate(media_fields):
        if not isinstance(media, dict):
            continue
        field_ref = media.get('field_ref')
        if not isinstance(field_ref, str) or not field_ref:
            continue
        if field_ref in seen_media_refs:
            issues.append(Issue('error', '01-tina-blueprint.json', f'media_fields[{idx}] duplicate field_ref: {field_ref}'))
        seen_media_refs.add(field_ref)


def validate_tina_coverage_contract(pipeline_dir: Path, phase_name: str | None, issues: list[Issue]) -> None:
    """Ensure frontend codegen proved coverage for every blueprint editable field."""
    if phase_name not in {'build', 'final'}:
        return
    blueprint = _load_pipeline_json(pipeline_dir / '01-tina-blueprint.json')
    coverage_doc = _load_pipeline_json(pipeline_dir / '03-tina-coverage.json')
    if not isinstance(blueprint, dict) or not isinstance(coverage_doc, dict):
        return

    surfaces = blueprint.get('editable_surface_map')
    coverage_entries = coverage_doc.get('coverage')
    if not isinstance(surfaces, list) or not isinstance(coverage_entries, list):
        return

    blueprint_by_ref: dict[str, dict[str, Any]] = {}
    for surface in surfaces:
        if isinstance(surface, dict) and isinstance(surface.get('field_ref'), str):
            blueprint_by_ref[surface['field_ref']] = surface

    coverage_by_ref: dict[str, dict[str, Any]] = {}
    for idx, entry in enumerate(coverage_entries):
        if not isinstance(entry, dict):
            continue
        field_ref = entry.get('field_ref')
        if not isinstance(field_ref, str) or not field_ref:
            continue
        if field_ref in coverage_by_ref:
            issues.append(Issue('error', '03-tina-coverage.json', f'coverage[{idx}] duplicate field_ref: {field_ref}'))
        coverage_by_ref[field_ref] = entry
        if field_ref not in blueprint_by_ref:
            issues.append(Issue('error', '03-tina-coverage.json', f'coverage[{idx}] field_ref is not declared in blueprint: {field_ref}'))
        if entry.get('declared_in_blueprint') is not True:
            issues.append(Issue('error', '03-tina-coverage.json', f'coverage[{idx}] declared_in_blueprint must be true: {field_ref}'))

    for field_ref, surface in blueprint_by_ref.items():
        entry = coverage_by_ref.get(field_ref)
        if entry is None:
            issues.append(Issue('error', '03-tina-coverage.json', f'missing coverage for blueprint field_ref: {field_ref}'))
            continue
        if entry.get('surface_kind') != surface.get('surface_kind'):
            issues.append(Issue(
                'error', '03-tina-coverage.json',
                f'coverage surface_kind mismatch for {field_ref}: expected {surface.get("surface_kind")}, got {entry.get("surface_kind")}',
            ))
        required_marker = surface.get('required_marker')
        if required_marker == 'data-tina-field' and entry.get('has_tina_field_marker') is not True:
            issues.append(Issue('error', '03-tina-coverage.json', f'coverage missing data-tina-field proof for {field_ref}'))


SECRET_ARTIFACTS = {'vps-connection.json', 'bootstrap-result.json', 'installation-summary.md', 'installation.log'}

CANONICAL_PACKAGE_RANGES = {
    'astro': '^7.0.2',
    '@astrojs/node': '^11.0.0',
    '@astrojs/mdx': '^7.0.0',
    '@astrojs/react': '^6.0.0',
    '@tailwindcss/vite': '^4.3.1',
    'tailwindcss': '^4.3.1',
    '@tinacms/astro': '^0.5.0',
    'tinacms': '^3.9.3',
    '@tinacms/cli': '^2.5.1',
}

REQUIRED_GITIGNORE_PATTERNS = {
    'node_modules/',
    'dist/',
    '.astro/',
    '.opencode/',
    '.env',
    '.env.*',
    '*.log',
    'pipeline/vps-connection.json',
    'pipeline/vps-connection.json.*',
    'pipeline/.git-credentials',
    'pipeline/bootstrap-result.json',
    'pipeline/bootstrap-result.json.*',
    'pipeline/bootstrap*.json',
    'pipeline/bootstrap*.log',
    'pipeline/bootstrap*.pid',
    'pipeline/bootstrap*.exit',
    'pipeline/installation-summary.md',
    'pipeline/installation.log',
    'pipeline/setup-wrapper.*',
    'pipeline/RESULT.md',
    'pipeline/HUMAN_REVIEW.md',
}


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


def validate_package_matrix(deps: dict[str, Any], issues: list[Issue]) -> None:
    """Keep generated projects pinned to the pipeline's tested Astro/Tina stack."""
    for package_name, expected_range in CANONICAL_PACKAGE_RANGES.items():
        actual = deps.get(package_name)
        if actual is None:
            issues.append(Issue(
                'error', 'package.json',
                f'missing canonical dependency {package_name}@{expected_range}',
            ))
        elif actual != expected_range:
            issues.append(Issue(
                'error', 'package.json',
                f'{package_name} must use tested range {expected_range}, got {actual!r}',
            ))


def validate_gitignore_safety(project_root: Path, issues: list[Issue]) -> None:
    """Prevent Gitea pushes from committing generated output or local secrets."""
    gitignore = project_root / '.gitignore'
    if not gitignore.exists():
        issues.append(Issue('error', '.gitignore', 'missing .gitignore — generated output and secrets may be committed'))
        return

    patterns = {
        line.strip()
        for line in gitignore.read_text(errors='replace').splitlines()
        if line.strip() and not line.strip().startswith('#')
    }
    for pattern in sorted(REQUIRED_GITIGNORE_PATTERNS):
        if pattern not in patterns:
            issues.append(Issue(
                'error', '.gitignore',
                f'missing required ignore pattern for safe pipeline pushes: {pattern}',
            ))

    for forbidden in ('admin/', 'admin/**', '/admin/', '/admin/**'):
        if forbidden in patterns:
            issues.append(Issue(
                'error', '.gitignore',
                'admin/ must not be ignored — TinaCMS admin SPA is built locally and committed/pushed',
            ))

    if (project_root / 'admin/.gitignore').exists():
        issues.append(Issue(
            'error', 'admin/.gitignore',
            'remove admin/.gitignore — tinacms build creates it but the pipeline must commit admin/index.html and assets',
        ))


def validate_tina_tsconfig(project_root: Path, issues: list[Issue]) -> None:
    tsconfig = project_root / 'tsconfig.json'
    if not tsconfig.exists():
        issues.append(Issue('error', 'tsconfig.json', 'TinaCMS projects must include tsconfig.json with generated-directory excludes'))
        return
    try:
        data = json.loads(tsconfig.read_text())
    except Exception as exc:
        issues.append(Issue('error', 'tsconfig.json', f'invalid JSON: {exc}'))
        return
    excludes = data.get('exclude')
    if not isinstance(excludes, list):
        issues.append(Issue('error', 'tsconfig.json', 'must set exclude to include admin/**, dist/**, and node_modules/**'))
        return
    exclude_set = {item for item in excludes if isinstance(item, str)}
    for required in ('admin/**', 'dist/**', 'node_modules/**'):
        if required not in exclude_set:
            issues.append(Issue(
                'error', 'tsconfig.json',
                f'missing exclude entry {required}; generated Tina/build output must not be type-checked',
            ))


def validate_tina_auth_user_shape(tina_content: str, issues: list[Issue]) -> None:
    if 'PasswordAuthProvider' not in tina_content:
        return
    if re.search(r'return\s+\(\s*await\s+fetch\(["\']/api/tina/auth-check["\']\)\s*\)\.ok', tina_content):
        issues.append(Issue(
            'error', 'tina/config.ts',
            'PasswordAuthProvider.getUser must return a user object with name/email after auth-check succeeds; returning boolean .ok makes Tina read undefined.name',
        ))
        return
    returns_named_user = re.search(r'return\s+\{[^}]*\bname\s*:', tina_content, re.DOTALL) is not None
    probes_auth_check = '/api/tina/auth-check' in tina_content
    if not returns_named_user or not probes_auth_check:
        issues.append(Issue(
            'error', 'tina/config.ts',
            'PasswordAuthProvider.getUser must probe /api/tina/auth-check and return a user object containing name',
        ))


def validate_tina_admin_artifacts(project_root: Path, issues: list[Issue]) -> None:
    admin_dir = project_root / 'admin'
    required_files = [
        ('admin/index.html', project_root / 'admin/index.html'),
        ('admin/login.html', project_root / 'admin/login.html'),
        ('admin/bridge.js', project_root / 'admin/bridge.js'),
        ('tina/__generated__/_schema.json', project_root / 'tina/__generated__/_schema.json'),
    ]
    for label, path in required_files:
        if not path.exists():
            issues.append(Issue('error', label, f'missing TinaCMS deployment artifact: {label}'))
    if admin_dir.exists():
        try:
            admin_size = sum(path.stat().st_size for path in admin_dir.rglob('*') if path.is_file())
        except OSError as exc:
            issues.append(Issue('error', 'admin/', f'cannot stat admin artifacts: {exc}'))
        else:
            if admin_size <= 50 * 1024:
                issues.append(Issue('error', 'admin/', f'admin SPA too small ({admin_size} bytes); run tinacms-local-build.sh'))
    bridge = project_root / 'admin/bridge.js'
    if bridge.exists() and bridge.stat().st_size <= 1000:
        issues.append(Issue('error', 'admin/bridge.js', 'bridge.js is too small; copy node_modules/@tinacms/bridge/dist/index.js, not the @tinacms/astro re-export stub'))


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

    if artifact_name == '01-tina-blueprint.json' and isinstance(data, dict):
        validate_tina_blueprint_contract(data, issues)

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


def validate_instagram_content_image_handoff(pipeline_dir: Path, phase_name: str | None, issues: list[Issue]) -> None:
    """Reject placeholder-only content images when usable Instagram photos exist.

    Instagram extraction writes downloaded source images to
    pipeline/00-instagram/assets/. When instagram_use is "both" (or an explicit
    content/media value), Phase 3.5 must prefer those real photos before falling
    back to deterministic SVG placeholders.
    """
    if phase_name not in {'assets', 'build', 'final'}:
        return

    brief_path = pipeline_dir / '00-brief.json'
    manifest_path = pipeline_dir / '02-asset-manifest.json'
    if not brief_path.exists() or not manifest_path.exists():
        return

    try:
        brief = load_json(brief_path)
        manifest = load_json(manifest_path)
    except (json.JSONDecodeError, OSError):
        return
    if not isinstance(brief, dict) or not isinstance(manifest, dict):
        return

    instagram_use = str(brief.get('instagram_use', '')).lower()
    if instagram_use not in {'both', 'content', 'content_images', 'media', 'photos'}:
        return

    ig_assets_dir = pipeline_dir / '00-instagram' / 'assets'
    if not ig_assets_dir.exists():
        return
    usable_assets = [
        asset for asset in ig_assets_dir.iterdir()
        if asset.is_file()
        and asset.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp', '.avif'}
        and asset.stat().st_size >= 10 * 1024
    ]
    if len(usable_assets) < 3:
        return

    content_images = manifest.get('content_images')
    if not isinstance(content_images, list) or not content_images:
        return
    renderable_entries = [entry for entry in content_images if isinstance(entry, dict) and entry.get('status') != 'failed']
    if not renderable_entries:
        return

    has_instagram_entry = any(
        str(entry.get('status', '')).lower() == 'scraped_instagram'
        or str(entry.get('source', '')).lower().startswith('instagram')
        or '00-instagram' in str(entry.get('source_path', ''))
        or '/instagram/' in str(entry.get('path', ''))
        for entry in renderable_entries
    )
    if has_instagram_entry:
        return

    if all(str(entry.get('status', '')).lower() == 'placeholder' for entry in renderable_entries):
        issues.append(Issue(
            'error',
            '02-asset-manifest.json',
            f'Instagram assets exist ({len(usable_assets)} usable files in pipeline/00-instagram/assets/) and instagram_use is "{instagram_use}", but every content image is still a placeholder; copy/select scraped Instagram photos into public/images or mark manifest entries with status: "scraped_instagram" before falling back to deterministic placeholders',
        ))


INSTAGRAM_CONTENT_USES = {'both', 'content', 'content_images', 'media', 'photos'}


def _load_pipeline_json(path: Path) -> Any | None:
    try:
        return load_json(path)
    except (json.JSONDecodeError, OSError):
        return None


def _usable_instagram_assets(pipeline_dir: Path) -> list[Path]:
    ig_assets_dir = pipeline_dir / '00-instagram' / 'assets'
    if not ig_assets_dir.exists():
        return []
    return [
        asset for asset in ig_assets_dir.iterdir()
        if asset.is_file()
        and asset.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp', '.avif'}
        and asset.stat().st_size >= 10 * 1024
    ]


def _entry_is_instagram_backed(entry: dict[str, Any]) -> bool:
    return (
        str(entry.get('status', '')).lower() == 'scraped_instagram'
        or str(entry.get('source', '')).lower().startswith('instagram')
        or '00-instagram' in str(entry.get('source_path', '')).lower()
        or '/instagram/' in str(entry.get('path', '')).lower()
        or '/instagram/' in str(entry.get('public_path', '')).lower()
    )


def _normalise_media_refs(*values: Any) -> set[str]:
    refs: set[str] = set()
    for value in values:
        if isinstance(value, str) and value.strip():
            refs.add(value.strip())
    return refs


def _url_matches_instagram_media(url: str, instagram_refs: set[str]) -> bool:
    lowered = url.lower()
    if 'instagram' in lowered or '/00-instagram/' in lowered or '/images/instagram/' in lowered:
        return True
    try:
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or '').lower().rstrip('.')
    except Exception:
        host = ''
    if (
        host == 'cdninstagram.com'
        or host.endswith('.cdninstagram.com')
        or host == 'fbcdn.net'
        or host.endswith('.fbcdn.net')
    ):
        return True
    return any(ref and (url == ref or url.endswith(ref) or ref in url) for ref in instagram_refs)


def validate_instagram_video_background_handoff(pipeline_dir: Path, phase_name: str | None, issues: list[Issue]) -> None:
    """Require Instagram-backed image-to-video inputs for requested background clips.

    When Instagram is an explicit content/media source and video backgrounds are
    requested, Phase 3.6 must animate the selected Instagram stills via i2v.
    Merely generating unrelated t2v clips — or using the Instagram still only as
    a static poster — breaks the user's content-source expectation.
    """
    if phase_name not in {'assets', 'build', 'final'}:
        return

    brief = _load_pipeline_json(pipeline_dir / '00-brief.json')
    creative = _load_pipeline_json(pipeline_dir / '01-creative-brief.json')
    manifest = _load_pipeline_json(pipeline_dir / '02-asset-manifest.json')
    if not isinstance(brief, dict) or not isinstance(creative, dict) or not isinstance(manifest, dict):
        return

    instagram_use = str(brief.get('instagram_use', '')).lower()
    if instagram_use not in INSTAGRAM_CONTENT_USES:
        return

    usable_assets = _usable_instagram_assets(pipeline_dir)
    if len(usable_assets) < 3:
        return

    motion_direction = creative.get('motion_direction')
    video_requested = isinstance(motion_direction, dict) and motion_direction.get('video_backgrounds') is True
    video_backgrounds = manifest.get('video_backgrounds')
    has_video_entries = isinstance(video_backgrounds, list) and bool(video_backgrounds)
    if not video_requested and not has_video_entries:
        return
    if not has_video_entries:
        if phase_name in {'build', 'final'}:
            issues.append(Issue(
                'error', '02-asset-manifest.json',
                f'Instagram assets exist ({len(usable_assets)} usable files) and video backgrounds are requested, but video_backgrounds is empty; derive AI-animated background clips from selected Instagram stills before build/final validation',
            ))
        return

    instagram_refs: set[str] = set()
    content_images = manifest.get('content_images', [])
    if isinstance(content_images, list):
        for entry in content_images:
            if not isinstance(entry, dict) or not _entry_is_instagram_backed(entry):
                continue
            instagram_refs.update(_normalise_media_refs(
                entry.get('path'),
                entry.get('public_path'),
                entry.get('source_path'),
            ))

    video_entries = video_backgrounds if isinstance(video_backgrounds, list) else []
    for video in video_entries:
        if not isinstance(video, dict) or str(video.get('status', '')).lower() == 'failed':
            continue
        image_url = video.get('image_url')
        if not isinstance(image_url, str) or not image_url.strip():
            issues.append(Issue(
                'error', '02-asset-manifest.json',
                f'Instagram content source requires image-to-video background input: id={video.get("id", "?")} is missing image_url from a selected Instagram still',
            ))
            continue
        if not _url_matches_instagram_media(image_url.strip(), instagram_refs):
            issues.append(Issue(
                'error', '02-asset-manifest.json',
                f'Instagram content source requires image-to-video background input from scraped Instagram media: id={video.get("id", "?")} image_url={image_url}',
            ))



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

    validate_instagram_content_image_handoff(pipeline_dir, phase_name, issues)
    validate_instagram_video_background_handoff(pipeline_dir, phase_name, issues)
    validate_tina_coverage_contract(pipeline_dir, phase_name, issues)

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
                        try:
                            profile_schema = load_json(SCHEMA_DIR / '00-instagram-extraction.schema.json')
                            validate_value(profile_data, profile_schema, profile_schema, '$', issues, '00-instagram/profile.json')
                        except Exception as exc:
                            issues.append(Issue('error', '00-instagram/profile.json', f'cannot load schema: {exc}'))
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

    if phase_name in {'build', 'final'} or require_all:
        validate_gitignore_safety(project_root, issues)

    package_json = project_root / 'package.json'
    if package_json.exists():
        try:
            package_data = json.loads(package_json.read_text())
        except json.JSONDecodeError as exc:
            issues.append(Issue('error', 'package.json', f'invalid JSON: {exc}'))
            package_data = {}
        deps = {**package_data.get('dependencies', {}), **package_data.get('devDependencies', {})}
        if phase_name in {'build', 'final'} or require_all:
            validate_package_matrix(deps, issues)
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
                validate_tina_auth_user_shape(tina_content, issues)
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
                validate_tina_content_contracts(project_root, tina_content, issues)
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
            else:
                island_content = island_route.read_text()
                if 'export const ALL' in island_content or 'export const POST' not in island_content:
                    issues.append(Issue('error', 'src/pages/tina-island/[name].ts', 'Tina visual editing island route must export POST, not ALL'))
                imports_island_registry = re.search(r'import\s+\{?\s*islands\b', island_content) is not None
                has_inline_island_fetch = re.search(r'\bislands\s*=\s*\{[\s\S]*\bfetch\s*:', island_content) is not None
                has_empty_registry = re.search(r'\bislands\s*=\s*\{\s*\}', island_content) is not None
                if has_empty_registry or not (imports_island_registry or has_inline_island_fetch):
                    issues.append(Issue('error', 'src/pages/tina-island/[name].ts', 'Tina visual editing island registry appears empty; register at least one island with fetch/component/wrapper/propsFromData so bridge refreshes editable regions'))
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
            for source_path in project_source_files:
                if source_path.suffix != '.astro':
                    continue
                try:
                    page_source = source_path.read_text()
                except UnicodeDecodeError:
                    continue
                if 'astro:content' in page_source and 'requestWithMetadata' not in page_source:
                    rel = str(source_path.relative_to(project_root))
                    issues.append(Issue('error', rel, 'Astro content-backed Tina page must call requestWithMetadata() in the page data loader; a re-export in src/lib/tina/data.ts does not register this page with the admin'))
            validate_tina_tsconfig(project_root, issues)
            if phase_name == 'final' or require_all:
                validate_tina_admin_artifacts(project_root, issues)
            validate_tina_editable_surfaces(project_root, project_source_files, issues)
    elif phase_name in {'build', 'final'} or require_all:
        issues.append(Issue('error', 'package.json', f'missing file: {package_json}'))

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
    parser.add_argument('--phase', choices=sorted(PHASES.keys()), help='Validate a specific workflow phase gate: startup, research, blueprint, assets, build, final')
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
