from __future__ import annotations

from dataclasses import dataclass

from laws import LawCatalog


@dataclass(frozen=True)
class DirectKernelRule:
    source_id: int
    source_equation: str
    kernel_id: int
    kernel_equation: str


@dataclass(frozen=True)
class MicroRewriteRule:
    source_id: int
    source_equation: str
    base_kernel_id: int
    base_equation: str
    helper_kernel_id: int
    helper_equation: str


@dataclass(frozen=True)
class ConstructiveProofCatalog:
    direct_kernel_rules: tuple[DirectKernelRule, ...]
    micro_rewrite_rules: tuple[MicroRewriteRule, ...]

    def direct_rules_for_source(self, source_id: int) -> tuple[DirectKernelRule, ...]:
        return tuple(rule for rule in self.direct_kernel_rules if rule.source_id == source_id)

    def micro_rules_for_source(self, source_id: int) -> tuple[MicroRewriteRule, ...]:
        return tuple(rule for rule in self.micro_rewrite_rules if rule.source_id == source_id)


_DIRECT_KERNEL_SPECS = (
    ("x = y ◇ (z ◇ ((w ◇ u) ◇ x))", "x ◇ y = z ◇ y"),
    ("x = (y ◇ y) ◇ (y ◇ (z ◇ x))", "x ◇ y = z ◇ y"),
    ("x = ((y ◇ x) ◇ y) ◇ (z ◇ z)", "x = x ◇ (((y ◇ z) ◇ y) ◇ z)"),
    ("x = (y ◇ (z ◇ (x ◇ w))) ◇ x", "x ◇ y = x ◇ (x ◇ y)"),
    ("x = (y ◇ (z ◇ (z ◇ x))) ◇ x", "x = (y ◇ ((z ◇ x) ◇ x)) ◇ x"),
    ("x = (y ◇ (z ◇ (z ◇ x))) ◇ y", "x = (x ◇ y) ◇ y"),
    ("x = (((x ◇ x) ◇ y) ◇ z) ◇ y", "x ◇ y = x ◇ z"),
    ("x ◇ x = (y ◇ (z ◇ z)) ◇ z", "x ◇ x = (x ◇ (y ◇ y)) ◇ z"),
    ("x ◇ x = ((y ◇ x) ◇ x) ◇ z", "x ◇ x = ((y ◇ z) ◇ z) ◇ w"),
    ("x ◇ (y ◇ z) = y ◇ (w ◇ u)", "x ◇ (y ◇ z) = w ◇ (u ◇ v)"),
)

_MICRO_REWRITE_SPECS = (
    (
        "x = y ◇ (y ◇ ((x ◇ z) ◇ z))",
        "x ◇ y = y ◇ ((x ◇ z) ◇ z)",
        "x ◇ y = y ◇ x",
    ),
    (
        "x = ((y ◇ z) ◇ x) ◇ (z ◇ y)",
        "x ◇ (x ◇ y) = (y ◇ z) ◇ z",
        "x ◇ y = y ◇ x",
    ),
)


def build_constructive_proof_catalog(catalog: LawCatalog) -> ConstructiveProofCatalog:
    direct_kernel_rules = tuple(
        DirectKernelRule(
            source_id=catalog.lookup_id(source_equation),
            source_equation=source_equation,
            kernel_id=catalog.lookup_id(kernel_equation),
            kernel_equation=kernel_equation,
        )
        for source_equation, kernel_equation in _DIRECT_KERNEL_SPECS
    )
    micro_rewrite_rules = tuple(
        MicroRewriteRule(
            source_id=catalog.lookup_id(source_equation),
            source_equation=source_equation,
            base_kernel_id=catalog.lookup_id(base_equation),
            base_equation=base_equation,
            helper_kernel_id=catalog.lookup_id(helper_equation),
            helper_equation=helper_equation,
        )
        for source_equation, base_equation, helper_equation in _MICRO_REWRITE_SPECS
    )
    return ConstructiveProofCatalog(
        direct_kernel_rules=direct_kernel_rules,
        micro_rewrite_rules=micro_rewrite_rules,
    )
