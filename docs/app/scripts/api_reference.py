"""Pure introspection for generated XYG API documentation. No UI framework."""

import inspect
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from typing import Any

import xyg
from xyg.components import _POLAR_INERT_AXIS_KEYWORDS

COMPONENT_API_METADATA_KEY = "components"
API_REFERENCE_HEADING = "API Reference"
_COMPONENT_API_NAMESPACES = {"xyg": xyg}
CHART_FACTORY_GROUPS = (
    ("Line and Area", (xyg.line_chart, xyg.area_chart, xyg.step_chart, xyg.stairs_chart)),
    ("Scatter", (xyg.scatter_chart,)),
    (
        "Polar",
        (xyg.polar_chart, xyg.radar_chart, xyg.polar_bar_chart, xyg.pie_chart, xyg.wind_rose),
    ),
    ("Bar and Column", (xyg.bar_chart, xyg.column_chart)),
    ("Distributions", (xyg.histogram_chart, xyg.ecdf_chart, xyg.box_chart, xyg.violin_chart)),
    ("Density and Grids", (xyg.hexbin_chart, xyg.heatmap_chart, xyg.contour_chart)),
    ("Uncertainty", (xyg.error_band_chart, xyg.errorbar_chart)),
    (
        "Specialized",
        (
            xyg.stem_chart,
            xyg.segments_chart,
            xyg.sankey_chart,
            xyg.graph_chart,
            xyg.triangle_mesh_chart,
        ),
    ),
    ("Annotations", (xyg.chart,)),
    ("Facets and Layers", (xyg.chart, xyg.facet_chart)),
)
_CHART_FACTORY_COMPONENTS = frozenset(
    (factory for _group_name, factories in CHART_FACTORY_GROUPS for factory in factories)
)
_FORWARDED_AXIS_COMPONENTS = {xyg.theta_axis: xyg.x_axis, xyg.r_axis: xyg.y_axis}
_REFUSED_POLAR_AXIS_PARAMETERS = {
    xyg.theta_axis: frozenset({*_POLAR_INERT_AXIS_KEYWORDS, "reverse"}),
    xyg.r_axis: frozenset(_POLAR_INERT_AXIS_KEYWORDS),
}
MARKS = (
    xyg.line,
    xyg.scatter,
    xyg.area,
    xyg.bar,
    xyg.column,
    xyg.histogram,
    xyg.box,
    xyg.violin,
    xyg.ecdf,
    xyg.heatmap,
    xyg.hexbin,
    xyg.contour,
    xyg.errorbar,
    xyg.error_band,
    xyg.step,
    xyg.stairs,
    xyg.stem,
    xyg.segments,
    xyg.ribbon,
    xyg.sankey,
    xyg.triangle_mesh,
    xyg.graph,
)
AXES_AND_ANNOTATIONS = (
    xyg.x_axis,
    xyg.y_axis,
    xyg.theta_axis,
    xyg.r_axis,
    xyg.vline,
    xyg.hline,
    xyg.x_band,
    xyg.y_band,
    xyg.threshold,
    xyg.threshold_zone,
    xyg.text,
    xyg.label,
    xyg.marker,
    xyg.arrow,
    xyg.callout,
)
CHROME_AND_BEHAVIOR = (
    xyg.legend,
    xyg.tooltip,
    xyg.colorbar,
    xyg.modebar,
    xyg.theme,
    xyg.interaction_config,
    xyg.animation,
    xyg.spring,
)


@dataclass(frozen=True, slots=True)
class ComponentApiParameter:
    """One generated callable parameter shared by HTML and Markdown output."""

    name: str
    type_name: str
    description: str


@dataclass(frozen=True, slots=True)
class ComponentApiReference:
    """Inspected public callable shared by all documentation renderers."""

    display_name: str
    summary: str
    parameters: tuple[ComponentApiParameter, ...]
    component: Callable[..., Any]


