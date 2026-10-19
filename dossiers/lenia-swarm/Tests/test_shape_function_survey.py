from __future__ import annotations

import numpy as np

from lenia_swarm_analysis.anatomical_compiler.shape_function_coupling import _SHAPE_METRICS
from lenia_swarm_analysis.anatomical_compiler.shape_function_survey import _fit


def test_fit_attributes_a_size_driven_target_to_the_size_group() -> None:
    rng = np.random.default_rng(0)
    shape = rng.standard_normal((2000, len(_SHAPE_METRICS)))
    target = 3.0 * shape[:, _SHAPE_METRICS.index("gyration")] + 0.1 * rng.standard_normal(2000)

    fit = _fit(shape, target)

    assert fit["r2"] > 0.99
    assert fit["groupOnlyR2"]["size"] > 0.99
    assert fit["groupOnlyR2"]["anisotropy"] < 0.01
    assert fit["dropGroupR2"]["size"] > 0.98
    assert abs(fit["dropGroupR2"]["anisotropy"]) < 0.01
    assert fit["dropOneR2"]["gyration"] > 0.98
