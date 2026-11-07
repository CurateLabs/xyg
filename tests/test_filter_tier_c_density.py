"""Linked 2D public composition, complete packets, and independent scalar oracles."""

import math
import struct
import subprocess
import sys
from pathlib import Path

import pytest

import xyg
from filter_density_oracle import DensityOracle
from xyg import _native
from xyg.filter_session import FilterTierCError, decode_reply, execute_packet

FIXTURE = Path(__file__).parent / "fixtures/filter_tier_c/density.bin"


def test_linked_density_complete_packets_and_independent_oracles():
    stream = FIXTURE.read_bytes()
    at = 0
    oracle = DensityOracle()
    h = _native._lib.xyg_filter_session_new(1 << 20)
    try:
        while at < len(stream):
            n, cap, code, size, needed = struct.unpack_from("<IIiIQ", stream, at)
            at += 24
            packet = stream[at : at + n]
            at += n
            expected = stream[at : at + size]
            at += size
            if code:
                with pytest.raises(RuntimeError, match=f"required capacity {needed}"):
                    execute_packet(h, packet, cap)
                continue
            actual = execute_packet(h, packet, cap)
            assert actual == expected
            oracle.check(packet, decode_reply(actual))
    finally:
        _native._lib.xyg_filter_session_free(h)


def test_linked_density_fixture_current():
    subprocess.run([sys.executable, "scripts/gen_filter_density_fixture.py", "--check"], check=True)


@pytest.mark.parametrize("n", [0, 1, 13, 511])
def test_public_density_exact_boundaries_nonfinite_and_screen_storage(n):
    import random

    rng = random.Random(112)
    columns = {
        "a": [rng.random() * 4 - 2 for _ in range(n)],
        "b": [rng.random() * 4 - 2 for _ in range(n)],
    }
    if n > 12:
        columns["a"][:7] = [-0.0, 0.0, math.nan, math.inf, -math.inf, 1.0, -1.0]
    chart = xyg.scatter_chart(xyg.scatter(x=columns["a"], y=columns["b"], density=True))
    with chart.filter_session(columns, source_id=112, first_row=(1 << 64) - 1024) as s:
        s.configure_density(
            dict(id=1, dimension="a", cuts=[-1.0, 0.0, 1.0]),
            [dict(id=1, x="a", y="b", width=4, height=4, x_range=[-2.0, 2.0], y_range=[-2.0, 2.0])],
        )
        index = s.paint()["index_bytes"]
        assert index == (5 * 17 * 8 + 17 * 16 + 4 * 16)
        for lo, hi in [
            (-0.0, 0.0),
            (1.0, -1.0),
            (0.1, 0.6),
            (-3.0, 3.0),
            (4.0, 5.0),
            (math.nextafter(0.0, 1.0), 0.5),
            (-math.nextafter(0.0, 1.0), 0.0),
        ]:
            s.range(lo, hi, exact=True)
            result = s.paint(exact=True)
            assert result["index_bytes"] == index
            assert result["selected_count"] == sum(
                math.isfinite(v) and min(lo, hi) <= v <= max(lo, hi) for v in columns["a"]
            )
        for value in [math.nan, math.inf, -math.inf]:
            with pytest.raises(FilterTierCError, match="status 1"):
                s.range(value, 0.0, exact=True)
        s.evict()
        cleared = s.clear()
        assert cleared["tier"] == 2 and cleared["fallback"] == 4
        warm = s.paint()
        assert warm["selected_count"] == n and warm["tier"] == 3 and warm["fallback"] == 0


