#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "astro-static-tina-blueprint/v1"
SUPPORTED_BLOCKS = {
    "hero": "HeroBlock",
    "splitFeature": "SplitFeatureBlock",
    "featureGrid": "FeatureGridBlock",
    "cardGrid": "CardGridBlock",
    "gallery": "GalleryBlock",
    "testimonial": "TestimonialBlock",
    "cta": "CtaBlock",
    "faq": "FaqBlock",
    "contact": "ContactBlock",
    "richText": "RichTextBlock",
    "mediaFeature": "MediaFeatureBlock",
    "eventSchedule": "EventScheduleBlock",
    "teamGrid": "TeamGridBlock",
}

SECTION_ID_BASES = {
    "hero": "hero",
    "splitFeature": "split-feature",
    "featureGrid": "features",
    "cardGrid": "card-grid",
    "gallery": "gallery",
    "testimonial": "testimonial",
    "cta": "cta",
    "faq": "faq",
    "contact": "contact",
    "richText": "rich-text",
    "mediaFeature": "media-feature",
    "eventSchedule": "event-schedule",
    "teamGrid": "team-grid",
}


def slugify(value: str, fallback: str = "item") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or fallback


def lower_words(value: Any) -> str:
    return str(value or "").strip().lower()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n")


def infer_block_type(section: str) -> str | None:
    text = lower_words(section)
    if any(token in text for token in ("hero", "banner", "splash", "headline")):
        return "hero"
    if any(token in text for token in ("split feature", "split-feature", "split layout", "image and copy")):
        return "splitFeature"
    if any(token in text for token in ("team grid", "team", "staff", "people", "members")):
        return "teamGrid"
    if any(token in text for token in ("media feature", "video feature", "video or image", "video")):
        return "mediaFeature"
    if any(token in text for token in ("event schedule", "schedule", "agenda", "events")):
        return "eventSchedule"
    if any(token in text for token in ("testimonial", "quote", "review", "reviews")):
        return "testimonial"
    if any(token in text for token in ("faq", "frequently asked", "questions", "accordion")):
        return "faq"
    if any(token in text for token in ("contact form", "contact section", "email and phone", "phone", "address")):
        return "contact"
    if any(token in text for token in ("gallery", "photos", "images", "portfolio")):
        return "gallery"
    if any(token in text for token in ("card grid", "service cards", "cards grid")):
        return "cardGrid"
    if any(token in text for token in ("feature", "features", "benefit", "benefits", "cards", "card grid")):
        return "featureGrid"
    if any(token in text for token in ("cta", "call-to-action", "call to action", "book", "signup", "contact", "final")):
        return "cta"
    if any(token in text for token in ("text", "story", "about", "intro")):
        return "richText"
    return None


def section_id(block_type: str, page_id: str, occurrence: int = 1) -> str:
    base = f"{SECTION_ID_BASES.get(block_type, slugify(block_type))}-{page_id}"
    return base if occurrence == 1 else f"{base}-{occurrence}"


def page_id_for(page: dict[str, Any], index: int) -> str:
    slug = str(page.get("slug") or "").strip("/")
    if not slug:
        return "home" if index == 0 else f"page-{index + 1}"
    return slugify(slug)


def surface(
    *,
    field_ref: str,
    field_type: str,
    owner: str,
    source_default: Any,
    tina_field_path: str,
    content_path: str,
    render_intent: str,
    required_marker: str = "data-tina-field",
    surface_kind: str = "text",
    static_exemption_reason: str | None = None,
) -> dict[str, Any]:
    item = {
        "field_ref": field_ref,
        "field_type": field_type,
        "owner": owner,
        "source_default": source_default,
        "tina_field_path": tina_field_path,
        "content_path": content_path,
        "render_intent": render_intent,
        "required_marker": required_marker,
        "surface_kind": surface_kind,
    }
    if static_exemption_reason:
        item["static_exemption_reason"] = static_exemption_reason
    return item


