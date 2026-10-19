"""Swift-oracle acceptance for a body re-seeded into LeniaCLI through init.state_patch."""

from __future__ import annotations


def form_is_held(
    *, stable: bool, mass_conservation: float, form_drift: float,
    topology_distance: float, target_features: tuple[int, int],
    terminal_features: tuple[int, int],
) -> bool:
    """Core Swift-oracle invariant for accepting a re-seeded form."""
    return (
        stable
        and 0.95 < mass_conservation < 1.05
        and form_drift <= 0.25
        and topology_distance <= 0.5
        and terminal_features == target_features
    )
