"""Explicit-state initial conditions for LeniaCLI runs of the anatomical compiler."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np

from lenia_swarm_analysis.trace_codec import state_patch


def state_patch_config(
    base_config: dict[str, Any], field: np.ndarray, *, center: tuple[int, int], seed: int
) -> dict[str, Any]:
    """Return a copy of base_config whose init seeds an explicit density field through
    init.state_patch, the Swift engine's explicit-state path (see
    SearchInitializationBuilder.buildExplicitInitialState).

    The builder writes a width*height*channels block, iterated x-outer/y/channel-inner,
    centered at `center` onto a zero background, so the values are the C-order ravel of the
    [sx, sy, C] field and width/height are the field's sx/sy. state_patch requires
    init.a_uniform == [0, 0] and (parameter_embedding disabled) no init.patches, so both are
    forced here."""
    if field.ndim == 2:
        field = field[:, :, None]
    sx, sy, channels = field.shape
    values = np.ascontiguousarray(field, dtype="<f4").ravel(order="C")
    config = deepcopy(base_config)
    config["init"] = {
        "seed": seed,
        "patches": [],
        "a_uniform": {"low": 0.0, "high": 0.0},
        "p_uniform": None,
        "state_patch": state_patch(
            center=[int(center[0]), int(center[1])],
            width=int(sx),
            height=int(sy),
            channels=int(channels),
            values=values,
        ),
    }
    return config