def default_settings(brief: dict[str, Any], pages: list[dict[str, Any]]) -> dict[str, Any]:
    client = str(brief.get("client_name") or brief.get("project_name") or "Site")
    tagline = str(brief.get("tagline") or "")
    nav = []
    for page in pages:
        label = str(page.get("name") or page.get("title") or page.get("id") or "Page")
        href = str(page.get("slug") or "/")
        if href != "/" and not href.startswith("/"):
            href = f"/{href}"
        nav.append({"label": label, "href": href})
    if not nav:
        nav.append({"label": "Home", "href": "/"})
    return {
        "siteName": client,
        "tagline": tagline,
        "nav": nav,
        "footerLinks": [dict(item) for item in nav],
        "socialLinks": [],
        "contactEmail": "",
        "copyrightText": f"© {client}",
        "seo": {
            "title": client,
            "description": tagline or f"{client} website",
        },
    }


def block_fields(block_type: str, section_text: str) -> list[dict[str, Any]]:
    if block_type == "hero":
        return [
            {"name": "headline", "field_type": "string", "source_default": "Welcome"},
            {"name": "deck", "field_type": "text", "source_default": section_text},
            {"name": "ctaLabel", "field_type": "string", "source_default": "Learn more"},
            {"name": "backgroundImage", "field_type": "image", "source_default": "/images/hero-background.webp"},
        ]
    if block_type == "splitFeature":
        return [
            {"name": "eyebrow", "field_type": "string", "source_default": "Featured"},
            {"name": "headline", "field_type": "string", "source_default": "A focused feature"},
            {"name": "body", "field_type": "text", "source_default": section_text},
            {"name": "image", "field_type": "image", "source_default": "/images/split-feature.webp"},
            {"name": "imageAlt", "field_type": "string", "source_default": "Feature image"},
        ]
    if block_type == "featureGrid":
        return [
            {"name": "headline", "field_type": "string", "source_default": "Highlights"},
            {
                "name": "items",
                "field_type": "object-list",
                "source_default": [
                    {"title": "Feature one", "description": "First editable feature card"},
                    {"title": "Feature two", "description": "Second editable feature card"},
                    {"title": "Feature three", "description": "Third editable feature card"},
                ],
                "item_fields": [
                    {"name": "title", "field_type": "string", "source_default": "Feature"},
                    {"name": "description", "field_type": "text", "source_default": "Description"},
                ],
            },
        ]
    if block_type == "cardGrid":
        return [
            {"name": "headline", "field_type": "string", "source_default": "Services"},
            {
                "name": "cards",
                "field_type": "object-list",
                "source_default": [
                    {"title": "Card one", "description": "First editable card"},
                    {"title": "Card two", "description": "Second editable card"},
                    {"title": "Card three", "description": "Third editable card"},
                ],
                "item_fields": [
                    {"name": "title", "field_type": "string", "source_default": "Card"},
                    {"name": "description", "field_type": "text", "source_default": "Description"},
                ],
            },
        ]
    if block_type == "gallery":
        return [
            {"name": "headline", "field_type": "string", "source_default": "Gallery"},
            {
                "name": "items",
                "field_type": "object-list",
                "source_default": [
                    {"image": "/images/gallery-1.webp", "alt": "Gallery image", "caption": "Editable gallery image"},
                    {"image": "/images/gallery-2.webp", "alt": "Gallery image", "caption": "Editable gallery image"},
                    {"image": "/images/gallery-3.webp", "alt": "Gallery image", "caption": "Editable gallery image"},
                ],
                "item_fields": [
                    {"name": "image", "field_type": "image", "source_default": "/images/gallery-1.webp"},
                    {"name": "alt", "field_type": "string", "source_default": "Gallery image"},
                    {"name": "caption", "field_type": "string", "source_default": "Caption"},
                ],
            },
        ]
    if block_type == "testimonial":
        return [
            {"name": "headline", "field_type": "string", "source_default": "What people say"},
            {
                "name": "quotes",
                "field_type": "object-list",
                "source_default": [
                    {"quote": "A memorable experience.", "author": "Customer", "role": "Client"},
                ],
                "item_fields": [
                    {"name": "quote", "field_type": "text", "source_default": "Quote"},
                    {"name": "author", "field_type": "string", "source_default": "Author"},
                    {"name": "role", "field_type": "string", "source_default": "Role"},
                    {"name": "image", "field_type": "image", "source_default": "/images/testimonial.webp"},
                ],
            },
        ]
    if block_type == "cta":
        return [
            {"name": "headline", "field_type": "string", "source_default": "Ready to start?"},
            {"name": "body", "field_type": "text", "source_default": section_text},
            {"name": "buttonLabel", "field_type": "string", "source_default": "Book now"},
            {"name": "buttonHref", "field_type": "url", "source_default": "/contact"},
        ]
    if block_type == "faq":
        return [
            {"name": "headline", "field_type": "string", "source_default": "Frequently asked questions"},
            {
                "name": "items",
                "field_type": "object-list",
                "source_default": [
                    {"question": "What should I know?", "answer": "This answer is editable."},
                ],
                "item_fields": [
                    {"name": "question", "field_type": "string", "source_default": "Question"},
                    {"name": "answer", "field_type": "text", "source_default": "Answer"},
                ],
            },
        ]
    if block_type == "contact":
        return [
            {"name": "headline", "field_type": "string", "source_default": "Contact us"},
            {"name": "body", "field_type": "text", "source_default": section_text},
            {"name": "email", "field_type": "string", "source_default": "hello@example.com"},
            {"name": "phone", "field_type": "string", "source_default": "+1 555 0100"},
            {"name": "buttonLabel", "field_type": "string", "source_default": "Send message"},
        ]
    if block_type == "mediaFeature":
        return [
            {"name": "headline", "field_type": "string", "source_default": "Media feature"},
            {"name": "body", "field_type": "text", "source_default": section_text},
            {"name": "image", "field_type": "image", "source_default": "/images/media-feature.webp"},
            {"name": "video", "field_type": "video", "source_default": "/videos/media-feature.mp4"},
        ]
    if block_type == "eventSchedule":
        return [
            {"name": "headline", "field_type": "string", "source_default": "Schedule"},
            {
                "name": "events",
                "field_type": "object-list",
                "source_default": [
                    {"time": "9:00", "title": "Opening", "location": "Main room", "description": "Editable agenda item"},
                ],
                "item_fields": [
                    {"name": "time", "field_type": "string", "source_default": "Time"},
                    {"name": "title", "field_type": "string", "source_default": "Event"},
                    {"name": "location", "field_type": "string", "source_default": "Location"},
                    {"name": "description", "field_type": "text", "source_default": "Description"},
                ],
            },
        ]
    if block_type == "teamGrid":
        return [
            {"name": "headline", "field_type": "string", "source_default": "Meet the team"},
            {
                "name": "members",
                "field_type": "object-list",
                "source_default": [
                    {"name": "Team member", "role": "Role", "bio": "Editable biography", "image": "/images/team-member.webp"},
                ],
                "item_fields": [
                    {"name": "name", "field_type": "string", "source_default": "Name"},
                    {"name": "role", "field_type": "string", "source_default": "Role"},
                    {"name": "bio", "field_type": "text", "source_default": "Bio"},
                    {"name": "image", "field_type": "image", "source_default": "/images/team-member.webp"},
                ],
            },
        ]
    return [
        {"name": "headline", "field_type": "string", "source_default": "Section"},
        {"name": "body", "field_type": "rich-text", "source_default": section_text},
    ]


