"""Premise dependencies of checked Lean proofs.

A proof's dependencies are the library constants its declaration value uses
directly. Constants created in the current file (auxiliary lemmas from simp,
match compilers, the declaration itself) are expanded, so a lemma that simp
used implicitly counts as a dependency; library lemmas stay opaque, so a lemma
used inside another lemma's proof does not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from leantree.repl_adapter.interaction import LeanInteractionException

DECLARATION_NAME_RE = re.compile(r"theorem\s+([A-Za-z_][A-Za-z0-9_.']*)\s")

TACTIC_PREFIXES = (
    "Mathlib.Tactic.",
    "Mathlib.Meta.",
    "Lean.",
    "Aesop.",
    "Batteries.Tactic.",
    "Std.Tactic.",
    "Qq.",
)
LOGIC_MODULES = frozenset(
    {
        "Init.Prelude",
        "Init.Core",
        "Init.SimpLemmas",
        "Init.PropLemmas",
        "Init.Classical",
        "Init.ByCases",
    }
)

_CLOSURE_COMMAND = """open Lean Meta in
#eval show MetaM Unit from do
  let env ← getEnv
  let mut todo : Array Name := #[`{root}]
  let mut seen : NameSet := {{}}
  let mut out := #[]
  while todo.size > 0 do
    let n := todo.back!
    todo := todo.pop
    if seen.contains n then continue
    seen := seen.insert n
    let some ci := env.find? n | throwError s!"missing {{n}}"
    match env.getModuleIdxFor? n with
    | none =>
      if let some v := ci.value? (allowOpaque := true) then
        todo := todo ++ v.getUsedConstants
    | some idx =>
      let kind := match ci with
        | .thmInfo _ => "thm" | .defnInfo _ => "def" | .axiomInfo _ => "axiom"
        | .ctorInfo _ => "ctor" | .recInfo _ => "rec" | .inductInfo _ => "induct"
        | .opaqueInfo _ => "opaque" | .quotInfo _ => "quot"
      let mod := (env.header.moduleNames[idx.toNat]!).toString
      let inst := isInstanceCore env n
      out := out.push s!"{{n}}\\t{{kind}}\\t{{mod}}\\t{{inst}}\\t{{← isProp ci.type}}"
  logInfo (String.intercalate "\\n" ("{marker}" :: out.toList))
"""
_MARKER = "wonton-dependencies"


class PremiseBlocked(Exception):
    def __init__(self, tactic: str, constants: list[str]):
        super().__init__(f"{tactic!r} uses blocked premise {', '.join(constants)}")
        self.tactic = tactic
        self.constants = constants


@dataclass(frozen=True)
class Dependency:
    name: str
    kind: str
    module: str
    instance: bool
    prop: bool

    @property
    def role(self) -> str:
        if self.instance:
            return "instance"
        if self.name.startswith(TACTIC_PREFIXES) or self.module.startswith(TACTIC_PREFIXES):
            return "tactic"
        if self.kind == "axiom":
            return "axiom"
        if not self.prop:
            return "definition"
        if self.module in LOGIC_MODULES:
            return "logic"
        return "lemma"

    @property
    def premise(self) -> str:
        return premise_name(self.name)

    def row(self) -> list[Any]:
        return [self.name, self.kind, self.module, self.instance, self.prop]

    @classmethod
    def from_row(cls, row: list[Any]) -> Dependency:
        name, kind, module, instance, prop = row
        return cls(name=name, kind=kind, module=module, instance=instance, prop=prop)


@dataclass(frozen=True)
class ProofCheck:
    ok: bool
    error: str | None
    dependencies: tuple[Dependency, ...]

    def premises(self) -> set[str]:
        return {d.premise for d in self.dependencies if d.role == "lemma"}


def premise_name(name: str) -> str:
    """Map generated auxiliary lemmas such as `foo._simp_1` to the lemma they come from."""
    parts = name.split(".")
    while len(parts) > 1 and parts[-1].startswith("_"):
        parts.pop()
    return ".".join(parts)


def forbidden_hits(names: Iterable[str], forbidden: Iterable[str]) -> set[str]:
    blocked = set(forbidden)
    return {name for name in names if premise_name(name) in blocked}


def declaration_name(statement: str) -> str:
    match = DECLARATION_NAME_RE.search(statement)
    if match is None:
        raise ValueError(f"statement has no theorem name: {statement[:120]!r}")
    return match.group(1)


def proof_script(statement_with_sorry: str, tactics: list[str]) -> str:
    """Replace the trailing `sorry` of a statement with a flat tactic script.

    Multi-line tactics are parenthesized so their internal layout parses as one
    tactic sequence, the same unit the REPL applied them as.
    """
    head, sep, tail = statement_with_sorry.rstrip().rpartition("\n")
    if not sep or tail.strip() != "sorry":
        raise ValueError("statement must end with a `sorry` line")
    indent = tail[: len(tail) - len(tail.lstrip())]
    lines = [head]
    for tactic in tactics:
        first, *rest = tactic.strip("\n").split("\n")
        if not rest:
            lines.append(indent + first)
            continue
        lines.append(f"{indent}({first}")
        lines.extend(f"{indent} {line}" for line in rest)
        lines.append(f"{indent})")
    return "\n".join(lines)


def _errors(response: dict) -> list[str]:
    return [m["data"] for m in response.get("messages", []) if m.get("severity") == "error"]


async def declaration_dependencies(env: Any, name: str) -> tuple[Dependency, ...]:
    response = await env.send_command_async(
        _CLOSURE_COMMAND.format(root=name, marker=_MARKER)
    )
    errors = _errors(response)
    if errors:
        raise RuntimeError(f"dependency query for {name} failed: {errors[0]}")
    infos = [
        m["data"]
        for m in response.get("messages", [])
        if m.get("severity") == "info" and m["data"].startswith(_MARKER)
    ]
    if len(infos) != 1:
        raise RuntimeError(f"dependency query for {name} returned {len(infos)} results")
    deps = []
    for line in infos[0].split("\n")[1:]:
        dep_name, kind, module, instance, prop = line.split("\t")
        deps.append(
            Dependency(
                name=dep_name,
                kind=kind,
                module=module,
                instance=instance == "true",
                prop=prop == "true",
            )
        )
    return tuple(sorted(deps, key=lambda d: d.name))


async def check_proof(env: Any, statement_with_sorry: str, tactics: list[str]) -> ProofCheck:
    """Elaborate the proof as a declaration and collect its dependencies."""
    name = declaration_name(statement_with_sorry)
    # The REPL raises instead of returning messages when the kernel rejects the term.
    try:
        response = await env.send_command_async(proof_script(statement_with_sorry, tactics))
    except LeanInteractionException as exc:
        return ProofCheck(ok=False, error=str(exc), dependencies=())
    errors = _errors(response)
    if errors:
        return ProofCheck(ok=False, error=errors[0], dependencies=())
    deps = await declaration_dependencies(env, name)
    if any(d.name == "sorryAx" for d in deps):
        return ProofCheck(ok=False, error="proof uses sorry", dependencies=deps)
    return ProofCheck(ok=True, error=None, dependencies=deps)
