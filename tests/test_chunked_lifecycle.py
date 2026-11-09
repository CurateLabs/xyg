"""Adversarial native ownership and loop ingress; no replacement renderer or oracle."""

from __future__ import annotations

import asyncio
import ctypes
import os
import struct
import sys
import threading

import pytest

from test_chunked_columns import _artifact_with_overview
from xyg import ChunkedColumns, _native


def mounted(path, *, budget=512, page=512):
    source = ChunkedColumns(path)
    chart = source.chart(max_points=2, budget_bytes=budget, page_bytes=page)
    widget = chart.widget()
    source.close()
    messages = asyncio.Queue()
    widget.send = lambda message, buffers=None: messages.put_nowait((message, buffers))
    widget._chunked_binding.message(dict(type="chunked_mount", mount="A", mount_epoch="1"))
    return chart, widget, messages


def navigate(widget, intent, x=(30, 40)):
    widget._on_custom_msg(
        widget,
        dict(
            type="view_change",
            mount="A",
            chunked_intent=str(intent),
            ranges={"x": list(x), "y": [-1, 6]},
        ),
        [],
    )


def receipt(widget, message, *, kind="chunked_painted", mount="A"):
    widget._chunked_binding.message(
        dict(
            type=kind,
            mount=mount,
            intent=message["intent"],
            frame=message["spec"]["chunked"]["frame"],
        )
    )


@pytest.mark.parametrize("failure", ["budget", "partial", "corrupt"])
def test_storage_failure_keeps_accepted_frame_and_settles_waiters(tmp_path, failure):
    async def run():
        path = tmp_path / "source.xygc"
        _artifact_with_overview(path, [(float(i), float(i % 5)) for i in range(64)])
        _, w, messages = mounted(path)
        try:
            navigate(w, 1)
            good, _ = await asyncio.wait_for(messages.get(), 5)
            receipt(w, good)
            await w.when_idle()
            accepted = w._figure
            if failure != "budget":
                with path.open("r+b") as f:
                    offset = 64 + 16 * 48
                    if failure == "partial":
                        f.truncate(offset + 3)
                    else:
                        f.seek(offset)
                        f.write(struct.pack("<d", 99.0))
            navigate(w, 2, (0, 63) if failure == "budget" else (0, 3))
            waiter = asyncio.create_task(w.when_idle())
            error, _ = await asyncio.wait_for(messages.get(), 5)
            assert error["type"] == "chunked_error"
            with pytest.raises(RuntimeError):
                await waiter
            assert w._figure is accepted
            assert list(w.source_row_ids) == list(range(30, 41))
            report = w._chunked_binding.memory_report()
            assert (
                report["host_retained_capacity_bytes"] <= report["host_typed_capacity_bound_bytes"]
            )
        finally:
            w.close()

    asyncio.run(run())


def test_cross_thread_cross_loop_latest_intent_and_stage_protocol(tmp_path):
    async def run():
        path = tmp_path / "source.xygc"
        _artifact_with_overview(path, [(float(i), float(i % 5)) for i in range(64)])
        _, w, messages = mounted(path)
        binding = w._chunked_binding
        started, release = threading.Event(), threading.Event()
        original = _native.chunked_columns_chart
        outcomes = []

        def blocked(*args, **kwargs):
            started.set()
            release.wait(5)
            try:
                return original(*args, **kwargs)
            except ValueError as e:
                outcomes.append(str(e))
                raise

        try:
            with pytest.MonkeyPatch.context() as monkey:
                monkey.setattr(_native, "chunked_columns_chart", blocked)
                navigate(w, 1, (10, 20))
                assert await asyncio.to_thread(started.wait, 5)
                previous = binding.generation
                # IPykernel can deliver comms on a thread with no running loop.
                await asyncio.to_thread(navigate, w, 2, (30, 40))
                assert binding.generation == previous + 1

                # A second independent foreign loop must still publish on the owner.
                def foreign():
                    async def send():
                        navigate(w, 3, (35, 45))

                    asyncio.run(send())

                await asyncio.to_thread(foreign)
                assert len(binding.controls) <= 16 and binding.pending[2] == "3"
                release.set()
                frame, _ = await asyncio.wait_for(messages.get(), 5)
            assert frame["intent"] == "3" and outcomes and "cancelled" in outcomes[0]
            waiter = asyncio.create_task(w.when_idle())
            await asyncio.sleep(0)
            receipt(w, frame, mount="retired")
            await asyncio.sleep(0)
            assert not waiter.done()
            receipt(w, frame, kind="chunked_rejected")
            with pytest.raises(RuntimeError, match="rejected"):
                await waiter
            assert w._figure is binding.initial_figure
            navigate(w, 4, (30, 40))
            frame, _ = await asyncio.wait_for(messages.get(), 5)
            receipt(w, frame)
            await w.when_idle()
            assert list(w.source_row_ids) == list(range(30, 41))
            # Superseding a mount cancels and rejects all old ACKs/unsubscribes.
            binding.message(dict(type="chunked_mount", mount="B", mount_epoch="2"))
            receipt(w, frame)
            binding.message(dict(type="chunked_unmount", mount="A"))
            await asyncio.sleep(0)
            assert binding.mount == "B" and w._figure is binding.initial_figure
            assert list(w.source_row_ids) == [0, 63]
            assert w.spec["chunked"]["frame"] == binding.initial_figure._chunked_generation
        finally:
            release.set()
            w.close()

    asyncio.run(run())