def test_u64_identity_and_refused_source_base_and_domain_changes_are_atomic():
    from xyg.filter_session import request

    maximum = (1 << 64) - 1
    chart = xyg.scatter_chart(xyg.scatter(x=[0.0, 1.0], y=[1.0, 0.0], density=True))
    with chart.filter_session(
        {"a": [0.0, 1.0], "b": [1.0, 0.0]}, source_id=maximum, epoch=maximum, first_row=maximum - 2
    ) as s:
        active = dict(id=maximum, dimension="a", cuts=[0.0, 1.0])
        views = [
            dict(
                id=maximum,
                x="a",
                y="b",
                width=2,
                height=2,
                x_range=[-1.0, 2.0],
                y_range=[-1.0, 2.0],
            )
        ]
        s.configure_density(active, views)
        s.range(0.0, 0.0)
        before = s.paint()
        assert before["source_id"] == before["epoch"] == maximum
        assert s.membership(maximum - 2, 2)["membership"] == b"\x01"
        for action in [
            lambda: s.base_filter(mask=b"\xff"),
            lambda: s.base_filter([dict(dimension="a", lo=math.inf, hi=1.0)]),
            lambda: s.configure_density(active, [dict(views[0], x_range=[1e300, 2e300])]),
        ]:
            with pytest.raises(FilterTierCError) as error:
                action()
            assert error.value.status == 1
            assert error.value.reply["filter_hash"] == before["filter_hash"]
        s.revision += 1
        bad = request(
            11,
            revision=s.revision,
            source_id=maximum,
            epoch=1,
            source_revision=s.source_revision,
            budget_bytes=s.budget_bytes,
        )
        refusal = decode_reply(execute_packet(s._handle, bad))
        assert refusal["status"] == 7 and refusal["filter_hash"] == before["filter_hash"]
        assert s.paint()["selected_count"] == 1


def test_explicit_transparent_selected_style_is_preserved_by_rust():
    chart = xyg.scatter_chart(xyg.scatter(x=[0.0, 1.0], y=[1.0, 0.0], density=True))
    with chart.filter_session({"a": [0.0, 1.0], "b": [1.0, 0.0]}, source_id=112) as s:
        active = dict(id=1, dimension="a", cuts=[0.0, 1.0])
        grid = dict(
            id=1,
            x="a",
            y="b",
            width=2,
            height=2,
            x_range=[-1.0, 2.0],
            y_range=[-1.0, 2.0],
            colors=[20, 30, 40, 255, 200, 100, 50, 0],
        )
        s.configure_density(active, [grid])
        s.range(-1.0, 2.0)
        result = s.paint()
        assert result["selected_count"] == 2
        assert all(alpha == 0 for alpha in result["density"][0]["rgba"][3::4])


def test_sixty_fifth_linked_clause_refuses_without_poisoning_accepted_state():
    columns = {"a": [0.0, 0.5, 1.0, 2.0], "b": [0.0, 0.5, 1.0, 2.0]}
    chart = xyg.scatter_chart(xyg.scatter(x=columns["a"], y=columns["b"], density=True))
    views = [
        dict(id=i, x="a", y="b", width=2, height=2, x_range=[0.0, 3.0], y_range=[0.0, 3.0])
        for i in range(1, 34)
    ]
    with chart.filter_session(columns, source_id=112) as session:
        for view in views[:32]:
            for dimension in ("a", "b"):
                session.configure_density(
                    dict(id=view["id"], dimension=dimension, cuts=[0.0, 1.0]), views
                )
                session.range(0.0, 1.0, exact=True)
        session.configure_density(dict(id=33, dimension="a", cuts=[0.0, 1.0]), views)
        before = session.paint(exact=True)
        assert before["selected_count"] == 3
        with pytest.raises(FilterTierCError) as refused:
            session.range(0.0, 1.0, exact=True)
        reply = refused.value.reply
        assert refused.value.status == 2
        for field in (
            "revision",
            "filter_hash",
            "index_bytes",
            "source_id",
            "epoch",
            "source_revision",
            "active_view",
            "has_intent",
        ):
            assert reply[field] == before[field], field
        after = session.paint(exact=True)
        assert after["filter_hash"] == before["filter_hash"]
        assert after["views"] == before["views"]
        assert after["selected_count"] == 3
        assert session.membership(0, 4)["membership"] == b"\x07"
        # Refusal must leave editing and reconfiguration usable at the cap.
        session.begin_edit()
        session.cancel_edit()
        session.configure_density(dict(id=1, dimension="a", cuts=[0.0, 1.0]), views)
        assert session.paint(exact=True)["filter_hash"] == before["filter_hash"]
        session.range(0.0, 0.5, exact=True)
        assert session.paint(exact=True)["selected_count"] == 2
        session.clear()
        assert session.paint(exact=True)["selected_count"] == 4
        session.range(0.0, 1.0, exact=True)
        assert session.paint(exact=True)["selected_count"] == 3