def _format_annotation(annotation: Any) -> str:
    """Format an inspected annotation for an API table."""
    if annotation is inspect.Parameter.empty:
        return "Any"
    if isinstance(annotation, str):
        return annotation.replace("typing.", "")
    return getattr(annotation, "__name__", str(annotation).replace("typing.", ""))


def _format_default(default: Any) -> str | None:
    """Format a stable, compact default value for generated documentation."""
    if callable(default):
        return getattr(default, "__name__", type(default).__name__)
    value = repr(default)
    if " object at 0x" in value:
        return None
    return value if len(value) <= 80 else f"{value[:77]}..."


def _parameter_descriptions(docstring: str) -> dict[str, str]:
    """Extract Google-style argument descriptions from a callable docstring."""
    descriptions: dict[str, str] = {}
    current: str | None = None
    in_args = False
    for line in docstring.splitlines():
        stripped = line.strip()
        if stripped in {"Args:", "Arguments:", "Parameters:"}:
            in_args = True
            current = None
            continue
        if not in_args:
            continue
        if stripped and (not line.startswith((" ", "\t"))):
            break
        if not stripped:
            continue
        if ":" in stripped and (not stripped.startswith(":")):
            name, description = stripped.split(":", 1)
            name = name.split("(", 1)[0].strip().lstrip("*")
            if name.isidentifier():
                current = name
                descriptions[current] = description.strip()
                continue
        if current is not None:
            descriptions[current] = f"{descriptions[current]} {stripped}".strip()
    return descriptions


def _summary(docstring: str) -> str:
    """Return the opening paragraph of a callable docstring."""
    return docstring.strip().split("\n\n", 1)[0].replace("\n", " ")


def _parameter_description(parameter: inspect.Parameter, descriptions: Mapping[str, str]) -> str:
    """Return explicit or generated prose for one callable parameter."""
    if description := descriptions.get(parameter.name):
        return description
    is_required = parameter.default is inspect.Parameter.empty
    default = None if is_required else _format_default(parameter.default)
    if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
        return "Additional positional arguments."
    if parameter.kind is inspect.Parameter.VAR_KEYWORD:
        return "Additional keyword arguments."
    if is_required:
        return "Required."
    if default is None:
        return "Optional."
    return f"Defaults to {default}."


def _documented_parameters(
    component: Callable[..., Any], descriptions: Mapping[str, str]
) -> tuple[tuple[inspect.Parameter, Mapping[str, str]], ...]:
    """Expand forwarded chart and polar-axis keyword arguments."""
    parameters = tuple(inspect.signature(component).parameters.values())
    if forwarded_axis := _FORWARDED_AXIS_COMPONENTS.get(component):
        forwarded_descriptions = _parameter_descriptions(inspect.getdoc(forwarded_axis) or "")
        merged_descriptions = {**forwarded_descriptions, **descriptions}
        existing_names = {
            parameter.name
            for parameter in parameters
            if parameter.kind is not inspect.Parameter.VAR_KEYWORD
        }
        forwarded_parameters = tuple(
            parameter
            for parameter in inspect.signature(forwarded_axis).parameters.values()
            if parameter.name not in existing_names
            and parameter.name not in _REFUSED_POLAR_AXIS_PARAMETERS[component]
            and (parameter.kind is not inspect.Parameter.VAR_KEYWORD)
        )
        documented: list[tuple[inspect.Parameter, Mapping[str, str]]] = []
        for parameter in parameters:
            if parameter.kind is inspect.Parameter.VAR_KEYWORD:
                documented.extend(
                    (forwarded_parameter, merged_descriptions)
                    for forwarded_parameter in forwarded_parameters
                )
                continue
            documented.append((parameter, merged_descriptions))
        return tuple(documented)
    if component not in _CHART_FACTORY_COMPONENTS:
        return tuple((parameter, descriptions) for parameter in parameters)
    shared_descriptions = _parameter_descriptions(inspect.getdoc(xyg.Chart.__init__) or "")
    merged_descriptions = {**shared_descriptions, **descriptions}
    existing_names = {
        parameter.name
        for parameter in parameters
        if parameter.kind is not inspect.Parameter.VAR_KEYWORD
    }
    shared_parameters = tuple(
        parameter
        for parameter in inspect.signature(xyg.Chart).parameters.values()
        if parameter.name not in {"kind", "children", *existing_names}
    )
    documented: list[tuple[inspect.Parameter, Mapping[str, str]]] = []
    for parameter in parameters:
        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
            documented.extend(
                (shared_parameter, merged_descriptions) for shared_parameter in shared_parameters
            )
            continue
        documented.append((parameter, merged_descriptions))
    return tuple(documented)


