"""N300 cards: each card is one (1, 2) mesh, driven by its own process.

Cards run as independent processes rather than one large mesh because bodies never interact,
so a fleet needs no fabric between cards and scales linearly.
"""

from __future__ import annotations

import multiprocessing as mp
import os
from collections.abc import Callable

MESH_SHAPE = (1, 2)


def open_card():
    import ttnn

    ttnn.set_fabric_config(ttnn.FabricConfig.FABRIC_1D)
    return ttnn.open_mesh_device(ttnn.MeshShape(*MESH_SHAPE))


def close_card(mesh) -> None:
    import ttnn

    ttnn.close_mesh_device(mesh)


def _card_main(card: int, target: Callable, args: tuple, results) -> None:
    os.environ["TT_VISIBLE_DEVICES"] = str(card)
    results.put((card, target(card, *args)))


def on_cards(target: Callable, jobs: dict[int, tuple]) -> dict:
    """Run target(card, *args) for every card at once and return {card: result}.

    TT_VISIBLE_DEVICES must be set before ttnn is imported, so each card gets a fresh spawned
    process. target must be a module-level function and its result small and picklable, since
    workers are joined before the queue is drained."""
    ctx = mp.get_context("spawn")
    results = ctx.Queue()
    procs = {
        card: ctx.Process(target=_card_main, args=(card, target, args, results))
        for card, args in jobs.items()
    }
    for p in procs.values():
        p.start()
    for p in procs.values():
        p.join()
    failed = sorted(card for card, p in procs.items() if p.exitcode != 0)
    if failed:
        raise RuntimeError(f"workers failed on cards {failed}")
    return dict(results.get() for _ in procs)
