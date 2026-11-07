"""Consumer hosts must not reuse a port released by an earlier allocation."""

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def smoke(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "consumer_port_test", root / "scripts/consumer_apps_smoke.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sockets(monkeypatch, smoke, *, fail_bind=None):
    active, opened = set(), []

    class Socket:
        def __init__(self):
            self.port = None
            self.closed = False
            opened.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.closed = True
            active.discard(self.port)

        def bind(self, address):
            assert address == ("127.0.0.1", 0)
            if len(active) == fail_bind:
                raise OSError("bind failed")
            # A valid OS allocator can immediately recycle any released port.
            self.port = next(port for port in range(50000, 50010) if port not in active)
            active.add(self.port)

        def getsockname(self):
            return ("127.0.0.1", self.port)

    monkeypatch.setattr(smoke.socket, "socket", Socket)
    return active, opened


def test_consumer_hosts_allocate_distinct_ports_and_release_them(smoke, monkeypatch):
    active, opened = sockets(monkeypatch, smoke)
    ports = smoke.free_ports(4)
    assert len(ports) == len(set(ports)) == 4
    assert not active
    assert len(opened) == 4 and all(sock.closed for sock in opened)


def test_partial_port_allocation_closes_every_socket(smoke, monkeypatch):
    active, opened = sockets(monkeypatch, smoke, fail_bind=2)
    with pytest.raises(OSError, match="bind failed"):
        smoke.free_ports(4)
    assert not active
    assert len(opened) == 4 and all(sock.closed for sock in opened)