def component_api_paths(metadata: Mapping[str, Any]) -> tuple[str, ...]:
    """Read and validate the shape of a page's component API frontmatter.

    Args:
        metadata: Parsed Markdown frontmatter mapping.

    Returns:
        Declared component paths, or an empty tuple.

    Raises:
        TypeError: If ``components`` is not a list of strings.
        ValueError: If a path is duplicated or outside a supported namespace.
    """
    value = metadata.get(COMPONENT_API_METADATA_KEY)
    if value is None:
        return ()
    if not isinstance(value, list):
        msg = "Documentation frontmatter 'components' must be a list"
        raise TypeError(msg)
    paths: list[str] = []
    seen: set[str] = set()
    for component_path in value:
        if not isinstance(component_path, str):
            msg = "Documentation component paths must be strings"
            raise TypeError(msg)
        if component_path in seen:
            msg = f"Duplicate documentation component path: {component_path!r}"
            raise ValueError(msg)
        seen.add(component_path)
        namespace, separator, public_name = component_path.partition(".")
        if (
            namespace not in _COMPONENT_API_NAMESPACES
            or not separator
            or (not public_name)
            or ("." in public_name)
        ):
            msg = f"Invalid documentation component path: {component_path!r}"
            raise ValueError(msg)
        paths.append(component_path)
    return tuple(paths)


@cache
def _component_api_references(
    component_paths: tuple[str, ...],
) -> tuple[ComponentApiReference, ...]:
    """Resolve and inspect a validated tuple once for every docs compilation."""
    references: list[ComponentApiReference] = []
    for component_path in component_paths:
        namespace, _, public_name = component_path.partition(".")
        module = _COMPONENT_API_NAMESPACES[namespace]
        if public_name not in getattr(module, "__all__", ()):
            msg = f"Non-public documentation component: {component_path!r}"
            raise ValueError(msg)
        component = getattr(module, public_name, None)
        if not callable(component):
            msg = f"Unknown documentation component: {component_path!r}"
            raise ValueError(msg)
        docstring = inspect.getdoc(component) or ""
        descriptions = _parameter_descriptions(docstring)
        parameters: list[ComponentApiParameter] = []
        for parameter, parameter_descriptions in _documented_parameters(component, descriptions):
            prefix = (
                "**"
                if parameter.kind is inspect.Parameter.VAR_KEYWORD
                else "*"
                if parameter.kind is inspect.Parameter.VAR_POSITIONAL
                else ""
            )
            parameters.append(
                ComponentApiParameter(
                    name=f"{prefix}{parameter.name}",
                    type_name=_format_annotation(parameter.annotation),
                    description=_parameter_description(parameter, parameter_descriptions),
                )
            )
        references.append(
            ComponentApiReference(
                display_name=component_path,
                summary=_summary(docstring) if docstring else "",
                parameters=tuple(parameters),
                component=component,
            )
        )
    return tuple(references)


def component_api_references(component_paths: Sequence[str]) -> tuple[ComponentApiReference, ...]:
    """Resolve public callables into their shared documentation metadata.

    Args:
        component_paths: Validated public component paths.

    Returns:
        Cached callable metadata in declaration order.

    Raises:
        ValueError: If a component is not exported or callable.
    """
    return _component_api_references(tuple(component_paths))


