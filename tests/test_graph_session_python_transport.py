"""Private S6 transport proof against the real ABI 398, with test-only codecs."""

from __future__ import annotations

import ctypes as ct
import itertools
import os
import subprocess
import sys
import threading
from array import array

import pytest

from xyg import _graph_session as transport
from xyg import _native
from xyg._graph_session import GraphSession, GraphSessionError
from xyg._graph_session import GraphSessionStatus as Status
from xyg._graphforge_container import DTYPE as D
from xyg._graphforge_container import decode_container, encode_container

_INSTANCES = itertools.count(0x5059544800000000)


def _document() -> bytes:
    return encode_container(
        "XYGF",
        [
            ("status", 0, D.U32, [0]),
            ("kind", 0, D.UTF8, "graph"),
            ("composition.version", 0, D.U32, [2]),
            ("node.uuid", 0, D.UUID, bytes([1]) * 16 + bytes([2]) * 16),
            ("edge.uuid", 0, D.UUID, bytes([11]) * 16),
            ("edge.derived", 0, D.U8, [0]),
            ("edge.layer", 0, D.U32, [0xFFFFFFFF]),
            ("edge.order", 0, D.I64, [-1]),
            ("edge.path", 0, D.U64, [0xFFFFFFFFFFFFFFFF]),
            ("edge.source", 0, D.U64, [0]),
            ("edge.target", 0, D.U64, [1]),
            ("node.label", 0, D.TEXTS, ["private-label", "second"]),
        ],
    )


def _request(instance, seq, op, rev=0, extra=(), group=9) -> bytes:
    return encode_container(
        "XYGI",
        [
            ("header.u64", 0, D.U64, [instance, group, seq]),
            ("header.u32", 0, D.U32, [rev, op, 0, 0, 0, 0, 0, 0, 0]),
            *extra,
        ],
    )


def _load(document=None, x=(0.0, 40.0)):
    return [
        ("document.bytes", 0, D.BYTES, _document() if document is None else document),
        ("load.x.f64", 0, D.F64, x),
        ("load.y.f64", 0, D.F64, [0.0, 0.0]),
    ]


def _open(instance, **kwargs):
    document = _document()
    return GraphSession(
        document,
        _request(instance, 1, 19, extra=_load()),
        instance_id=instance,
        group_id=9,
        **kwargs,
    )


def _decode(reply):
    result = decode_container(reply, "XYGR")
    assert list(result["status.u32", 0]) == [0]
    return result


def _revision(reply):
    return int(_decode(reply)["header.u32", 0][0])


@pytest.fixture
def session():
    instance = next(_INSTANCES)
    with _open(instance) as handle:
        yield handle, instance


def test_native_398_create_render_update_and_replay(session) -> None:
    assert _native._lib.xyg_abi_version() == 398
    handle, instance = session
    request = _request(instance, 2, 21)
    before = handle.render(request)
    result = _decode(before)
    assert any(name.startswith("render.") for name, index in result)
    assert handle.render(request) == before
    update = _request(instance, 3, 20, _revision(before), _load(x=(10.0, 50.0)))
    updated = handle.update(update)
    assert _revision(updated) == _revision(before) + 1
    assert handle.update(update) == updated


@pytest.mark.parametrize(
    ("method", "symbol", "operation"),
    [
        ("render", "xyg_graphforge_session_render", 21),
        ("interact", "xyg_graphforge_session_interact", 10),
        ("poll_event", "xyg_graphforge_session_poll_event", 22),
    ],
)
def test_real_query_short_exact_replay_retains_complete_bytes(
    session, monkeypatch, method, symbol, operation
) -> None:
    handle, instance = session
    rendered = handle.render(_request(instance, 2, 21))
    revision = _revision(rendered)
    selected = handle.interact(
        _request(instance, 3, 10, revision, [("uuids.uuid", 0, D.UUID, bytes([1]) * 16)])
    )
    extra = [("uuids.uuid", 0, D.UUID, bytes([2]) * 16)] if operation == 10 else []
    request = bytearray(_request(instance, 4, operation, _revision(selected), extra))
    expected_input = bytes(request)
    native = getattr(_native._lib, symbol)
    observed = []
    retained = []

    def inspect(handle, data, length, out, capacity, out_length):
        observed.append((ct.string_at(data, length), ct.addressof(data), capacity))
        status = native(handle, data, length, out, capacity, out_length)
        if capacity == 0:
            assert status == Status.CAPACITY
            size = ct.cast(out_length, ct.POINTER(ct.c_size_t))[0]
            assert size > 0
            short = (ct.c_uint8 * size)(*([0xA5] * size))
            required = ct.c_size_t()
            assert native(handle, data, length, short, size - 1, ct.byref(required)) == -5
            assert required.value == size
            assert bytes(short) == b"\xa5" * size
            exact = (ct.c_uint8 * size)()
            assert native(handle, data, length, exact, size, ct.byref(required)) == 0
            assert required.value == size
            retained.append(bytes(exact))
            request[:] = b"\x00" * len(request)  # caller mutation cannot rewrite the retry
        return status

    with monkeypatch.context() as patch:
        patch.setattr(_native._lib, symbol, inspect)
        reply = getattr(handle, method)(request)
    assert reply == retained[0]
    assert [item[0] for item in observed] == [expected_input, expected_input]
    assert observed[0][1] == observed[1][1]
    assert [item[2] for item in observed] == [0, len(reply)]
    assert getattr(handle, method)(expected_input) == reply
    result = _decode(reply)
    if operation == 22:
        assert ("outbound.bytes", 0) in result
        empty = _decode(handle.poll_event(_request(instance, 5, 22, revision)))
        assert ("outbound.bytes", 0) not in empty