def make_block_surfaces(page_id: str, block_id: str, block_type: str, fields: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    surfaces: list[dict[str, Any]] = []
    media_fields: list[dict[str, Any]] = []
    for field in fields:
        name = field["name"]
        field_ref = f"pages.{page_id}.sections.{block_id}.{name}"
        field_type = field["field_type"]
        surface_kind = "background_image" if name.lower().endswith("image") and block_type == "hero" else "media" if field_type in {"image", "video", "file"} else "text"
        if field_type == "object-list":
            surface_kind = "repeated_object"
        item = surface(
            field_ref=field_ref,
            field_type=field_type,
            owner="block",
            source_default=field.get("source_default"),
            tina_field_path=f"sections.{block_id}.{name}",
            content_path=f"src/content/pages/{page_id}.json.sections.{block_id}.{name}",
            render_intent=f"{block_type} {name}",
            required_marker="data-tina-field",
            surface_kind=surface_kind,
        )
        surfaces.append(item)
        if field_type in {"image", "video", "file"} or surface_kind == "background_image":
            media_fields.append(dict(item))
        if field_type == "object-list":
            for item_field in field.get("item_fields", []):
                if item_field.get("field_type") in {"image", "video", "file"}:
                    child = surface(
                        field_ref=f"{field_ref}[].{item_field['name']}",
                        field_type=item_field["field_type"],
                        owner="block",
                        source_default=item_field.get("source_default"),
                        tina_field_path=f"sections.{block_id}.{name}[].{item_field['name']}",
                        content_path=f"src/content/pages/{page_id}.json.sections.{block_id}.{name}[].{item_field['name']}",
                        render_intent=f"{block_type} repeated {item_field['name']}",
                        required_marker="data-tina-field",
                        surface_kind="media",
                    )
                    media_fields.append(child)
    return surfaces, media_fields


def generate_blueprint(brief: dict[str, Any]) -> dict[str, Any]:
    content_structure = brief.get("content_structure") if isinstance(brief.get("content_structure"), dict) else {}
    raw_pages = content_structure.get("pages") if isinstance(content_structure, dict) else None
    if not isinstance(raw_pages, list) or not raw_pages:
        raise ValueError("STATUS:TINA_BLUEPRINT_MISSING_FIELD field=content_structure.pages")

    settings = default_settings(brief, [page for page in raw_pages if isinstance(page, dict)])
    pages: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []
    media_fields: list[dict[str, Any]] = []
    editable_surfaces: list[dict[str, Any]] = [
        surface(
            field_ref="settings.siteName",
            field_type="string",
            owner="settings",
            source_default=settings["siteName"],
            tina_field_path="siteName",
            content_path="src/content/settings/site.json.siteName",
            render_intent="site header brand text",
            surface_kind="text",
        ),
        surface(
            field_ref="settings.copyrightText",
            field_type="string",
            owner="settings",
            source_default=settings["copyrightText"],
            tina_field_path="copyrightText",
            content_path="src/content/settings/site.json.copyrightText",
            render_intent="footer copyright text",
            surface_kind="text",
        ),
    ]
    if settings["tagline"]:
        editable_surfaces.append(surface(
            field_ref="settings.tagline",
            field_type="string",
            owner="settings",
            source_default=settings["tagline"],
            tina_field_path="tagline",
            content_path="src/content/settings/site.json.tagline",
            render_intent="site tagline text",
            surface_kind="text",
        ))
    for idx, nav_item in enumerate(settings["nav"]):
        editable_surfaces.append(surface(
            field_ref=f"settings.nav[{idx}].label",
            field_type="string",
            owner="settings",
            source_default=nav_item["label"],
            tina_field_path=f"nav[{idx}].label",
            content_path=f"src/content/settings/site.json.nav[{idx}].label",
            render_intent="header navigation label",
            surface_kind="text",
        ))
    for idx, footer_item in enumerate(settings["footerLinks"]):
        editable_surfaces.append(surface(
            field_ref=f"settings.footerLinks[{idx}].label",
            field_type="string",
            owner="settings",
            source_default=footer_item["label"],
            tina_field_path=f"footerLinks[{idx}].label",
            content_path=f"src/content/settings/site.json.footerLinks[{idx}].label",
            render_intent="footer navigation label",
            surface_kind="text",
        ))

    for page_index, raw_page in enumerate(raw_pages):
        if not isinstance(raw_page, dict):
            raise ValueError(f"STATUS:TINA_BLUEPRINT_MISSING_FIELD field=content_structure.pages[{page_index}]")
        page_id = page_id_for(raw_page, page_index)
        raw_sections = raw_page.get("sections")
        if not isinstance(raw_sections, list) or not raw_sections:
            raise ValueError(f"STATUS:TINA_BLUEPRINT_MISSING_FIELD field=content_structure.pages[{page_index}].sections")

        sections: list[dict[str, Any]] = []
        section_counts: dict[str, int] = {}
        emitted_block_types = {block["type"] for block in blocks}
        for raw_section in raw_sections:
            section_text = str(raw_section)
            block_type = infer_block_type(section_text)
            if block_type is None:
                snippet = section_text[:120].replace("\n", " ")
                raise ValueError(f"STATUS:TINA_BLUEPRINT_UNSUPPORTED_BLOCK section={json.dumps(snippet)}")
            section_counts[block_type] = section_counts.get(block_type, 0) + 1
            block_id = section_id(block_type, page_id, section_counts[block_type])
            fields = block_fields(block_type, section_text)
            sections.append({"id": block_id, "type": block_type, "fields": fields})
            if block_type not in emitted_block_types:
                blocks.append({
                    "type": block_type,
                    "label": re.sub(r"(?<!^)([A-Z])", r" \1", block_type).title(),
                    "renderer": SUPPORTED_BLOCKS[block_type],
                    "fields": [field["name"] for field in fields],
                })
                emitted_block_types.add(block_type)
            block_surfaces, block_media = make_block_surfaces(page_id, block_id, block_type, fields)
            editable_surfaces.extend(block_surfaces)
            media_fields.extend(block_media)

        title = str(raw_page.get("name") or raw_page.get("title") or page_id.title())
        pages.append({
            "id": page_id,
            "slug": raw_page.get("slug") or ("/" if page_id == "home" else f"/{page_id}"),
            "title": title,
            "seo": {"title": title, "description": str(raw_page.get("purpose") or settings["seo"]["description"])},
            "sections": sections,
        })

    collections = []
    content_model = brief.get("content_model")
    if isinstance(content_model, dict) and isinstance(content_model.get("collections"), list):
        for collection in content_model["collections"]:
            if not isinstance(collection, dict) or not collection.get("name"):
                continue
            collections.append({
                "name": collection.get("name"),
                "path": collection.get("path") or f"src/content/{collection.get('name')}",
                "fields": collection.get("fields") if isinstance(collection.get("fields"), list) else [],
            })

    return {
        "schema_version": SCHEMA_VERSION,
        "project_name": brief.get("project_name") or slugify(str(brief.get("client_name") or "site")),
        "settings": settings,
        "pages": pages,
        "collections": collections,
        "blocks": blocks,
        "media_fields": media_fields,
        "editable_surface_map": editable_surfaces,
    }


def minimal_validate(blueprint: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in ("schema_version", "project_name", "settings", "pages", "collections", "blocks", "media_fields", "editable_surface_map"):
        if key not in blueprint:
            errors.append(f"missing {key}")
    settings = blueprint.get("settings")
    if isinstance(settings, dict):
        for key in ("siteName", "nav", "footerLinks", "copyrightText"):
            if key not in settings:
                errors.append(f"settings missing {key}")
    for page_index, page in enumerate(blueprint.get("pages", []) if isinstance(blueprint.get("pages"), list) else []):
        if not isinstance(page, dict):
            continue
        seen_section_ids: set[str] = set()
        for section_index, section in enumerate(page.get("sections", []) if isinstance(page.get("sections"), list) else []):
            if not isinstance(section, dict):
                continue
            section_key = str(section.get("id") or "")
            if section_key in seen_section_ids:
                errors.append(f"pages[{page_index}].sections[{section_index}] duplicate id {section_key}")
            seen_section_ids.add(section_key)
    for unique_key in ("field_ref", "tina_field_path", "content_path"):
        seen_values: set[str] = set()
        for idx, surface_item in enumerate(blueprint.get("editable_surface_map", []) if isinstance(blueprint.get("editable_surface_map"), list) else []):
            if not isinstance(surface_item, dict):
                continue
            value = str(surface_item.get(unique_key) or "")
            if not value:
                continue
            if value in seen_values:
                errors.append(f"editable_surface_map[{idx}] duplicate {unique_key} {value}")
            seen_values.add(value)
    for idx, surface_item in enumerate(blueprint.get("editable_surface_map", []) if isinstance(blueprint.get("editable_surface_map"), list) else []):
        if isinstance(surface_item, dict) and surface_item.get("required_marker") == "static-exempt" and not surface_item.get("static_exemption_reason"):
            errors.append(f"editable_surface_map[{idx}] missing static_exemption_reason")
    return errors


def validate_blueprint(pipeline_dir: Path) -> int:
    path = pipeline_dir / "01-tina-blueprint.json"
    if not path.exists():
        print("STATUS:TINA_BLUEPRINT_MISSING_FIELD field=01-tina-blueprint.json")
        return 1
    try:
        blueprint = load_json(path)
    except Exception as exc:
        print(f"STATUS:TINA_BLUEPRINT_FAILED reason=invalid_json detail={exc}")
        return 1
    if not isinstance(blueprint, dict):
        print("STATUS:TINA_BLUEPRINT_FAILED reason=root_not_object")
        return 1
    errors = minimal_validate(blueprint)
    if errors:
        print("STATUS:TINA_BLUEPRINT_FAILED reason=contract_errors")
        for error in errors:
            print(error)
        return 1
    print(f"STATUS:TINA_BLUEPRINT_OK fields={len(blueprint.get('editable_surface_map', []))} media={len(blueprint.get('media_fields', []))}")
    return 0


def summarize_blueprint(pipeline_dir: Path) -> int:
    path = pipeline_dir / "01-tina-blueprint.json"
    if not path.exists():
        print("STATUS:TINA_BLUEPRINT_MISSING_FIELD field=01-tina-blueprint.json")
        return 1
    blueprint = load_json(path)
    print(json.dumps({
        "schema_version": blueprint.get("schema_version"),
        "project_name": blueprint.get("project_name"),
        "pages": len(blueprint.get("pages", [])),
        "blocks": [block.get("type") for block in blueprint.get("blocks", []) if isinstance(block, dict)],
        "editable_fields": len(blueprint.get("editable_surface_map", [])),
        "media_fields": len(blueprint.get("media_fields", [])),
    }, indent=2))
    print("STATUS:TINA_BLUEPRINT_OK")
    return 0


def generate(pipeline_dir: Path) -> int:
    brief_path = pipeline_dir / "01-creative-brief.json"
    if not brief_path.exists():
        print("STATUS:TINA_BLUEPRINT_MISSING_FIELD field=01-creative-brief.json")
        return 1
    try:
        brief = load_json(brief_path)
        if not isinstance(brief, dict):
            raise ValueError("creative brief root must be object")
        if brief.get("_requires_human_confirmation") is True:
            raise ValueError("STATUS:TINA_BLUEPRINT_FAILED reason=brief_flagged_for_human_confirmation")
        blueprint = generate_blueprint(brief)
    except ValueError as exc:
        message = str(exc)
        if message.startswith("STATUS:"):
            print(message)
        else:
            print(f"STATUS:TINA_BLUEPRINT_FAILED reason={message}")
        return 1
    except Exception as exc:
        print(f"STATUS:TINA_BLUEPRINT_FAILED reason=exception detail={exc}")
        return 1

    write_json(pipeline_dir / "01-tina-blueprint.json", blueprint)
    errors = minimal_validate(blueprint)
    if errors:
        print("STATUS:TINA_BLUEPRINT_FAILED reason=generated_invalid")
        for error in errors:
            print(error)
        return 1
    print(f"STATUS:TINA_BLUEPRINT_OK fields={len(blueprint['editable_surface_map'])} media={len(blueprint['media_fields'])}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate and validate the astro-static Tina blueprint contract.")
    parser.add_argument("mode", choices=["generate", "validate", "summarize"])
    parser.add_argument("--pipeline-dir", type=Path, default=Path("pipeline"))
    args = parser.parse_args(argv)
    pipeline_dir = args.pipeline_dir.expanduser().resolve()
    if not pipeline_dir.exists():
        print(f"STATUS:TINA_BLUEPRINT_FAILED reason=no_pipeline_dir path={pipeline_dir}")
        return 1
    if args.mode == "generate":
        return generate(pipeline_dir)
    if args.mode == "validate":
        return validate_blueprint(pipeline_dir)
    return summarize_blueprint(pipeline_dir)


if __name__ == "__main__":
    raise SystemExit(main())
