"""anywidget integration (§33.3): one widget implementation covers Jupyter,
JupyterLab, VS Code, Colab, and Marimo, with a binary comm channel — spec as
JSON, data as raw buffers, never base64/JSON numbers (§29 Jupyter row).

The JS render client ships inside the wheel as a static asset — versioned,
no CDN (§33.2, airgapped notebooks).
"""

from __future__ import annotations

import math
import pathlib
import struct
from concurrent.futures import Future
from typing import TYPE_CHECKING, Any

import anywidget
import traitlets

# Selection lives in figure.py (it's the on_select payload and has no widget
# dependency); re-exported here for backward compatibility.
from ._figure import Selection
from .channel import ChannelCallbacks, handle_message

if TYPE_CHECKING:
    from ._figure import Figure

_STATIC = pathlib.Path(__file__).parent / "static"

__all__ = ["FigureWidget", "Selection", "bundled_js"]


def bundled_js(which: str = "widget") -> str:
    """Read a bundled client build ("widget" ESM or "standalone" IIFE)."""
    name = "index.js" if which == "widget" else "standalone.js"
    path = _STATIC / name
    if not path.exists():
        raise FileNotFoundError(
            f"{path} missing — the JS render client was not bundled into this "
            "install. The bundle is a generated artifact (not committed to git); "
            "a published wheel/sdist ships it prebuilt. From a source checkout, "
            "build it once with `npm ci && node js/build.mjs`."
        )
    return path.read_text(encoding="utf-8")


class FigureWidget(anywidget.AnyWidget):
    """The live notebook widget host: a data-less JSON spec plus raw binary
    column buffers, rendered by the shipped ES module."""

    _esm = _STATIC / "index.js"

    # Data-less spec (§9) — tiny JSON, sync'd as a trait.
    spec = traitlets.Dict().tag(sync=True)
    # Encoded columns — raw binary, never JSON. First paint and streaming
    # append both ship the split layout: a list of per-column memoryviews,
    # each transported as its own binary comm frame with no join copy (§29).
    # The trait stays Any so the client picks the layout from
    # `spec.buffer_layout`, not the trait shape (older saved outputs may
    # still hold a packed blob).
    buffers = traitlets.Any().tag(sync=True)

    def __init__(
        self,
        figure: "Figure",
        *,
        on_hover: Any = None,
        on_click: Any = None,
        on_brush: Any = None,
        on_select: Any = None,
        on_view_change: Any = None,
        on_animation_start: Any = None,
        on_animation_end: Any = None,
        wasm_ticks: Any = None,
        **kwargs: Any,
    ) -> None:
        self._figure = figure
        self._callbacks = ChannelCallbacks(
            on_hover=on_hover,
            on_click=on_click,
            on_brush=on_brush,
            on_select=on_select,
            on_view_change=on_view_change,
            on_animation_start=on_animation_start,
            on_animation_end=on_animation_end,
        )
        spec, bufs = figure.build_payload_split()
        self._configure_transport(spec)
        if wasm_ticks is not None:
            from .export import resolve_wasm_tick_assets

            spec["wasm_ticks"] = resolve_wasm_tick_assets(wasm_ticks)
        super().__init__(spec=spec, buffers=bufs, **kwargs)
        self.on_msg(self._on_custom_msg)

    def _configure_transport(self, spec: dict[str, Any]) -> None:
        """Attach private subscriptions without changing browser behavior."""
        if self._callbacks.on_view_change is not None:
            spec["interaction"] = {
                **spec.get("interaction", {}),
                "_transport_view_change": True,
            }

    def append(
        self,
        trace_id: int,
        x: Any,
        y: Any,
        *,
        color: Any = None,
        size: Any = None,
        stroke: Any = None,
        opacity: Any = None,
        alpha: Any = None,
        stroke_width: Any = None,
        symbol: Any = None,
    ) -> None:
        """Streaming append: extend a trace's data and push the refresh to the
        client.

        The refresh is the trait update itself: one comm message carrying the
        fresh spec plus split-layout buffers, which the client applies when
        `spec.append.seq` advances — and which doubles as the notebook-reopen
        state. The payload crosses the wire exactly once per tick; there is no
        separate custom-message send."""
        msg, buffers = self._figure.append(
            trace_id,
            x,
            y,
            color=color,
            size=size,
            stroke=stroke,
            opacity=opacity,
            alpha=alpha,
            stroke_width=stroke_width,
            symbol=symbol,
        )
        self._configure_transport(msg["spec"])
        with self.hold_sync():
            self.spec = msg["spec"]
            self.buffers = buffers

    # -- programmatic view state (spec/design/view-state.md §5.1) ------------

    def set_view(
        self,
        ranges: Any = None,
        *,
        animate: bool = True,
        history: bool = True,
    ) -> None:
        """Apply a partial per-axis ranges patch through the client's single
        clamped mutation path (merge-patch: absent axes are untouched)."""
        msg = self._figure.state_patch_message(ranges=ranges, animate=animate, history=history)
        self.send(msg)

    def reset_view(self, axes: Any = None) -> None:
        """Navigate to the home ranges (None = the configured reset_axes)."""
        self.send(self._figure.view_nav_message(axes))

    def select(
        self,
        *,
        range: Any = None,
        polygon: Any = None,
        rows: Any = None,
        history: bool = True,
    ) -> None:
        """Programmatic selection. Geometric forms (`range=`/`polygon=`) ship
        to the client and resolve exactly like a gesture; `rows=` resolves
        kernel-side into mask buffers and is non-durable (history is ignored
        for it, and `view_state()` reports only the opaque rows marker)."""
        if rows is not None:
            if range is not None or polygon is not None:
                raise ValueError("pass rows= alone, or range=/polygon= without rows=")
            msg, buffers = self._figure.selection_rows_message(rows)
            self._figure._record_selection({"rows": True})
            self.send(msg, buffers=buffers)
            return
        selection = self._figure._validated_state_selection(range=range, polygon=polygon)
        if selection is None:
            raise ValueError("select() needs range=, polygon=, or rows=")
        self.send(self._figure.state_patch_message(selection=selection, history=history))

    def clear_selection(self) -> None:
        """Clear any selection (durable: history records it)."""
        self.send(self._figure.state_patch_message(selection=None))

    def view_state(self) -> dict[str, Any]:
        """Last committed durable view state (kernel-side cache, §5.1)."""
        return self._figure.view_state()

    def _on_custom_msg(self, widget: Any, content: Any, msg_buffers: Any) -> None:
        # All dispatch and callback semantics live in channel.handle_message
        # (reflex-integration §3.1) — this widget is one transport among
        # (eventually) several; it only owns the anywidget comm send.
        reply = handle_message(self._figure, content, msg_buffers, callbacks=self._callbacks)
        if reply is not None:
            msg, buffers = reply
            self.send(msg, buffers=buffers)