def test_native_rejections_preserve_success_cache_and_sequence(session) -> None:
    handle, instance = session
    request = _request(instance, 2, 21)
    before = handle.render(request)
    revision = _revision(before)
    cases = [
        (handle.interact, _request(instance, 3, 4, revision + 1), Status.STALE),
        (handle.render, _request(instance + 1, 3, 21), Status.INVALID),
        (handle.render, _request(instance, 3, 21, group=10), Status.INVALID),
        (handle.interact, b"private-invalid-wire", Status.INVALID),
        (handle.render, _request(instance, 2, 21, revision + 1), Status.INVALID),
        (handle.render, _request(instance, 1, 21), Status.INVALID),
        (handle.update, _request(instance, 3, 21), Status.INVALID),
        (handle.bind_temporal, _request(instance, 3, 21), Status.INVALID),
        (handle.unbind_temporal, _request(instance, 3, 21), Status.INVALID),
        (handle.coordinate_deliver, _request(instance, 3, 21), Status.INVALID),
    ]
    for method, invalid, status in cases:
        with pytest.raises(GraphSessionError) as error:
            method(invalid)
        assert error.value.status == status
        assert str(error.value) == "native graph session request failed"
        assert handle.render(request) == before
    # Every refusal above leaves seq 3 available, and no Python counter intervenes.
    handle.interact(
        _request(instance, 3, 10, revision, [("uuids.uuid", 0, D.UUID, bytes([1]) * 16)])
    )


def test_independent_native_handles_and_lifetimes() -> None:
    first, second = next(_INSTANCES), next(_INSTANCES)
    with _open(first) as a, _open(second) as b:
        before_a = a.render(_request(first, 2, 21))
        before_b = b.render(_request(second, 2, 21))
        assert a._handle != b._handle
        selected = a.interact(
            _request(
                first, 3, 10, _revision(before_a), [("uuids.uuid", 0, D.UUID, bytes([1]) * 16)]
            )
        )
        assert list(_decode(selected)["node.flags.u32", 0]) != list(
            _decode(before_a)["node.flags.u32", 0]
        )
        assert list(_decode(before_b)["node.flags.u32", 0]) == list(
            _decode(before_a)["node.flags.u32", 0]
        )
        a.close()
        assert b.render(_request(second, 2, 21)) == before_b


def test_identical_native_open_alias_and_conflicting_open(session) -> None:
    handle, instance = session
    with _open(instance) as alias:
        assert alias._handle == handle._handle
        with pytest.raises(GraphSessionError) as error:
            GraphSession(
                _document(),
                _request(instance, 1, 19, extra=_load(x=(1.0, 2.0))),
                instance_id=instance,
                group_id=9,
            )
        assert error.value.status == Status.INVALID
    with pytest.raises(GraphSessionError) as error:
        handle.render(_request(instance, 2, 21))
    assert error.value.status == Status.UNBOUND
    handle.close()  # native Unbound is a successful local close


def test_bound_owner_disposal_is_observable_and_unbind_recovers(session) -> None:
    handle, instance = session
    nodes = [list(bytes([i]) * 16) for i in (1, 2)]
    edge = [list(bytes([11]) * 16)]
    projection = _native.graph_projection_create(nodes, edge, nodes[:1], nodes[1:])
    owner = _native.temporal_graph_create(projection)
    try:
        binding = _request(instance, 2, 18, extra=[("temporal.u64", 0, D.U64, [owner])])
        bound = handle.bind_temporal(binding)
        assert handle.bind_temporal(binding) == bound
        select = _request(
            instance, 3, 10, _revision(bound), [("uuids.uuid", 0, D.UUID, bytes([1]) * 16)]
        )
        selected = handle.interact(select)
        _native.temporal_graph_destroy(owner)
        owner = None
        for method, request in [
            (handle.interact, select),  # even a cached reply checks owner disposal
            (handle.render, _request(instance, 4, 21)),
            (handle.poll_event, _request(instance, 4, 22, _revision(selected))),
        ]:
            with pytest.raises(GraphSessionError) as error:
                method(request)
            assert error.value.status == Status.UNBOUND
        detached = handle.unbind_temporal(
            _request(instance, 4, 18, _revision(selected), [("temporal.u64", 0, D.U64, [0])])
        )
        assert _revision(handle.render(_request(instance, 5, 21))) >= _revision(detached)
    finally:
        if owner is not None:
            _native.temporal_graph_destroy(owner)
        _native.graph_projection_destroy(projection)


