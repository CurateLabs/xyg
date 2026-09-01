"""Small-multiple composition built from independent screen-bounded figures.

Facets deliberately use one Figure per panel instead of duplicating a second
axis/LOD model inside the WebGL client. Each panel keeps the existing payload
contract, native aggregation, and context governor behavior. The wrapper only
owns grid layout and shared-domain coordination.
"""

from __future__ import annotations

from ._facets_data import _facet_values, _label_codes, _subset_data
from ._facets_grid import FacetGrid

__all__ = ["FacetGrid", "_facet_values", "_label_codes", "_subset_data"]
