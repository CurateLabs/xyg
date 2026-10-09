"""Actual native allocation replay and asynchronous attempt ownership."""

import asyncio

import numpy as np
import pytest

from test_geo_selected_hierarchy import setup
from xyg import _geoscale as g


@pytest.mark.parametrize("failure", ["lost", "corrupt"])
def test_exact_nonce_recovery_and_lost_disposal(monkeypatch, failure):
    source, original, scope, selected, query, issue = setup()
    execute = g.execute
    input_ids = np.array([2**64 - 1], dtype="<u8")
    attempt = scope.begin_state(revision=2, ids=input_ids, fill=b"\0\xff\0\xff")
    input_ids[:] = 1
    handles = []
    fail = True

    def intercept(request):
        nonlocal fail
        raw = execute(request)
        if int.from_bytes(request[8:12], "little") == 33:
            handles.append(int.from_bytes(raw[16:24], "little"))
            if fail:
                fail = False
                if failure == "lost":
                    raise RuntimeError("lost33")
                return b"bad!" + raw[4:]
        return raw

    monkeypatch.setattr(g, "execute", intercept)
    try:
        with pytest.raises((RuntimeError, ValueError)):
            attempt.recover()
        state = attempt.recover()
        assert handles == [state.handle, state.handle]
        reject = True

        def disposal(request):
            nonlocal reject
            raw = execute(request)
            if int.from_bytes(request[8:12], "little") == 10 and reject:
                reject = False
                raise RuntimeError("lost10")
            return raw

        monkeypatch.setattr(g, "execute", disposal)
        with pytest.raises(RuntimeError):
            attempt.close()
        attempt.close()
        assert not state._live
        attempt.close()
    finally:
        monkeypatch.setattr(g, "execute", execute)
        attempt.close()
        selected.close()
        original.close()
        source.close()
        scope.close()


def test_async_repeated_cancel_recover_and_cleanup_settle():
    async def run():
        source, original, scope, selected, query, issue = setup()
        entered, release = asyncio.Event(), asyncio.Event()

        class Bridge:
            async def execute(self, request):
                raw = g.execute(request)
                if int.from_bytes(request[8:12], "little") == 33:
                    entered.set()
                    await release.wait()
                return raw

        from xyg._geo_selected import _AUTHORITY, GeoSelectedScope

        async_scope = GeoSelectedScope(scope.handle, Bridge(), _token=_AUTHORITY)
        async_scope.budget = scope.budget
        attempt = async_scope.begin_state(
            revision=2, ids=np.array([2**64 - 1], dtype="<u8"), fill=b"\0\xff\0\xff"
        )
        try:
            task = asyncio.create_task(attempt.recover_async())
            await entered.wait()
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            state = await attempt.recover_async()
            await asyncio.gather(attempt.aclose(), attempt.aclose())
            assert not state._live
        finally:
            release.set()
            await attempt.aclose()
            selected.close()
            original.close()
            source.close()
            scope.close()

    asyncio.run(run())


def test_async_delayed_allocation_keeps_captured_producer_when_scope_is_edited():
    async def run():
        from xyg._geo_selected import _AUTHORITY, GeoSelectedScope, claim_selected_state

        source, original, scope, selected, query, issue = setup()
        entered, release = asyncio.Event(), asyncio.Event()
        foreign_calls = 0

        class Original:
            async def execute(self, request):
                raw = g.execute(request)
                if int.from_bytes(request[8:12], "little") == 33:
                    entered.set()
                    await release.wait()
                return raw

        class Foreign:
            async def execute(self, request):
                nonlocal foreign_calls
                foreign_calls += 1
                return g.execute(request)

        producer, foreign = Original(), Foreign()
        async_scope = GeoSelectedScope(scope.handle, producer, _token=_AUTHORITY)
        async_scope.budget = scope.budget
        attempt = async_scope.begin_state(
            revision=2, ids=np.array([2**64 - 1], dtype="<u8"), fill=b"\0\xff\0\xff"
        )
        try:
            task = asyncio.create_task(attempt.recover_async())
            await entered.wait()
            async_scope._bridge = foreign
            release.set()
            state = await task
            assert state._bridge is producer
            claim = claim_selected_state(state, producer)
            claim.reject()
            with pytest.raises(TypeError):
                claim_selected_state(state, foreign)
            await attempt.aclose()
            assert foreign_calls == 0
        finally:
            release.set()
            await attempt.aclose()
            selected.close()
            original.close()
            source.close()
            scope.close()

    asyncio.run(run())


@pytest.mark.parametrize("status", [-1, -9])
def test_native_status_after_allocation_uncertain_only_when_not_proven_atomic(monkeypatch, status):
    from xyg._native import GeoNativeError

    source, original, scope, selected, query, issue = setup()
    execute = g.execute
    attempt = scope.begin_state(
        revision=2, ids=np.array([2**64 - 1], dtype="<u8"), fill=b"\0\xff\0\xff"
    )
    failed = False
    calls = 0

    def intercept(request):
        nonlocal failed, calls
        if int.from_bytes(request[8:12], "little") == 33:
            calls += 1
            if not failed:
                failed = True
                # -9 is a genuine pre-execute admission failure; -1 may be a
                # post-mutation panic and cannot prove allocation absence.
                if status == -1:
                    execute(request)
                raise GeoNativeError(status)
        return execute(request)

    monkeypatch.setattr(g, "execute", intercept)
    try:
        with pytest.raises(GeoNativeError):
            attempt.recover()
        if status == -1:
            state = attempt.recover()
            assert state.handle
            assert calls == 2
        attempt.close()
        if status == -9:
            assert calls == 1
    finally:
        monkeypatch.setattr(g, "execute", execute)
        attempt.close()
        selected.close()
        original.close()
        source.close()
        scope.close()
