"""Figure interaction configuration, polar validation, and payload specs."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Optional

import numpy as np

from .config import POLAR_DIRECT_CEILING, POLAR_MARK_KINDS

if TYPE_CHECKING:
    from ._figure import Figure


def set_interaction(
    self,
    *,
    hover: Optional[bool] = None,
    click: Optional[bool] = None,
    select: Optional[bool] = None,
    brush: Optional[bool] = None,
    crosshair: Optional[bool] = None,
    navigation: Optional[bool] = None,
    pan: Optional[bool] = None,
    pan_axes: Optional[tuple[str, ...]] = None,
    zoom: Optional[bool] = None,
    default_drag_action: Optional[str] = None,
    zoom_axes: Optional[tuple[str, ...]] = None,
    zoom_limits: Any = None,
    wheel_zoom: Optional[bool] = None,
    box_zoom: Optional[bool] = None,
    zoom_buttons: Optional[bool] = None,
    double_click_reset: Optional[bool] = None,
    reset_axes: Optional[tuple[str, ...]] = None,
    link_group: Optional[str] = None,
    link_axes: Optional[tuple[str, ...]] = None,
    link_select: Optional[bool] = None,
    history: Optional[bool] = None,
) -> "Figure":
    updates: dict[str, Any] = {}
    for name, value in (
        ("hover", hover),
        ("click", click),
        ("select", select),
        ("brush", brush),
        ("crosshair", crosshair),
        ("navigation", navigation),
        ("pan", pan),
        ("zoom", zoom),
        ("wheel_zoom", wheel_zoom),
        ("box_zoom", box_zoom),
        ("zoom_buttons", zoom_buttons),
        ("double_click_reset", double_click_reset),
        ("link_select", link_select),
        ("history", history),
    ):
        normalized = self._optional_bool(value, f"interaction {name}")
        if normalized is not None:
            updates[name] = normalized
    for name, axes in (
        ("pan_axes", pan_axes),
        ("zoom_axes", zoom_axes),
        ("reset_axes", reset_axes),
    ):
        if axes is not None:
            updates[name] = self._axis_policy(axes, name)
    if zoom_limits is not None:
        updates["zoom_limits"] = zoom_limits
    if default_drag_action is not None:
        updates["default_drag_action"] = self._default_drag_action(default_drag_action)
    if link_group is not None:
        group = self._optional_text(link_group, "interaction link_group")
        if not group:
            raise ValueError("interaction link_group must be a non-empty string or None")
        updates["link_group"] = group
    if link_axes is not None:
        updates["link_axes"] = self._axis_policy(link_axes, "link_axes")
    self.interaction.update(updates)
    return self


def set_mark_style(
    self,
    *,
    hover: Optional[dict[str, Any]] = None,
    selected: Optional[dict[str, Any]] = None,
    unselected: Optional[dict[str, Any]] = None,
) -> "Figure":
    """Configure legacy standalone hover/selection styling.

    This low-level compatibility hook is intentionally not exposed by the
    declarative component API. Reflex integrations should derive ordinary
    mark props/styles from Reflex state instead of maintaining XYG state.
    """
    for state, value in (
        ("hover", hover),
        ("selected", selected),
        ("unselected", unselected),
    ):
        style = self._optional_state_style(value, f"mark_style {state}")
        if style:
            self.mark_style[state] = {**self.mark_style.get(state, {}), **style}
    return self


def _default_drag_action(value: Any) -> str:
    allowed = {
        "auto",
        "none",
        "pan",
        "zoom",
        "select",
        "select-x",
        "select-y",
        "select-lasso",
    }
    if not isinstance(value, str) or value not in allowed:
        choices = ", ".join(repr(mode) for mode in sorted(allowed))
        raise ValueError(f"interaction default_drag_action must be one of {choices}")
    return value


def _zoom_limit_pair(value: Any, label: str) -> list[Optional[float]]:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError(f"{label} must be a two-item tuple/list")
    normalized: list[Optional[float]] = []
    for endpoint in value:
        if endpoint is None:
            normalized.append(None)
            continue
        if isinstance(endpoint, (bool, np.bool_)):
            raise ValueError(f"{label} endpoints must be positive finite numbers or None")
        try:
            number = float(endpoint)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} endpoints must be positive finite numbers or None") from exc
        if not np.isfinite(number) or number <= 0:
            raise ValueError(f"{label} endpoints must be positive finite numbers or None")
        normalized.append(number)
    lower, upper = normalized
    if lower is not None and upper is not None and lower > upper:
        raise ValueError(f"{label} lower endpoint must not exceed its upper endpoint")
    if (lower is not None and lower > 1.0) or (upper is not None and upper < 1.0):
        raise ValueError(f"{label} must contain home magnification 1.0")
    return normalized


def _zoom_limits(self, value: Any) -> dict[str, list[Optional[float]]]:
    selected = self._interaction_axes("zoom_axes")
    default = [1.0, None]
    if isinstance(value, Mapping):
        unknown = [axis for axis in value if axis not in self.axis_options]
        if unknown:
            raise ValueError(f"interaction zoom_limits contains unknown axis IDs {unknown!r}")
        normalized = {axis: list(default) for axis in selected}
        for axis in self.axis_options:
            if axis in value:
                normalized[axis] = self._zoom_limit_pair(
                    value[axis], f"interaction zoom_limits[{axis!r}]"
                )
        return normalized
    pair = self._zoom_limit_pair(value, "interaction zoom_limits")
    return {axis: list(pair) for axis in selected}


def _interaction_axes(self, name: str) -> list[str]:
    value = self.interaction.get(name)
    return list(self.axis_options) if value is None else self._axis_policy(value, name)


def _validate_coords(self) -> None:
    """Refuse mark kinds the polar transform does not yet render correctly.

    A whole-scene check rather than a per-mark one: marks can be appended
    at any time, so only payload-build time sees the finished figure.

    The refusal is deliberate. Every unsupported kind here *would* draw
    something — a bar would come out as a chord-edged rectangle rather than
    an annular sector, an area would fill the wrong region — and a
    plausible wrong picture is worse than an error. §28 requires the
    decision to ship rather than be silently approximated.
    """
    if self.coords != "polar":
        return
    unsupported = sorted({t.kind for t in self.traces} - POLAR_MARK_KINDS)
    if unsupported:
        raise ValueError(
            f"coords='polar' does not support {unsupported} yet; "
            f"supported kinds are {sorted(POLAR_MARK_KINDS)}. "
            "See spec/design/polar-axes.md."
        )
    unsupported_annotations = sorted(
        {str(annotation.get("kind")) for annotation in self.annotations} & {"rule", "band"}
    )
    if unsupported_annotations:
        raise ValueError(
            "coords='polar' does not support rule/band annotations yet; "
            f"found {unsupported_annotations}. Point-anchored text, label, marker, "
            "arrow, and callout annotations remain supported."
        )
    # One angular and one radial axis, no more. A secondary axis binds and
    # validates exactly like a Cartesian one, but the polar transform reads
    # only the primary pair, so the result is the failure this method exists
    # to prevent: an overlapping secondary range draws *pixel-identical* to
    # the primary, inviting the reader to decode it against a tick ladder it
    # does not belong to, while a disjoint one culls the series away
    # entirely — and either way the axis still gets its Cartesian spine and
    # title drawn in the gutter of a disc. Refuse instead.
    extra_axes = sorted(
        (set(self.axis_options) | {t.x_axis for t in self.traces} | {t.y_axis for t in self.traces})
        - {"x", "y"}
    )
    if extra_axes:
        raise ValueError(
            "coords='polar' supports a single angular ('x') and radial ('y') "
            f"axis; found {extra_axes}. See spec/design/polar-axes.md."
        )
    theta = self.axis_options.get("x", {})
    # A non-linear *angle* has no coherent projection, and the two renderers
    # never agreed on one: the client scales theta before projecting it
    # while the static exporters ignore the scale outright (their SVG is
    # byte-identical across linear/log/symlog), so the same figure points a
    # datum at opposite sides of the disc depending on where it is drawn.
    # The spec offers a scale row for r only; a log radial axis stays valid.
    # Inspecting only the *declared* spelling let an inferred time column
    # through: datetime theta shipped with kind="time" pinned to a fixed
    # 0..2pi range, so twelve consecutive days wrapped the disc billions of
    # times and the spokes were labelled as radians. `theta_axis(domain=)`
    # is aliased to `sector`, so there was no escape hatch either. Refuse on
    # the resolved kind, and say what a time angle would have to mean.
    if self._axis_kind("x") == "time":
        raise ValueError(
            "coords='polar' does not support a time angular axis; an "
            "instant has no angle. Map time onto the turn yourself — e.g. "
            "theta = 2*pi * ((t - t0) / period) — and pass the result as a "
            "number. A time *radial* axis (r_axis) is supported."
        )
    theta_scale = theta.get("type")
    if theta_scale is not None and theta_scale != "linear":
        raise ValueError(
            f"coords='polar' does not support a {theta_scale!r} angular axis; "
            "the angle must be linear. A log or symlog *radial* axis "
            "(r_axis) is supported. See spec/design/polar-axes.md."
        )
    # `reverse` is the Cartesian "flip this axis" switch; on a disc the
    # equivalent is a direction of travel, which the angular axis already
    # spells as `direction`. It rode the wire as `"reverse": true` and every
    # renderer ignored it, so the axis silently drew unreversed — the same
    # accepted-but-inert trap as a secondary axis. Point at the switch that
    # works instead. (`r_axis(reverse=True)` is honoured and unaffected.)
    if theta.get("reverse"):
        raise ValueError(
            "coords='polar' does not support reverse=True on the angular "
            "axis; use theta_axis(direction='clockwise') to reverse the "
            "direction of travel. See spec/design/polar-axes.md."
        )
    sector = theta.get("sector")
    if sector is not None:
        unit = theta.get("theta_unit") or "radians"
        turn = 360.0 if unit == "degrees" else 2.0 * math.pi
        if sector[1] - sector[0] > turn:
            raise ValueError(f"x axis sector sweep must not exceed one full turn ({turn:g} {unit})")
    radial = self.axis_options.get("y", {})
    r_origin = radial.get("r_origin")
    if r_origin is not None:
        # The first resolved limit is the centre-side ring and the second
        # is the outer ring.  On an ordinary radial axis that means the
        # origin lies at/below r_lo; reversing the axis reverses that
        # inequality too.  Sorting here accepted an origin on the wrong
        # side of a reversed view, which then normalized every visible
        # radius beyond 1 and culled the entire plot.
        r_inner, r_outer = self._range("y")
        if radial.get("type") == "log" and r_origin <= 0:
            raise ValueError("y log axis r_origin must be positive")
        if r_inner < r_outer:
            if not r_origin < r_outer:
                raise ValueError("y axis r_origin must be less than the resolved radial maximum")
            if r_origin > r_inner:
                raise ValueError("y axis r_origin must not exceed the resolved radial minimum")
        else:
            if not r_origin > r_outer:
                raise ValueError("y axis r_origin must be greater than the resolved radial minimum")
            if r_origin < r_inner:
                raise ValueError(
                    "y axis r_origin must not be less than the resolved radial maximum"
                )
    for t in self.traces:
        # heatmap/contour are exempt because a cell grid legitimately
        # carries more cells than the *point* ceiling. Narrowing the gate
        # to that end un-capped bar/column/errorbar as collateral, and a
        # polar bar is the most expensive mark there is — 2*(96+1) verts
        # per wedge against a cartesian quad's 4 — so a million of them
        # built without a word. Name every capped kind explicitly.
        if (
            t.kind in {"line", "scatter", "area", "bar", "column", "errorbar"}
            and t.n_points > POLAR_DIRECT_CEILING
        ):
            # Polar has no decimation or density tier to fall back to
            # (polar-axes.md §7), so past the cap the only honest options
            # are refusing or an unbounded direct draw. Refuse, and say
            # which trace and why.
            raise ValueError(
                f"polar {t.kind} trace has {t.n_points:,} points, over the "
                f"{POLAR_DIRECT_CEILING:,}-point polar ceiling: polar traces "
                "always draw every point (no decimation/density tier yet — "
                "spec/design/polar-axes.md §7). Reduce the data or bin it "
                "before charting."
            )


def _zoom_enabled(self) -> bool:
    """The resolved `zoom` capability.

    `zoom` is the one interaction switch whose default depends on the
    coordinate system: polar resolves it to False (polar-axes.md §8 — the
    centre is a fixed point, so zooming a constant-rim composition crops it
    instead of navigating it), Cartesian to True. Every consumer of the
    resolved value goes through here, so validation and the payload cannot
    disagree about it — they did, and `default_drag_action='zoom'` on a
    polar chart passed construction only to ship the self-contradicting
    `{"zoom": false, "default_drag_action": "zoom"}`.
    """
    value = self.interaction.get("zoom")
    if value is None:
        return self.coords != "polar"
    return value is not False


def _validate_interaction(self) -> None:
    for name in ("pan_axes", "zoom_axes", "reset_axes", "link_axes"):
        if name in self.interaction:
            self._axis_policy(self.interaction[name], name)
    if "zoom_limits" in self.interaction:
        self._zoom_limits(self.interaction["zoom_limits"])
    action = self.interaction.get("default_drag_action")
    if action is None:
        return
    action = self._default_drag_action(action)
    if action in {"auto", "none"}:
        return
    if self.coords == "polar":
        # A disc has no drag tools at all (polar-axes.md §8), which is why
        # polar's resolved drag mode is `none`: the client returns [] for
        # `pan_axes` and forces `box_zoom`/`select`/`brush` off under polar,
        # whatever the flags say. So every action but `auto`/`none` is
        # accepted-and-inert — the plausible-but-wrong outcome §28 refuses
        # everywhere else in this validator. Radial zoom is unaffected: it is
        # a wheel/button gesture, not a drag.
        raise ValueError(
            f"coords='polar' does not support default_drag_action={action!r}; a "
            "disc has no drag tools (theta pan, box zoom, and rectangular/lasso "
            "selection all lack polar geometry), so only 'auto' and 'none' are "
            "meaningful. Radial zoom is a separate wheel/button capability, "
            "controlled by the `zoom` switch rather than by a drag action. See "
            "spec/design/polar-axes.md."
        )

    def enabled(name: str) -> bool:
        # `zoom` reads through the resolved predicate rather than the raw
        # dict so this can never disagree with what `_interaction_spec`
        # ships. The polar guard above means the two currently agree for
        # every action that reaches here; keeping the indirection is what
        # stops that from silently ceasing to be true.
        if name == "zoom":
            return self._zoom_enabled()
        return self.interaction.get(name, True) is not False

    if action == "pan" and not (enabled("navigation") and enabled("pan")):
        raise ValueError("interaction default_drag_action='pan' requires navigation and pan")
    if action == "zoom" and not (enabled("navigation") and enabled("zoom") and enabled("box_zoom")):
        raise ValueError(
            "interaction default_drag_action='zoom' requires navigation, zoom, and box_zoom"
        )
    if action.startswith("select") and not (
        enabled("select") and enabled("brush") and any(t.kind == "scatter" for t in self.traces)
    ):
        raise ValueError(
            f"interaction default_drag_action={action!r} requires select, brush, and pickable data"
        )


def _interaction_spec(self) -> dict[str, Any]:
    self._validate_interaction()
    spec: dict[str, Any] = {}
    for name in (
        "hover",
        "click",
        "select",
        "brush",
        "crosshair",
        "navigation",
        "pan",
        "zoom",
        "wheel_zoom",
        "box_zoom",
        "zoom_buttons",
        "double_click_reset",
        "link_select",
        "history",
    ):
        if name in self.interaction:
            spec[name] = self._bool_param(self.interaction[name], f"interaction {name}")
    if "zoom" not in self.interaction and not self._zoom_enabled():
        # Polar zoom is OFF by default (polar-axes.md §8). The centre is a
        # fixed point of the transform and r_lo is pinned, so zooming in
        # only crops the rim while the geometry stays welded to the middle
        # of the disc — on a pie, radial bar, or radar, whose radius is a
        # constant rim or a fixed frame, that reads as broken rather than as
        # navigation. A composition whose RADIUS is a measured quantity
        # (`wind_rose`, where it is a frequency count) opts back in by
        # shipping `zoom=True`, as does any author via
        # `xyg.interaction_config(zoom=True)`; an ordinary `polar_chart` whose
        # radius IS data is expected to do the same.
        #
        # Resolved HERE and shipped explicitly, against §5.2's "unspecified
        # keys stay absent" rule, for two reasons: the client cannot make
        # this decision (`Chart.kind` never reaches the wire — every polar
        # figure looks identical to it), and §28 requires the choice to be
        # on the wire rather than re-derived per renderer. The predicate is
        # `_zoom_enabled` so validation resolves the same default this ships.
        spec["zoom"] = False
    for name in ("pan_axes", "zoom_axes", "reset_axes", "link_axes"):
        if name in self.interaction:
            spec[name] = self._axis_policy(self.interaction[name], name)
    if "zoom_limits" in self.interaction:
        spec["zoom_limits"] = self._zoom_limits(self.interaction["zoom_limits"])
    if "default_drag_action" in self.interaction:
        spec["default_drag_action"] = self._default_drag_action(
            self.interaction["default_drag_action"]
        )
    link_group = self.interaction.get("link_group")
    if link_group is not None:
        group = self._optional_text(link_group, "interaction link_group")
        if not group:
            raise ValueError("interaction link_group must be a non-empty string or None")
        spec["link_group"] = group
    return spec


def _mark_style_spec(self) -> dict[str, Any]:
    spec: dict[str, Any] = {}
    for state in ("hover", "selected", "unselected"):
        style = self._optional_state_style(self.mark_style.get(state), f"mark_style {state}")
        if style:
            spec[state] = style
    return spec


def _optional_state_style(
    self: "Figure",
    value: Optional[dict[str, Any]],
    label: str,
) -> dict[str, str | int | float]:
    if value is None:
        return {}
    return self._style_mapping(value, label)
