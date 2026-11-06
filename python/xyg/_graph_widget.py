"""Retained native scheduling for the default property-graph notebook view.

The worker owns the native session. The kernel only dispatches opaque requests;
one outstanding frame request provides comm backpressure.
"""

from __future__ import annotations

import asyncio
import secrets
from concurrent.futures import ThreadPoolExecutor

import anywidget
import numpy as np
import traitlets

from ._graph_session import GraphSession
from ._graphforge_container import DTYPE as D
from ._graphforge_container import encode_container
from .widget import _STATIC


class GraphWidget(anywidget.AnyWidget):
    _esm = _STATIC / "index.js"
    spec = traitlets.Dict().tag(sync=True)
    buffers = traitlets.Any().tag(sync=True)

    def __init__(self, document, *, width=800, height=500, **kwargs):
        self._document = document
        self._instance = secrets.randbits(64) or 1
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="xyg-graph")
        self._session = None  # accessed only on the worker
        self._epoch = None
        self._closed = False
        self._busy = False
        self._pending = None
        super().__init__(
            spec={
                "graph_host": True,
                "instance": str(self._instance),
                "width": width,
                "height": height,
            },
            buffers=[],
            **kwargs,
        )
        self.on_msg(self._message)

    def _retire(self):
        if self._session is not None:
            self._session.close()
            self._session = None

    def _execute(self, operation, packet):
        if operation == "mount":
            self._retire()
            opening = encode_container(
                "XYGI",
                [
                    ("header.u64", 0, D.U64, np.array([self._instance, 0, 1], dtype="<u8")),
                    ("header.u32", 0, D.U32, [0, 19, 0, 0, 0, 0, 0, 0, 0]),
                    ("document.bytes", 0, D.BYTES, self._document),
                    ("load.progressive.u8", 0, D.U8, [1]),
                ],
            )
            self._session = GraphSession(
                self._document, opening, instance_id=self._instance, group_id=0
            )
            return None
        if self._session is None:
            raise RuntimeError("graph widget has no mounted session")
        if operation == "render":
            return self._session.render(packet)
        return self._session.interact(packet)

    def _message(self, widget, content, buffers):
        if self._closed or not isinstance(content, dict):
            return
        operation, epoch = content.get("operation"), content.get("epoch")
        if not isinstance(epoch, str) or not 0 < len(epoch) <= 64:
            return
        if operation == "dispose":
            if epoch == self._epoch:
                self._epoch = None
                self._executor.submit(self._retire)
            return
        if operation == "mount":
            if epoch == self._epoch:
                return
            if self._pending is not None:
                self._pending.cancel()
            self._epoch = epoch
            self._busy = False
        elif epoch != self._epoch or self._busy:
            return
        if operation not in ("mount", "render", "step"):
            return
        if operation != "mount" and len(buffers) != 1:
            return
        loop = asyncio.get_running_loop()
        packet = None if operation == "mount" else bytes(buffers[0])
        self._busy = True
        future = self._executor.submit(self._execute, operation, packet)
        self._pending = future

        def deliver():
            if self._closed or self._epoch != epoch:
                return
            self._busy = False
            try:
                result = future.result()
            except Exception:
                self._epoch = None
                self._executor.submit(self._retire)
                self.send(
                    {"type": "graph_failed", "epoch": epoch, "code": "XYG_GRAPH_WORKER_FAILED"}
                )
                return
            self.send(
                {"type": "graph_reply", "epoch": epoch},
                buffers=[] if result is None else [result],
            )

        def completed(_):
            if not self._closed and not loop.is_closed():
                loop.call_soon_threadsafe(deliver)

        future.add_done_callback(completed)

    def close(self):
        if getattr(self, "_closed", True):
            return
        self._closed = True
        self._epoch = None
        if self._pending is not None:
            self._pending.cancel()
        self._executor.submit(self._retire)
        self._executor.shutdown(wait=False)
        super().close()
