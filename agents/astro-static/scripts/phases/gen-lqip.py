#!/usr/bin/env python3
"""Generate a base64 WebP LQIP (Low-Quality Image Placeholder) for an image
and write it to a sibling `<stem>.lqip.txt` file.

The output is a `data:image/webp;base64,…` URI suitable for inline use as a
CSS `background-image`. The frontend-builder pairs this with the full
`<Image>` so visitors see a blurred preview during the brief moment between
HTML parse and image decode — a real LCP win on slow connections.

Usage:
  python3 gen-lqip.py <image_path>
  python3 gen-lqip.py <image_path> --width 32 --blur 1.5 --quality 40
  python3 gen-lqip.py <image_path> --out path/to/custom.lqip.txt

Exit codes:
  0  success — LQIP file written; data URI printed to stdout
  2  input image not found
  3  Pillow not installed
  4  unsafe input/output path
"""
from __future__ import annotations

import argparse
import base64
import sys
from io import BytesIO
from pathlib import Path

try:
    from PIL import Image, ImageFilter
except ImportError:
    print('ERROR: Pillow not installed. pip install Pillow', file=sys.stderr)
    raise SystemExit(3)


def make_lqip(img_path: Path, *, width: int, blur: float, quality: int) -> str:
    """Resize → blur → WebP-encode → base64-wrap as data URI."""
    src = Image.open(img_path)
    aspect = src.size[1] / src.size[0] if src.size[0] else 1.0
    new_h = max(1, int(round(width * aspect)))
    tiny = (
        src.convert('RGB')
           .resize((width, new_h), Image.LANCZOS)
           .filter(ImageFilter.GaussianBlur(blur))
    )
    buf = BytesIO()
    tiny.save(buf, format='WEBP', quality=quality)
    return 'data:image/webp;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


def safe_project_relative_path(path: Path, label: str) -> Path:
    """Resolve a user-supplied path only if it stays inside the current project."""
    if path.is_absolute():
        raise ValueError(f'unsafe_{label}_path: absolute paths are not allowed: {path}')
    if '..' in path.parts:
        raise ValueError(f'unsafe_{label}_path: path traversal is not allowed: {path}')
    project_root = Path.cwd().resolve()
    resolved = (project_root / path).resolve()
    try:
        resolved.relative_to(project_root)
    except ValueError:
        raise ValueError(f'unsafe_{label}_path: resolved path escapes project root: {path}')
    return resolved


def main() -> int:
    ap = argparse.ArgumentParser(description='Generate LQIP data URI sibling file.')
    ap.add_argument('image', type=Path, help='Path to source image (PNG/WebP/JPG)')
    ap.add_argument('--width', type=int, default=24,
                    help='LQIP width in pixels (default: 24)')
    ap.add_argument('--blur', type=float, default=2.0,
                    help='Gaussian blur radius (default: 2.0)')
    ap.add_argument('--quality', type=int, default=30,
                    help='WebP quality 1-100 (default: 30)')
    ap.add_argument('--out', type=Path, default=None,
                    help='Override output path (default: <stem>.lqip.txt next to source)')
    args = ap.parse_args()

    try:
        image_path = safe_project_relative_path(args.image, 'image')
        out = safe_project_relative_path(args.out, 'output') if args.out else image_path.with_name(image_path.stem + '.lqip.txt')
    except ValueError as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 4

    if not image_path.exists():
        print(f'ERROR: image not found: {args.image}', file=sys.stderr)
        return 2

    data_uri = make_lqip(image_path, width=args.width, blur=args.blur, quality=args.quality)
    out.write_text(data_uri, encoding='ascii')
    print(data_uri)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
