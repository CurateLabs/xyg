"""Independent scalar oracle for the shared linked density protocol fixture.

Only canonical ingress/predicate bytes feed this model. It neither calls kernels
nor reads production bin/slab implementations or expected packet counts.
"""

import hashlib
import math
import struct


class DensityOracle:
    def __init__(self):
        self.columns = []
        self.clauses = {}
        self.base = {}
        self.mask = b""
        self.intent = None
        self.active = None
        self.edit = None
        self.views = []
        self.source_revision = 0
        self.visible = 0
        self.index_present = False
        self.active_cells = 0

    def check(self, packet, reply):
        op = struct.unpack_from("<I", packet, 8)[0]
        args = struct.unpack_from("<3Q", packet, 56)
        seq, source_id, epoch = struct.unpack_from("<3Q", packet, 16)
        if reply["status"]:
            assert reply["revision"] == self.visible
            if self.active:
                assert reply["filter_hash"] == self.last_hash
                assert reply["has_intent"] == bool(
                    self.intent is not None or self.clauses or self.base or self.mask
                )
            return
        self.visible = seq
        assert reply["requested_revision"] == seq and reply["newest_revision"] == seq
        if op in (1, 2, 6, 12, 14):
            self.index_present = False
        if op in (4, 5, 7, 10, 11):
            self.index_present = True
        if op in (1, 2):
            dims, n, first = args
            if op == 1:
                self.columns = [[] for _ in range(dims)]
                self.first = first
                self.source_id, self.epoch = source_id, epoch
            for d in range(dims):
                self.columns[d].extend(struct.unpack_from(f"<{n}d", packet, 96 + d * n * 8))
            self.source_revision += 1
        if op == 10:
            if self.active and self.intent is not None:
                self.clauses[self.active] = self.intent
            ident, dimension, n = args
            self.active = (ident, dimension)
            self.intent = self.clauses.pop(self.active, None)
            self.active_cells = struct.unpack_from("<Q", packet, 96)[0] + 1
            at = 104 + (self.active_cells - 1) * 8
            self.views = []
            for _ in range(n):
                ident, x, y, w, h, *bounds = struct.unpack_from("<3Q2I4d", packet, at)
                colors = (
                    packet[at + 64 : at + 72]
                    if struct.unpack_from("<I", packet, at + 72)[0]
                    else bytes([57, 135, 229, 255, 239, 105, 45, 255])
                )
                self.views.append(
                    (ident, x, y, w, h, sorted(bounds[:2]) + sorted(bounds[2:]), colors)
                )
                at += 80
        if op == 5:
            self.intent = sorted(struct.unpack_from("<2d", packet, 80))
        if op == 7:
            self.intent, self.clauses = None, {}
        if op == 12:
            self.base = {}
            for i in range(args[0]):
                dim, lo, hi = struct.unpack_from("<Q2d", packet, 96 + i * 24)
                self.base[(0, dim)] = sorted((lo, hi))
            self.mask = packet[96 + args[0] * 24 :]
        if op == 13:
            self.edit = dict(self.clauses)
            if self.intent is not None:
                self.edit[self.active] = self.intent
        if op == 14:
            self.clauses = self.edit
            self.intent = self.clauses.pop(self.active, None)
            self.edit = None
        if op == 15:
            self.edit = None
        assert reply["source_id"] == source_id and reply["epoch"] == epoch
        assert reply["source_revision"] == self.source_revision
        assert reply["source_rows"] == len(self.columns[0])
        assert reply["first_row"] == self.first
        if not self.active:
            return
        assert reply["affected_count"] == len(self.views)
        assert [v["id"] for v in reply["views"]] == [v[0] for v in self.views]
        width = 1 + sum(v[3] * v[4] for v in self.views)
        expected_index = 8 * (self.active_cells + 1) * width + 16 * width + 16 * self.active_cells
        assert reply["index_bytes"] == (expected_index if self.index_present else 0)
        assert (
            reply["resident_bytes"]
            <= reply["peak_bytes"]
            <= struct.unpack_from("<Q", packet, 48)[0]
        )
        if op in (4, 10):
            assert reply["rows_read"] == len(self.columns[0]) and reply["tier"] == 0
        if op in (6, 8, 12, 13, 14, 15):
            assert reply["rows_read"] == 0 and reply["tier"] == 0
        assert reply["membership_bytes"] == ((args[1] + 7) // 8 if op == 9 else 0)
        assert reply["page_first"] == (args[0] if op == 9 else 0)
        clauses = dict(self.clauses)
        if self.intent is not None:
            clauses[self.active] = self.intent
        h = hashlib.blake2s(digest_size=8, person=b"xyfilt02")
        h.update(
            struct.pack(
                "<5Q", source_id, epoch, self.source_revision, self.first, len(self.columns[0])
            )
        )
        for tag, predicates in ((1, self.base), (0, clauses)):
            h.update(bytes([tag]))
            h.update(struct.pack("<Q", len(predicates)))
            for (ident, dim), bounds in sorted(predicates.items()):
                h.update(struct.pack("<QQ2d", ident, dim, *(0.0 if v == 0 else v for v in bounds)))
        h.update(struct.pack("<Q", len(self.mask)))
        h.update(
            hashlib.blake2s(self.mask, digest_size=8, person=b"xyfmsk01").digest()
            if self.mask
            else bytes(8)
        )
        assert reply["filter_hash"] == int.from_bytes(h.digest(), "little")
        self.last_hash = reply["filter_hash"]
        assert reply["has_intent"] == bool(clauses or self.base or self.mask)
        selected = [
            (
                not self.mask
                or (row // 8 < len(self.mask) and self.mask[row // 8] & (1 << (row % 8)))
            )
            and all(
                math.isfinite(self.columns[d][row]) and lo <= self.columns[d][row] <= hi
                for (_, d), (lo, hi) in {**self.base, **clauses}.items()
            )
            for row in range(len(self.columns[0]))
        ]
        if op == 9:
            first, n, _ = args
            bits = bytearray((n + 7) // 8)
            total = 0
            for i in range(n):
                if selected[first - self.first + i]:
                    bits[i // 8] |= 1 << (i % 8)
                    total += 1
            assert reply["membership"] == bits
            assert reply["selected_count"] == total
        if op not in (5, 7, 11):
            return
        assert reply["selected_count"] == sum(bool(v) for v in selected)
        if reply["tier"] == 3:
            assert reply["rows_read"] == 0 and reply["fallback"] == 0
        for v, actual in zip(self.views, reply["views"], strict=True):
            ident, x, y, w, hh, (x0, x1, y0, y1), colors = v
            totals, counts = [0] * (w * hh), [0] * (w * hh)
            # Explicit disjoint interval tests; no production floor/bin helper.
            for row, (xx, yy) in enumerate(zip(self.columns[x], self.columns[y], strict=True)):
                if not math.isfinite(xx) or not math.isfinite(yy):
                    continue
                for cy in range(hh):
                    if y0 + (y1 - y0) * cy / hh <= yy < y0 + (y1 - y0) * (cy + 1) / hh:
                        for cx in range(w):
                            if x0 + (x1 - x0) * cx / w <= xx < x0 + (x1 - x0) * (cx + 1) / w:
                                totals[cy * w + cx] += 1
                                counts[cy * w + cx] += bool(selected[row])
            assert actual["id"] == ident and actual["counts"] == tuple(counts)
            if op == 11:
                plane = next(p for p in reply["density"] if p["id"] == ident)
                assert plane["totals"] == tuple(totals) and plane["selected"] == tuple(counts)
                assert plane["width"] == w and plane["height"] == hh
                assert plane["x_range"] + plane["y_range"] == [x0, x1, y0, y1]
                expected_grid = [float(v) for v in totals]
                assert list(plane["grid"]) == expected_grid
                rgba = bytearray(w * hh * 4)
                filtered = bool(clauses or self.base or self.mask)
                maximum = max(totals, default=0)
                assert plane["maximum"] == maximum
                for cell, total in enumerate(totals):
                    at = cell * 4
                    alpha = int(
                        min(1, total / (maximum or 1) * 1.35) * (255 if filtered else colors[3])
                    )
                    ratio = counts[cell] / total if total else 0
                    rgb = (
                        [
                            int(colors[i] * (1 - ratio) + colors[4 + i] * ratio + 0.5)
                            for i in range(3)
                        ]
                        if filtered
                        else colors[:3]
                    )
                    if filtered:
                        alpha = int(
                            alpha * ((1 - ratio) * 0.18 * colors[3] / 255 + ratio * colors[7] / 255)
                            + 0.5
                        )
                    rgba[at : at + 4] = bytes([*rgb, alpha])
                assert plane["rgba"] == rgba
