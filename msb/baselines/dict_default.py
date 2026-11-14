"""Dictionary default-implementation baseline: bind a metric by alias, run the default grain, no contracts."""
from __future__ import annotations

from msb.baselines.naive_surface import NaiveSurfaceBaseline


class DictDefaultBaseline(NaiveSurfaceBaseline):
    """Same surface parser as naive, documented as 'dictionary default, no contract checks'.

    Kept as a separate named baseline so the SOTA table can later swap in a stricter binder
    without changing naive_surface. In v0 the two coincide on most questions; they will
    diverge once a contract-aware binder is attached (that work belongs to BindOrClarify).
    """

    name = "dict_default"
