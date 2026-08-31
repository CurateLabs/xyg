"""ABI 275 payload_transition_keys_admit parity."""

from __future__ import annotations

from xyg import kernels
from xyg.config import MAX_ANIMATION_MATCH_ROWS


def test_payload_transition_keys_admit_ship() -> None:
    assert (
        kernels.payload_transition_keys_admit(
            has_keys=True,
            tier_direct=True,
            n_keys=10,
            n_marks=10,
            max_rows=MAX_ANIMATION_MATCH_ROWS,
        )
        is None
    )


def test_payload_transition_keys_admit_snap_aggregate() -> None:
    assert (
        kernels.payload_transition_keys_admit(
            has_keys=True,
            tier_direct=False,
            n_keys=10,
            n_marks=10,
            max_rows=MAX_ANIMATION_MATCH_ROWS,
        )
        == "snap:aggregate"
    )


def test_payload_transition_keys_admit_key_limit() -> None:
    assert (
        kernels.payload_transition_keys_admit(
            has_keys=True,
            tier_direct=True,
            n_keys=MAX_ANIMATION_MATCH_ROWS + 1,
            n_marks=MAX_ANIMATION_MATCH_ROWS + 1,
            max_rows=MAX_ANIMATION_MATCH_ROWS,
        )
        == "snap:key-limit"
    )


def test_payload_transition_keys_admit_count_mismatch() -> None:
    assert (
        kernels.payload_transition_keys_admit(
            has_keys=True,
            tier_direct=True,
            n_keys=10,
            n_marks=9,
            max_rows=MAX_ANIMATION_MATCH_ROWS,
        )
        == "index:key-count-mismatch"
    )