def component_api_callables(component_paths: Sequence[str]) -> tuple[Callable[..., Any], ...]:
    """Return resolved public callables from the cached metadata model."""
    return tuple(reference.component for reference in component_api_references(component_paths))


def _markdown_cell(value: str) -> str:
    """Escape generated text for one GitHub-Flavored Markdown table cell."""
    return " ".join(value.split()).replace("|", "\\|")


def component_api_markdown(references: Sequence[ComponentApiReference]) -> str:
    """Serialize the same API metadata used by every documentation output."""
    if not references:
        return ""
    lines = [f"## {API_REFERENCE_HEADING}", ""]
    for reference in references:
        lines.extend((f"### {reference.display_name}", ""))
        if reference.summary:
            lines.extend((reference.summary, ""))
        lines.extend(("#### Props", "", "| Prop | Type | Description |", "| --- | --- | --- |"))
        lines.extend(
            f"| {_markdown_cell(f'`{parameter.name}`')} | {_markdown_cell(f'`{parameter.type_name}`')} | {_markdown_cell(parameter.description)} |"
            for parameter in reference.parameters
        )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


_FAQ_HEADING = re.compile("^## FAQ\\s*$", re.MULTILINE)


def split_faq_section(content: str) -> tuple[str, str | None]:
    """Split authored Markdown at its FAQ heading.

    The generated API Reference is inserted between the body and the FAQ, so
    the FAQ stays the final section on every surface (HTML page, per-page
    Markdown, and llms-full.txt).
    """
    match = _FAQ_HEADING.search(content)
    if match is None:
        return (content, None)
    return (content[: match.start()], content[match.start() :])


def append_component_api_markdown(content: str, metadata: Mapping[str, Any]) -> str:
    """Insert a generated Markdown API section when frontmatter declares one.

    The section lands after the authored body but before any FAQ, matching the
    rendered page order.
    """
    paths = component_api_paths(metadata)
    if not paths:
        return content
    section = component_api_markdown(component_api_references(paths))
    body, faq = split_faq_section(content)
    if faq is None:
        return f"{content.rstrip()}\n\n{section}"
    return f"{body.rstrip()}\n\n{section.rstrip()}\n\n{faq.strip()}\n"


def callable_markdown(component: Callable[..., Any], display_name: str) -> str:
    """Render a constructor or public callable from its actual signature."""
    descriptions = _parameter_descriptions(inspect.getdoc(component) or "")
    parameters = tuple(
        ComponentApiParameter(
            name=parameter.name,
            type_name=_format_annotation(parameter.annotation),
            description=_parameter_description(parameter, descriptions),
        )
        for parameter in inspect.signature(component).parameters.values()
        if parameter.name not in {"self", "kind"}
    )
    return component_api_markdown(
        (
            ComponentApiReference(
                display_name, _summary(inspect.getdoc(component) or ""), parameters, component
            ),
        )
    ).removeprefix("## API Reference\n\n")


def reference_group_markdown(name: str) -> str:
    """Resolve legacy reference placeholders into framework-free Markdown."""
    if name == "chart_containers_api":
        return callable_markdown(xyg.Chart.__init__, "Shared chart props")
    if name == "chart_factories_api":
        return "\n\n".join(
            f"### {title}\n\n"
            + component_api_markdown(
                component_api_references(tuple(f"xyg.{factory.__name__}" for factory in factories))
            )
            .removeprefix("## API Reference\n\n")
            .replace("### xyg.", "#### xyg.")
            .replace("#### Props", "##### Props")
            for title, factories in CHART_FACTORY_GROUPS
        )
    groups = {
        "marks_api": MARKS,
        "axes_and_annotations_api": AXES_AND_ANNOTATIONS,
        "chrome_and_behavior_api": CHROME_AND_BEHAVIOR,
    }
    if name not in groups:
        raise ValueError(f"Unknown API reference placeholder: {name}")
    return component_api_markdown(
        component_api_references(tuple(f"xyg.{component.__name__}" for component in groups[name]))
    ).removeprefix("## API Reference\n\n")
