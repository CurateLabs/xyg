"""M2 leftover-cluster inventory stays unique and importable."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_clusters():
    path = Path(__file__).resolve().parents[1] / "scripts" / "m2_leftover_clusters.py"
    spec = importlib.util.spec_from_file_location("m2_leftover_clusters", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_m2_leftover_cluster_keys_and_titles_are_unique() -> None:
    module = _load_clusters()
    keys = [cluster["key"] for cluster in module.CLUSTERS]
    titles = [cluster["title"] for cluster in module.CLUSTERS]
    parents = {cluster["parent"] for cluster in module.CLUSTERS}
    assert len(keys) == len(set(keys))
    assert len(titles) == len(set(titles))
    assert len(module.CLUSTERS) == 27
    assert parents == {271, 272, 275, 276, 278, 279, 282, 283}
