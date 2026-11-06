import LeanTacticRepresentation.Compiler.Surface

open Lean

namespace LeanTacticRepresentation.Compiler

structure StaticGoal where
  goalId : String
  target : PropExpr
  deriving Repr, BEq

structure StepPlan where
  goalId : String
  operator : String
  resolvedTerm : String
  target : PropExpr
  children : Array StaticGoal
  continuationKind : String
  couplingKind : String
  childOrder : Array String
  residualTemplate : String
  deriving Repr, BEq

structure Compilation where
  request : Request
  prediction : Array StepPlan
  instructionCount : Nat
  deriving Repr, BEq

private structure InferredStep where
  operator : String
  resolvedTerm : String
  children : Array StaticGoal
  continuationKind : String
  couplingKind : String
  childOrder : Array String
  residualTemplate : String

private structure GoalCompilation where
  program : Program
  rest : List Instr
  prediction : Array StepPlan

def propExprText : PropExpr → String
  | .atom name => name
  | .andExpr left right => s!"{propExprTextParen left} ∧ {propExprTextParen right}"
  | .arrow domain codomain => s!"{propExprTextParen domain} → {propExprText codomain}"
where
  propExprTextParen : PropExpr → String
    | .atom name => name
    | expression => s!"({propExprText expression})"

private def termRefText : TermRef → String
  | .local name => name
  | .constant name => name

private def continuationKind (childCount : Nat) : String :=
  if childCount == 0 then
    "solve"
  else if childCount == 1 then
    "refine"
  else
    "branch"

private def couplingKind (childCount : Nat) : String :=
  if childCount <= 1 then "none" else "independent"

private def stableChildIds (goalId : String) (count : Nat) : Array String :=
  Array.ofFn fun index : Fin count => s!"{goalId}.{index.val + 1}"

private def applicationTemplate (head : String) (childIds : Array String) : String :=
  if childIds.isEmpty then
    head
  else
    let holes := childIds.toList.map fun childId => s!"?{childId}"
    s!"{head}({String.intercalate ", " holes})"

private partial def applyPremises (target : PropExpr) : PropExpr → Option (Array PropExpr)
  | type =>
      if type == target then
        some #[]
      else
        match type with
        | .arrow domain codomain =>
            (applyPremises target codomain).map fun premises => #[domain] ++ premises
        | _ => none

private def lookupHypothesis (problem : Problem) (name : String) : Except String Hypothesis := do
  let some hypothesis := problem.hypotheses.find? fun hypothesis => hypothesis.name == name
    | throw s!"unknown hypothesis '{name}'"
  return hypothesis

private def inferStep
    (problem : Problem) (goal : StaticGoal) (instruction : Instr) : Except String InferredStep := do
  let (operator, resolvedTerm, childTargets) ←
    match instruction with
    | .exactStep hypothesisName => do
        let hypothesis ← lookupHypothesis problem hypothesisName
        unless hypothesis.type == goal.target do
          throw s!"exact '{hypothesisName}' has type {propExprText hypothesis.type}, expected {propExprText goal.target} at {goal.goalId}"
        pure ("exact", hypothesisName, #[])
    | .applyStep (.local name) => do
        let hypothesis ← lookupHypothesis problem name
        let some premises := applyPremises goal.target hypothesis.type
          | throw s!"apply '{name}' has no result suffix matching {propExprText goal.target} at {goal.goalId}"
        pure ("apply", name, premises)
    | .applyStep (.constant name) =>
        throw s!"apply constant '{name}' has no pure compiler contract in v0"
    | .constructorStep =>
        match goal.target with
        | .andExpr left right => pure ("constructor", "And.intro", #[left, right])
        | target =>
            throw s!"constructor expects a conjunction at {goal.goalId}, got {propExprText target}"

  let childIds := stableChildIds goal.goalId childTargets.size
  let children := Array.ofFn fun index : Fin childTargets.size => {
    goalId := childIds[index.val]!
    target := childTargets[index]
  }
  return {
    operator
    resolvedTerm
    children
    continuationKind := continuationKind children.size
    couplingKind := couplingKind children.size
    childOrder := childIds
    residualTemplate := applicationTemplate resolvedTerm childIds
  }

private def lowerInstruction (instruction : Instr) (children : Array Program) : Program :=
  match instruction with
  | .exactStep hypothesis => .exactStep hypothesis
  | .applyStep term => .applyStep term children
  | .constructorStep => .constructorStep children

private partial def compileGoal
    (problem : Problem) (goal : StaticGoal) (code : List Instr) : Except String GoalCompilation := do
  let instruction :: remaining := code
    | throw s!"source ended with unresolved goal {goal.goalId}: {propExprText goal.target}"
  let inferred ← inferStep problem goal instruction
  let step : StepPlan := {
    goalId := goal.goalId
    operator := inferred.operator
    resolvedTerm := inferred.resolvedTerm
    target := goal.target
    children := inferred.children
    continuationKind := inferred.continuationKind
    couplingKind := inferred.couplingKind
    childOrder := inferred.childOrder
    residualTemplate := inferred.residualTemplate
  }

  let mut rest := remaining
  let mut childPrograms : Array Program := #[]
  let mut prediction := #[step]
  for child in inferred.children do
    let compiled ← compileGoal problem child rest
    childPrograms := childPrograms.push compiled.program
    prediction := prediction ++ compiled.prediction
    rest := compiled.rest

  return {
    program := lowerInstruction instruction childPrograms
    rest
    prediction
  }

def compile (source : SourceRequest) : Except String Compilation := do
  let root : StaticGoal := {
    goalId := "g0"
    target := source.problem.target
  }
  let compiled ← compileGoal source.problem root source.code.toList
  unless compiled.rest.isEmpty do
    throw s!"source has {compiled.rest.length} extra instruction(s) after all goals were solved"
  let request : Request := {
    schemaVersion := source.schemaVersion
    requestId := source.requestId
    imports := source.imports
    problem := source.problem
    program := compiled.program
  }
  request.validate
  return {
    request
    prediction := compiled.prediction
    instructionCount := source.code.size
  }

private def staticGoalToJson (goal : StaticGoal) : Json :=
  Json.mkObj [
    ("goal_id", goal.goalId),
    ("target", toJson goal.target),
    ("target_text", propExprText goal.target),
  ]

private def stepPlanToJson (step : StepPlan) : Json :=
  Json.mkObj [
    ("goal_id", step.goalId),
    ("operator", step.operator),
    ("resolved_term", step.resolvedTerm),
    ("target", toJson step.target),
    ("target_text", propExprText step.target),
    ("children", Json.arr (step.children.map staticGoalToJson)),
    ("branch_arity", step.children.size),
    ("continuation_kind", step.continuationKind),
    ("coupling", Json.mkObj [
      ("kind", step.couplingKind),
      ("shared_metavars", Json.arr #[]),
      ("dependency_edges", Json.arr #[]),
    ]),
    ("child_order", toJson step.childOrder),
    ("residual_template", step.residualTemplate),
  ]

def Compilation.toJsonObject (compilation : Compilation) : Json :=
  Json.mkObj [
    ("instruction_count", compilation.instructionCount),
    ("target_request", toJson compilation.request),
    ("prediction", Json.arr (compilation.prediction.map stepPlanToJson)),
    ("certificates", Json.arr #[
      "pure_compiler_no_metam",
      "source_goal_stack_exhausted",
      "target_request_validated",
    ]),
  ]

end LeanTacticRepresentation.Compiler
