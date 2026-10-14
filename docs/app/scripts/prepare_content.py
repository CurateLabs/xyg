"""Prepare Starlight pages and agent Markdown from canonical XYG sources.

Native previews are produced separately by generate_examples.py. This step
never executes authored example code and never imports an application framework.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import yaml
from api_reference import (
    append_component_api_markdown,
    component_api_paths,
    reference_group_markdown,
)

APP = Path(__file__).resolve().parents[1]
DOCS = APP.parent

BASE = "/docs/xy"
FENCES = re.compile(
    r"^(?P<fence>~{3,}|`{3,})(?P<info>[^\n]*)\n(?P<code>.*?)^(?P=fence)[ \t]*$",
    re.MULTILINE | re.DOTALL,
)
EXCLUDED = {
    "integrations/reflex.md",
    "styling/component-variations.md",
    "styling/mark-styles.md",
    "styling/playground.md",
    "styling/recipes.md",
}
REDIRECTED_GUIDES = {
    "integrations/reflex": "integrations/graphforge",
    "styling/component-variations": "styling/customize",
    "styling/mark-styles": "styling/customize",
    "styling/playground": "styling/themes-and-tokens",
    "styling/recipes": "styling/examples",
}
BLOCKED_CODE = re.compile(
    r"(?<![\w-])(?:reflex|reflex_xy|reflex_components_internal|xy_docs|rx|ui)(?![\w-])"
)
PREVIEW_NOTE = (
    "This preview paints a generated chart snapshot. Pan, zoom, and hover follow "
    "the chart's settings in the browser; Python callbacks and application "
    "controls require their live host."
)


def read_page(source: str) -> tuple[dict[str, Any], str]:
    """Separate YAML metadata from one canonical Markdown page."""
    if source.startswith("---\n"):
        _, frontmatter, body = source.split("---", 2)
        metadata = yaml.safe_load(frontmatter) or {}
        if not isinstance(metadata, dict):
            raise ValueError("Documentation frontmatter must be a mapping")
    else:
        metadata, body = {}, source
    return metadata, re.sub(r"\A\s*# [^\n]+\n", "", body, count=1).lstrip()


def code_fence(language: str, code: str) -> str:
    """Emit a fence longer than any fence already present in the code."""
    runs = re.findall(r"`+", code)
    fence = "`" * max(3, max((len(run) + 1 for run in runs), default=3))
    return f"{fence}{language}\n{code.rstrip()}\n{fence}"


def preview_mount(preview: dict[str, Any]) -> str:
    """Mount one unchanged Rust-compiled panel payload."""
    return (
        '<div class="xyg-demo not-content" data-payload="'
        + html.escape(preview["src"], quote=True)
        + '" aria-label="'
        + html.escape(preview["title"], quote=True)
        + '">Loading chart…</div>'
    )


def previews_markdown(previews: list[dict[str, Any]]) -> str:
    """Keep consecutive SDK facet panels in their authored titled grid."""
    rendered = []
    cursor = 0
    while cursor < len(previews):
        preview = previews[cursor]
        facet = preview.get("facet")
        if facet is None:
            rendered.append(preview_mount(preview))
            cursor += 1
            continue
        count = facet["count"]
        panels = previews[cursor : cursor + count]
        if len(panels) != count or any(
            panel.get("facet", {}).get("group") != facet["group"]
            or panel["facet"]["panel"] != index
            for index, panel in enumerate(panels)
        ):
            raise ValueError("Incomplete or reordered generated facet group")
        title = html.escape(facet["title"] or "", quote=True)
        heading = f'<div class="xyg-facet-title">{title}</div>' if title else ""
        rendered.append(
            '<section class="xyg-facets not-content" data-facet-group="'
            + html.escape(facet["group"], quote=True)
            + f'" data-facet-cols="{facet["cols"]}" aria-label="{title or "XYG facets"}" '
            + f'style="--xyg-facet-cols:{facet["cols"]};--xyg-facet-gap:{facet["gap"]}px;'
            + f'--xyg-facet-height:{facet["height"]}px">'
            + heading
            + '<div class="xyg-facet-grid">'
            + "\n".join(preview_mount(panel) for panel in panels)
            + "</div></section>"
        )
        cursor += count
    return "\n\n".join(rendered)


def api_placeholder(code: str) -> str | None:
    """Recognize the closed set of legacy API rendering placeholders."""
    match = re.fullmatch(
        r"\s*(chart_factories_api|chart_containers_api|marks_api|axes_and_annotations_api|chrome_and_behavior_api)\(\)\s*",
        code,
    )
    return reference_group_markdown(match.group(1)) if match else None


def gallery_markdown(records: dict[str, list[dict[str, Any]]]) -> str:
    """Link chart families with actual generated first-paint previews."""
    cards = []
    for page in sorted(DOCS.joinpath("charts").glob("*.md")):
        relative = page.relative_to(DOCS).as_posix()
        metadata, _ = read_page(page.read_text())
        title = str(metadata.get("title", page.stem))
        route = f"{BASE}/charts/{page.stem}/"
        previews = [
            preview for record in records.get(relative, []) for preview in record["previews"]
        ]
        cards.append(f"### [{title}]({route})\n\n" + previews_markdown(previews[:1]))
    return "\n\n".join(cards)


def convert_body(
    body: str,
    page: str,
    records: dict[str, list[dict[str, Any]]],
) -> str:
    """Adapt executable fences and shared-docs directives to static Markdown."""
    indexed = {record["block"]: record for record in records.get(page, [])}
    block_index = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal block_index
        index = block_index
        block_index += 1
        info = match.group("info").strip().split()
        code = match.group("code")
        language = info[0] if info else ""
        if language == "md":
            nested = convert_body(code, page, {})
            if "alert" in info:
                kind = (
                    "caution"
                    if any(token in info for token in ("warning", "caution"))
                    else "tip"
                    if "tip" in info
                    else "note"
                )
                return f":::{kind}\n{nested.strip()}\n:::"
            return nested
        if index in indexed:
            if language != "python" or not any(token in info for token in ("demo", "demo-only")):
                raise ValueError(
                    f"{page}:{index}: stale example indices; regenerate native previews"
                )
            record = indexed[index]
            sanitized = record["code"]
            if BLOCKED_CODE.search(sanitized):
                raise ValueError(f"{page}:{index}: framework code escaped example sanitization")
            parts = [previews_markdown(record["previews"])]
            if record.get("note"):
                parts.append(str(record["note"]))
            elif record["previews"]:
                parts.append(PREVIEW_NOTE)
            if sanitized.strip() and "demo-only" not in info:
                parts.append(code_fence("python", sanitized))
            return "\n\n".join(part for part in parts if part)
        if language == "python" and "eval" in info:
            api = api_placeholder(code)
            if api is not None:
                return api
            if "chart_gallery_grid()" in code:
                return gallery_markdown(records)
            if "chart_examples_layout_marker()" in code:
                return ""
            if "chart_playground()" in code:
                return "Use `xyg.theme(palette=...)` to author a palette; a live palette editor is not included in this static documentation site."
            raise ValueError(f"{page}:{index}: unsupported executable placeholder")
        if language == "python" and BLOCKED_CODE.search(code):
            raise ValueError(
                f"{page}:{index}: public examples must use framework-free chart authoring"
            )
        return code_fence(language, code)

    transformed = FENCES.sub(replace, body)
    transformed = re.sub(
        r"<!-- xyg:api ([a-z_]+) -->",
        lambda match: reference_group_markdown(match.group(1)),
        transformed,
    )
    transformed = transformed.replace("<!-- xyg:chart-gallery -->", gallery_markdown(records))
    transformed = re.sub(
        r"\]\((?P<path>/docs/xy/[^#)\s]*|)(?P<fragment>#[^)\s]+)\)",
        lambda match: (
            "]("
            + match.group("path")
            + "#"
            + re.sub(r"[^\w-]", "", unquote(match.group("fragment")[1:]).lower())
            + ")"
        ),
        transformed,
    )
    for old, new in REDIRECTED_GUIDES.items():
        transformed = transformed.replace(f"{BASE}/{old}/", f"{BASE}/{new}/")
    transformed = transformed.replace(
        "Every preview is a code-native inline SVG, keeping this index quick and making\nthe artwork straightforward to restyle. Every linked family page includes a\nfull-size live demo.",
        "Previews paint generated native chart payloads with the same client as the\nfamily guides. Open a guide for its complete chart authoring code.",
    )
    if page == "styling/examples.md":
        transformed = re.sub(
            r"responsive preview includes.*?Each preview displays",
            "preview includes its chart authoring code. The site displays generated\nsnapshots rather than application controls or a reactive palette editor.\n\nEach preview displays",
            transformed,
            count=1,
            flags=re.DOTALL,
        )
        transformed = re.sub(
            r"## Palette playground\n.*?(?=## Build your own)", "", transformed, flags=re.DOTALL
        )
    return transformed.strip() + "\n"


def main() -> None:
    """Write one content projection for Starlight, Markdown, and agent files."""
    records = json.loads((APP / ".generated" / "examples.json").read_text())
    output = APP / "src" / "content" / "docs"
    public = APP / "public"
    output.mkdir(parents=True, exist_ok=True)
    for stale in output.rglob("*.md"):
        stale.unlink()
    pages = []
    full = [
        "# XYG documentation",
        "",
        "Generated from the same canonical sources as the public site.",
        "",
    ]
    for source in sorted(DOCS.rglob("*.md")):
        relative = source.relative_to(DOCS).as_posix()
        if relative.startswith("app/") or relative in EXCLUDED:
            continue
        metadata, body = read_page(source.read_text())
        title = str(metadata.get("title", source.stem.replace("-", " ").title()))
        metadata["title"] = title
        components = list(component_api_paths(metadata))
        body = append_component_api_markdown(convert_body(body, relative, records), metadata)
        if BLOCKED_CODE.search(body.replace("reflex_components", "adapter_components")):
            # Provenance URLs are allowed; framework code is not.
            for match in FENCES.finditer(body):
                if match.group("info").strip().startswith("python") and BLOCKED_CODE.search(
                    match.group("code").replace("reflex_components", "adapter_components")
                ):
                    raise ValueError(f"{relative}: exposed framework code in prepared page")
        metadata.pop("components", None)
        generated = (
            "---\n"
            + yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True).strip()
            + "\n---\n\n"
            + body
        )
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(generated)
        slug = relative.removesuffix(".md")
        if slug == "index":
            slug = ""
        elif slug.endswith("/index"):
            slug = slug.removesuffix("/index")
        route = f"{BASE}/{slug}/".replace("//", "/")
        markdown_route = f"{BASE}/{slug}.md" if slug else f"{BASE}/index.md"
        exported = f"# {title}\n\n" + body
        aliases = (
            [public / f"{slug}.md", public / slug / ".md", public / slug / "index.md"]
            if slug
            else [public / "index.md", public / ".md"]
        )
        for alias in aliases:
            alias.parent.mkdir(parents=True, exist_ok=True)
            alias.write_text(exported)
        previews = [
            preview for record in records.get(relative, []) for preview in record["previews"]
        ]
        pages.append(
            {
                "source": relative,
                "route": route,
                "markdown": markdown_route,
                "title": title,
                "components": components,
                "previews": previews,
            }
        )
        full.extend((f"<!-- Source: {route} -->", exported, ""))
    (APP / ".generated" / "content-manifest.json").write_text(
        json.dumps({"base": BASE, "pages": pages}, indent=2) + "\n"
    )
    (public / "llms.txt").write_text(
        "# XYG\n\nRust-powered graph visualization and charting for Python, Node, and browser WASM.\n\n"
        + "\n".join(f"- [{page['title']}]({page['markdown']})" for page in pages)
        + f"\n\n[Full documentation]({BASE}/llms-full.txt)\n"
    )
    (public / "llms-full.txt").write_text("\n".join(full))
    print(f"Prepared {len(pages)} Starlight pages and matching Markdown/agent exports.")


if __name__ == "__main__":
    main()