class GeoWidget(anywidget.AnyWidget):
    """Binary native geographic frame transport with release acknowledgements."""

    _esm = _STATIC / "index.js"
    spec = traitlets.Dict().tag(sync=True)
    buffers = traitlets.Any().tag(sync=True)

    def __init__(self, adapter, **kwargs):
        self._adapter = adapter
        self._close_requested = False
        self._geo_updates = {}
        self._geo_update_serial = 0
        super().__init__(spec={"geo_host": True}, buffers=[], **kwargs)
        self.on_msg(self._on_geo_message)

    def update(
        self, *, operation, args, sequence, camera_revision, time_revision, state_revision, time
    ):
        """Return a Future settled after visual commit and exact retirement ACK."""
        if self._close_requested:
            raise RuntimeError("geographic widget disposed")
        if len(self._geo_updates) >= 16:
            raise RuntimeError("geographic widget update queue is full")
        args = tuple(args)
        if (
            type(operation) is not int
            or not 0 <= operation <= 9
            or len(args) > 5
            or any(type(x) not in (int, float) or not math.isfinite(x) for x in args)
        ):
            raise ValueError("invalid camera authoring")
        revisions = (sequence, camera_revision, time_revision, state_revision)
        if any(type(n) is not int or not 0 <= n < 1 << 64 for n in revisions):
            raise ValueError("exact u64 revisions required")
        kind = time.get("kind")
        allowed = {"kind"} | (
            {"instant"} if kind == 1 else {"start", "end"} if kind == 2 else set()
        )
        if type(kind) is not int or kind not in (0, 1, 2) or set(time) != allowed:
            raise ValueError("invalid signed time authoring")
        start = time["instant"] if kind == 1 else time["start"] if kind == 2 else 0
        end = time["end"] if kind == 2 else 0
        if any(type(n) is not int or not -(1 << 63) <= n < 1 << 63 for n in (start, end)):
            raise ValueError("exact i64 time required")
        packet = bytearray(128)
        struct.pack_into(
            "<4sIII4QI4x5d2q",
            packet,
            0,
            b"XYHU",
            1,
            operation,
            len(args),
            *revisions,
            kind,
            *(args + (0,) * (5 - len(args))),
            start,
            end,
        )
        self._geo_update_serial += 1
        request = f"update:{self._geo_update_serial}"
        future = Future()
        self._geo_updates[request] = future
        try:
            self.send({"type": "geo_host_update", "request": request}, buffers=[bytes(packet)])
        except BaseException:
            self._geo_updates.pop(request, None)
            raise
        return future

    def _on_geo_message(self, widget, content, msg_buffers):
        if isinstance(content, dict) and content.get("type") == "geo_host_updated":
            future = self._geo_updates.pop(content.get("request"), None)
            if future is not None and not future.done():
                if isinstance(content.get("error"), str):
                    future.set_exception(RuntimeError(content["error"]))
                else:
                    future.set_result(None)
            return
        reply = self._adapter.handle_host_message(content, msg_buffers)
        if reply is not None:
            message, buffers = reply
            self.send(message, buffers=buffers)
        if self._close_requested and not self._adapter.mounted:
            super().close()

    def close(self):
        adapter = getattr(self, "_adapter", None)
        if adapter is None:
            return super().close()
        self._close_requested = True
        for future in self._geo_updates.values():
            if not future.done():
                future.set_exception(RuntimeError("geographic widget disposed"))
        self._geo_updates.clear()
        adapter.close()
        if adapter.mounted:
            self.send({"type": "geo_host_close"})
        else:
            super().close()