@pytest.mark.parametrize("alias_close", [False, True])
def test_close_waits_for_complete_query_copy_transaction(session, monkeypatch, alias_close) -> None:
    handle, instance = session
    closer = _open(instance) if alias_close else handle
    queried, release, closing, destroyed = (threading.Event() for _ in range(4))
    events, results, errors = [], [], []
    native_render = _native._lib.xyg_graphforge_session_render
    native_destroy = _native._lib.xyg_graphforge_session_destroy

    def render(*args):
        status = native_render(*args)
        if args[4] == 0:
            events.append("query")
            queried.set()
            assert release.wait(5)
        else:
            events.append("copy")
        return status

    def destroy(*args):
        events.append("destroy")
        destroyed.set()
        return native_destroy(*args)

    def operation():
        try:
            results.append(handle.render(_request(instance, 2, 21)))
        except BaseException as error:
            errors.append(error)

    def close():
        closing.set()
        try:
            closer.close()
        except BaseException as error:
            errors.append(error)

    monkeypatch.setattr(_native._lib, "xyg_graphforge_session_render", render)
    monkeypatch.setattr(_native._lib, "xyg_graphforge_session_destroy", destroy)
    worker, closing_worker = threading.Thread(target=operation), threading.Thread(target=close)
    worker.start()
    try:
        assert queried.wait(5)
        closing_worker.start()
        assert closing.wait(5)
        assert not destroyed.is_set()
    finally:
        release.set()
        worker.join(5)
        if closing_worker.ident is not None:
            closing_worker.join(5)
    assert not worker.is_alive() and not closing_worker.is_alive()
    assert not errors
    assert events == ["query", "copy", "destroy"]
    _decode(results[0])


def test_repeated_close_and_every_future_operation_refused_locally(session, monkeypatch) -> None:
    handle, instance = session
    handle.close()

    def unexpected(*args):
        pytest.fail("closed wrapper must not call native code")

    monkeypatch.setattr(_native._lib, "xyg_graphforge_session_destroy", unexpected)
    handle.close()
    for method in (
        handle.render,
        handle.update,
        handle.interact,
        handle.poll_event,
        handle.bind_temporal,
        handle.unbind_temporal,
        handle.coordinate_deliver,
    ):
        with pytest.raises(GraphSessionError, match=r"^graph session is closed$") as error:
            method(None)  # local closed check precedes buffer validation
        assert error.value.status is None
    with pytest.raises(GraphSessionError, match=r"^graph session is closed$"):
        handle.__enter__()


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        "private-text",
        [1, 2],
        42,
        memoryview(b"abcd")[::2],
        memoryview(array("I", [1])),
        memoryview(b"abcd").cast("B", (2, 2)),
    ],
)
def test_buffer_boundary_refuses_unsafe_inputs_before_native(session, monkeypatch, invalid) -> None:
    handle, instance = session

    def unexpected(*args):
        pytest.fail("invalid host buffers must not call native code")

    monkeypatch.setattr(_native._lib, "xyg_graphforge_session_render", unexpected)
    with pytest.raises((TypeError, ValueError), match=r"^graph session input"):
        handle.render(invalid)


def test_released_buffer_and_host_bounds_are_value_free(session, monkeypatch) -> None:
    handle, instance = session
    view = memoryview(b"private-input")
    view.release()
    with pytest.raises(ValueError, match=r"^graph session input buffer is unavailable$"):
        handle.render(view)
    monkeypatch.setattr(transport, "_MAX_BUFFER", 1)
    with pytest.raises(ValueError, match=r"^graph session input exceeds host buffer bounds$"):
        handle.render(b"private-input")


@pytest.mark.parametrize("invalid", [True, -1, 1 << 64, 1.5, "private-identity"])
@pytest.mark.parametrize("field", ["instance_id", "group_id"])
def test_create_scalar_bounds_before_native(monkeypatch, invalid, field) -> None:
    def unexpected(*args):
        pytest.fail("invalid host scalars must not call native code")

    monkeypatch.setattr(_native._lib, "xyg_graphforge_session_create", unexpected)
    kwargs = {"instance_id": next(_INSTANCES), "group_id": 9, field: invalid}
    with pytest.raises((TypeError, ValueError), match=r"^graph session identity must be"):
        GraphSession(b"", b"", **kwargs)