def test_source_claim_rollback_rebind_and_waiter_teardown(tmp_path, monkeypatch):
    async def run():
        path = tmp_path / "source.xygc"
        _artifact_with_overview(path, [(float(i), float(i % 5)) for i in range(64)])
        with ChunkedColumns(path) as source:
            chart = source.chart(max_points=2)
            original = _native.chunked_columns_open
            with monkeypatch.context() as patch:
                patch.setattr(
                    _native,
                    "chunked_columns_open",
                    lambda *_: (_ for _ in ()).throw(ValueError("missing artifact")),
                )
                with pytest.raises(ValueError):
                    chart.widget()
            assert source.overview()[0].size > 0
            w = chart.widget()
            other = source.chart().widget()
        try:
            assert w._chunked_binding.handle != other._chunked_binding.handle
            w._chunked_binding.message(dict(type="chunked_mount", mount="A", mount_epoch="1"))
            navigate(w, 1)
            waiter = asyncio.create_task(w.when_idle())
            await asyncio.sleep(0)
            cancelled = asyncio.create_task(w.when_idle())
            await asyncio.sleep(0)
            cancelled.cancel()
            with pytest.raises(asyncio.CancelledError):
                await cancelled
            w.close()
            with pytest.raises(asyncio.CancelledError):
                await waiter
            replacement = chart.widget()
            assert replacement is not w and replacement._chunked_binding.handle
            replacement.close()
            assert other._chunked_binding.handle
            assert original is _native.chunked_columns_open
        finally:
            w.close()
            other.close()

    asyncio.run(run())


@pytest.mark.skipif(
    sys.platform != "linux", reason="inotify observes actual positioned reads on Linux"
)
def test_close_cancels_actual_arc_held_native_read(tmp_path, monkeypatch):
    async def run():
        path = tmp_path / "many-chunks.xygc"
        _artifact_with_overview(
            path,
            [(float(i), float(i % 5)) for i in range(262144)],
            chunk_rows=1,
            overview_indices=range(0, 262144, 128),
        )
        _, w, _ = mounted(path, budget=4 << 20, page=64 << 10)
        libc = ctypes.CDLL(None, use_errno=True)
        fd = libc.inotify_init1(os.O_CLOEXEC)
        assert fd >= 0
        assert (
            libc.inotify_add_watch(fd, os.fsencode(path), 1) >= 0
        )  # IN_ACCESS, after open/overview
        original = _native.chunked_columns_chart
        outcomes = []

        def observe(*args, **kwargs):
            try:
                return original(*args, **kwargs)
            except ValueError as error:
                outcomes.append(str(error))
                raise

        try:
            monkeypatch.setattr(_native, "chunked_columns_chart", observe)
            navigate(w, 1, (0, 262143))
            event = await asyncio.wait_for(asyncio.to_thread(os.read, fd, 4096), 5)
            assert event and w._chunked_binding.reading
            w.close()
            assert outcomes and "cancelled" in outcomes[0]
            assert not w._chunked_binding.thread.is_alive() and w._chunked_binding.handle == 0
        finally:
            os.close(fd)
            w.close()

    asyncio.run(run())


def test_rejected_superseded_stage_does_not_fail_latest_waiter(tmp_path):
    async def run():
        path = tmp_path / "source.xygc"
        _artifact_with_overview(path, [(float(i), float(i % 5)) for i in range(64)])
        _, w, messages = mounted(path)
        try:
            navigate(w, 1, (10, 20))
            old, _ = await asyncio.wait_for(messages.get(), 5)
            navigate(w, 2, (30, 40))
            waiter = asyncio.create_task(w.when_idle())
            receipt(w, old, kind="chunked_rejected")
            latest, _ = await asyncio.wait_for(messages.get(), 5)
            assert latest["intent"] == "2"
            receipt(w, latest)
            await waiter
            assert list(w.source_row_ids) == list(range(30, 41))
        finally:
            w.close()

    asyncio.run(run())
