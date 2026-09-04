"""Binary blob + column table accumulator for ``build_payload`` (§29)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from . import kernels, lod

if TYPE_CHECKING:
    from .columns import Column


class PayloadWriter:
    """Accumulates the binary blob + column table for ``build_payload``.

    The single place that knows the wire encoding, so every chart type ships
    columns the same way (§29): ``ship`` for offset-encoded geometry (§4), and
    ``ship_scalar`` for raw f32 channels/grids already in final units, and
    ``ship_u8`` for byte-precision categorical/density values. Adding a chart
    means calling these, not re-implementing the encoding.
    """

    def __init__(
        self,
        *,
        split: bool = False,
        wasm_source: bool = False,
        borrow_heatmaps: bool = False,
        point_overlay: bool = True,
    ) -> None:
        if wasm_source and not split:
            raise ValueError("wasm_source requires split payload buffers")
        # split=True: every column ships as its own wire buffer — spec entries
        # carry `buf` (the wire-buffer index) with byte_offset 0, and
        # `buffers()` returns per-column views with no join copy. Packed mode
        # keeps the single `blob()` with global byte offsets (standalone
        # export, streaming-refresh reopen state).
        self.columns: list[dict[str, Any]] = []
        self._chunks: list[bytes | np.ndarray] = []
        self._pos = 0
        self._split = split
        # Canonical replay columns are an explicit Worker/WASM transport, not
        # part of the ordinary split painter payload (§27/§29; #864).
        self.wasm_source = bool(wasm_source)
        self.borrow_heatmaps = borrow_heatmaps
        self.borrowed: list[np.ndarray] = []
        # point_overlay=False: skip the density tier's sampled point overlay.
        # Only the *raster* exporters set this. They draw density traces
        # through `_emit_grid`, which never reads `density["sample"]`, so on
        # that path the overlay is an O(N) SplitMix scan plus two gathers whose
        # result no pixel consumes. The browser client *does* draw it
        # (`50_chartview.ts`), so `build_payload`/`build_payload_split` must
        # keep shipping it.
        self.point_overlay = point_overlay

    def ship(self, values: np.ndarray, col: "Column", *, scale: str | None = None) -> int:
        """Offset-encoded geometry column: ``(v - offset) * scale`` as f32
        (§4/§16). Scale is 1.0 except for absurd-magnitude domains, where it
        normalizes so finite f64 can't overflow to ±inf in f32 (§19).
        ``scale`` is the target axis scale: log-family axes pin the offset to
        0.0 (``lod.geometry_offset``) so relative f32 precision survives the
        shader-side transform."""
        offset = (
            lod.geometry_offset(scale, col.min, col.max)
            if lod.pins_offset_to_zero(scale)
            else col.suggest_offset()
        )
        encoded = lod.encode_f32_values(
            values,
            offset,
            col.min,
            col.max,
            kind=col.kind,
        )
        return self._append(encoded.values, encoded.meta)

    def ship_scalar(self, values: np.ndarray) -> int:
        """Raw f32 column already in final units (no offset): channel/grid/heights."""
        enc = np.ascontiguousarray(values, dtype=np.float32)
        return self._append(enc, {})

    def ship_u8(self, values: np.ndarray) -> int:
        """Raw byte column, padded so every later f32 column stays aligned."""
        enc = np.ascontiguousarray(values, dtype=np.uint8).reshape(-1)
        index = len(self.columns)
        if self._split:
            padding = (-len(enc)) % 4
            padded = np.concatenate([enc, np.zeros(padding, np.uint8)]) if padding else enc
            self.columns.append(
                {"buf": len(self._chunks), "byte_offset": 0, "len": int(len(enc)), "dtype": "u8"}
            )
            self._chunks.append(padded)
            self._pos += padded.nbytes
            return index
        self.columns.append({"byte_offset": self._pos, "len": int(len(enc)), "dtype": "u8"})
        self._chunks.append(enc)
        self._pos += enc.nbytes
        padding = (-self._pos) % 4
        if padding:
            self._chunks.append(bytes(padding))
            self._pos += padding
        return index

    def ship_u32(self, values: np.ndarray) -> int:
        """Raw uint32 identity words used by keyed transitions."""
        enc = np.ascontiguousarray(values, dtype="<u4").reshape(-1)
        return self._append(enc, {"dtype": "u32"})

    def ship_f64(self, values: np.ndarray) -> int:
        """Ship a canonical f64 column for an explicitly bounded WASM source."""
        return self._append(
            np.ascontiguousarray(values, dtype="<f8").reshape(-1),
            {"dtype": "f64"},
        )

    def borrow_f64(self, values: np.ndarray) -> int:
        """Register canonical f64 storage as a synchronous raster-only span."""
        arr = np.ascontiguousarray(values, dtype="<f8").reshape(-1)
        span = len(self.borrowed) + 1
        self.borrowed.append(arr)
        index = len(self.columns)
        self.columns.append({"span": span, "byte_offset": 0, "len": int(len(arr)), "dtype": "f64"})
        return index

    def ship_values(
        self, values: np.ndarray, *, kind: str = "float", scale: str | None = None
    ) -> int:
        """Offset-encoded temporary geometry not backed by a canonical Column."""
        vals = np.ascontiguousarray(values, dtype=np.float64)
        bounds = kernels.min_max(vals)
        lo, hi = bounds if bounds is not None else (0.0, 0.0)
        offset = lod.geometry_offset(scale, lo, hi) if bounds is not None else 0.0
        encoded = lod.encode_f32_values(vals, offset, lo, hi, kind=kind)
        return self._append(encoded.values, encoded.meta)

    def append_from_materialized(self, enc: np.ndarray, meta: dict[str, Any]) -> int:
        """Register a Rust-materialized column without host-side re-encoding."""
        enc = np.ascontiguousarray(enc)
        idx = len(self.columns)
        if self._split:
            self.columns.append({"buf": len(self._chunks), "byte_offset": 0, **meta})
            self._chunks.append(enc)
            self._pos += enc.nbytes
            return idx
        self.columns.append({"byte_offset": self._pos, **meta})
        self._chunks.append(enc)
        self._pos += enc.nbytes
        if meta.get("dtype") != "u8" and meta.get("dtype") != "u32":
            padding = (-self._pos) % 4
            if padding:
                self._chunks.append(bytes(padding))
                self._pos += padding
        return idx

    def _append_from_materialized(self, enc: np.ndarray, meta: dict[str, Any]) -> int:
        return self.append_from_materialized(enc, meta)

    def _append(self, enc: np.ndarray, meta: dict[str, Any]) -> int:
        enc = np.ascontiguousarray(enc)
        idx = len(self.columns)
        if self._split:
            self.columns.append(
                {"buf": len(self._chunks), "byte_offset": 0, "len": int(len(enc)), **meta}
            )
        else:
            self.columns.append({"byte_offset": self._pos, "len": int(len(enc)), **meta})
        self._chunks.append(enc)
        self._pos += enc.nbytes
        return idx

    def blob(self) -> bytes:
        return b"".join(
            chunk if isinstance(chunk, bytes) else chunk.data.cast("B") for chunk in self._chunks
        )

    def buffers(self) -> list[memoryview]:
        """Per-column wire buffers (split mode): zero-copy views over the
        encoded chunks, ready to ship as separate binary comm frames."""
        return [
            memoryview(c).cast("B") if isinstance(c, bytes) else c.data.cast("B")
            for c in self._chunks
        ]


# Back-compat alias for internal imports that still use the private name.
_PayloadWriter = PayloadWriter