def test_byte_views_accepted_and_invalid_wire_left_to_rust(session) -> None:
    handle, instance = session
    request = _request(instance, 2, 21)
    assert handle.render(memoryview(request)) == handle.render(bytearray(request))
    with pytest.raises(GraphSessionError) as error:
        handle.render(b"")
    assert error.value.status == Status.INVALID


@pytest.mark.parametrize("field", ["instance_id", "group_id", "document", "opening"])
def test_constructor_input_callbacks_can_close_and_open_native_sessions(field) -> None:
    if field in {"document", "opening"} and sys.version_info < (3, 12):
        pytest.skip("Python buffer callbacks require Python 3.12")
    code = """
import runpy
import sys
from xyg import _native
from xyg._graph_session import GraphSession, GraphSessionError

helpers = runpy.run_path('tests/test_graph_session_python_transport.py')
open_session, request = helpers['_open'], helpers['_request']
assert _native._lib.xyg_abi_version() == 398
instance = 0x505954485245454E
callbacks = []

with open_session(instance + 1) as peer:
    def reenter():
        peer.close()
        with open_session(instance + 2) as nested:
            helpers['_decode'](nested.render(request(instance + 2, 2, 21)))
        callbacks.append('closed/opened/rendered')

    class Scalar:
        def __init__(self, value):
            self.value = value
        def __index__(self):
            reenter()
            return self.value

    class Buffer(bytes):
        def __buffer__(self, flags):
            reenter()
            return memoryview(bytes(self))

    document = helpers['_document']()
    opening = request(instance, 1, 19, extra=helpers['_load']())
    values = dict(document=document, opening=opening, instance_id=instance, group_id=9)
    field = sys.argv[1]
    values[field] = Scalar(values[field]) if field.endswith('_id') else Buffer(values[field])
    with GraphSession(**values) as session:
        helpers['_decode'](session.render(request(instance, 2, 21)))
    assert callbacks == ['closed/opened/rendered']
    try:
        peer.render(request(instance + 1, 2, 21))
    except GraphSessionError as error:
        assert error.status is None and str(error) == 'graph session is closed'
    else:
        raise AssertionError('peer closure was lost')
print('native398: constructor callback completed')
"""
    # subprocess.run kills and reaps the child on timeout, so the regression
    # cannot strand a thread holding the module lock in the pytest process.
    result = subprocess.run(
        [sys.executable, "-c", code, field],
        capture_output=True,
        text=True,
        timeout=8,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "native398: constructor callback completed"


@pytest.mark.skipif(
    sys.version_info < (3, 12), reason="Python buffer callbacks require Python 3.12"
)
@pytest.mark.parametrize("close_target", [False, True])
def test_command_buffer_callback_reenters_and_rechecks_native_lifetime(close_target) -> None:
    code = """
import runpy
import sys
from xyg import _native
from xyg._graph_session import GraphSessionError

helpers = runpy.run_path('tests/test_graph_session_python_transport.py')
open_session, request = helpers['_open'], helpers['_request']
assert _native._lib.xyg_abi_version() == 398
instance = 0x505954485245434D
close_target = sys.argv[1] == 'True'
callbacks = []

with open_session(instance) as session, open_session(instance + 1) as peer:
    class Buffer(bytearray):
        def __buffer__(self, flags):
            (session if close_target else peer).close()
            with open_session(instance + 2) as nested:
                helpers['_decode'](nested.render(request(instance + 2, 2, 21)))
            callbacks.append('closed/opened/rendered')
            return memoryview(original)

    original = request(instance, 2, 21)
    if close_target:
        try:
            session.render(Buffer(original))
        except GraphSessionError as error:
            assert error.status is None and str(error) == 'graph session is closed'
        else:
            raise AssertionError('command used a handle closed during its snapshot')
    else:
        reply = session.render(Buffer(original))
        helpers['_decode'](reply)
        assert session.render(original) == reply
    assert callbacks == ['closed/opened/rendered']
print('native398: command callback completed')
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(close_target)],
        capture_output=True,
        text=True,
        timeout=8,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "native398: command callback completed"


def test_private_import_does_not_load_widget_stack_or_export_public_api() -> None:
    code = """
import sys
import xyg
from xyg._graph_session import GraphSession
assert not hasattr(xyg, 'GraphSession')
assert not any(name in sys.modules for name in (
    'xyg.widget', 'anywidget', 'ipywidgets', 'IPython', 'traitlets',
    'xyg.graph_layout', 'xyg.channel',
))
"""
    subprocess.run([sys.executable, "-c", code], env=os.environ.copy(), check=True, timeout=20)
