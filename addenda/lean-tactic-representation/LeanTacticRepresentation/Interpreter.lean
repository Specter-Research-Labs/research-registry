import Lean.Meta.Tactic.Constructor
import LeanTacticRepresentation.Schema

open Lean Meta

namespace LeanTacticRepresentation

structure ChildObligation where
  goalId : String
  target : String
  targetIr : PropExpr

structure CouplingInfo where
  kind : String
  sharedMetavars : Array String := #[]
  dependencyEdges : Array (String × String) := #[]

structure StepTrace where
  goalId : String
  operator : String
  resolvedTerm : String
  target : String
  targetIr : PropExpr
  contextTypes : Array String
  children : Array ChildObligation
  continuationKind : String
  coupling : CouplingInfo
  partialTermBefore : String
  partialTermAfter : String
  residualBuilderId : String
  childOrder : Array String
  effectFlags : Array String
  tacticDependsOn : Array String
  certificates : Array String

private structure MVarOccurrence where
  id : MVarId
  childIds : Array String

private def stringArrayJson (values : Array String) : Json :=
  Json.arr (values.map Json.str)

private def childObligationToJson (child : ChildObligation) : Json :=
  Json.mkObj [
    ("goal_id", child.goalId),
    ("target", child.target),
    ("target_ir", toJson child.targetIr),
  ]

private def couplingToJson (coupling : CouplingInfo) : Json :=
  Json.mkObj [
    ("kind", coupling.kind),
    ("shared_metavars", stringArrayJson coupling.sharedMetavars),
    ("dependency_edges", Json.arr <| coupling.dependencyEdges.map fun (source, target) =>
      Json.arr #[source, target]),
  ]

private def stepTraceToJson (step : StepTrace) : Json :=
  Json.mkObj [
    ("goal_id", step.goalId),
    ("operator", step.operator),
    ("resolved_term", step.resolvedTerm),
    ("target", step.target),
    ("target_ir", toJson step.targetIr),
    ("context_types", stringArrayJson step.contextTypes),
    ("children", Json.arr (step.children.map childObligationToJson)),
    ("action_kind", "tactic_step"),
    ("operator_kind", match step.operator with
      | "exact" => "close"
      | "apply" => "apply"
      | _ => "branch"),
    ("effect_flags", stringArrayJson step.effectFlags),
    ("branch_arity", step.children.size),
    ("continuation_kind", step.continuationKind),
    ("goal_coupling", step.coupling.kind),
    ("coupling", couplingToJson step.coupling),
    ("tactic_depends_on", stringArrayJson step.tacticDependsOn),
    ("proof_step_count", 1),
    ("partial_term_before", step.partialTermBefore),
    ("partial_term_after", step.partialTermAfter),
    ("residual_builder", Json.mkObj [
      ("builder_id", step.residualBuilderId),
      ("child_order", stringArrayJson step.childOrder),
      ("template", step.partialTermAfter),
    ]),
    ("certificates", stringArrayJson step.certificates),
  ]

private partial def compileProp (atoms : NameMap Expr) : PropExpr → MetaM Expr
  | .atom name =>
      match atoms.find? name.toName with
      | some atom => pure atom
      | none => throwError "unknown atom '{name}'"
  | .andExpr left right => do
      return mkApp2 (mkConst ``And) (← compileProp atoms left) (← compileProp atoms right)
  | .arrow domain codomain => do
      return mkForall .anonymous .default (← compileProp atoms domain) (← compileProp atoms codomain)

private partial def withAtoms {alpha : Type}
    (names : List String) (atoms : NameMap Expr) (k : NameMap Expr → MetaM alpha) : MetaM alpha := do
  match names with
  | [] => k atoms
  | name :: rest =>
      withLocalDeclD name.toName (mkSort levelZero) fun atom =>
        withAtoms rest (atoms.insert name.toName atom) k

private partial def withHypotheses {alpha : Type}
    (hypotheses : List Hypothesis)
    (atoms : NameMap Expr)
    (locals : NameMap Expr)
    (k : NameMap Expr → MetaM alpha) : MetaM alpha := do
  match hypotheses with
  | [] => k locals
  | hypothesis :: rest => do
      let type ← compileProp atoms hypothesis.type
      withLocalDeclD hypothesis.name.toName type fun localExpr =>
        withHypotheses rest atoms (locals.insert hypothesis.name.toName localExpr) k

private def ppExprString (expression : Expr) : MetaM String := do
  return toString (← ppExpr expression)

private partial def reifyProp (expression : Expr) : MetaM PropExpr := do
  let expression ← instantiateMVars expression
  match expression with
  | .fvar fvarId =>
      let declaration ← fvarId.getDecl
      return .atom declaration.userName.toString
  | .forallE _ domain codomain _ =>
      if codomain.hasLooseBVars then
        throwError "cannot reify a dependent forall into the v0 proposition IR"
      return .arrow (← reifyProp domain) (← reifyProp codomain)
  | _ =>
      let arguments := expression.getAppArgs
      if expression.getAppFn.isConstOf ``And && arguments.size == 2 then
        return .andExpr (← reifyProp arguments[0]!) (← reifyProp arguments[1]!)
      throwError "cannot reify actual Lean goal into the v0 proposition IR: {expression}"

private def TermRef.resolve (term : TermRef) (locals : NameMap Expr) : MetaM Expr :=
  match term with
  | .local name =>
      match locals.find? name.toName with
      | some localExpr => pure localExpr
      | none => throwError "unknown local apply term '{name}'"
  | .constant name => mkConstWithFreshMVarLevels name.toName

private def TermRef.display : TermRef → String
  | .local name => name
  | .constant name => name

private def stableChildIds (goalId : String) (count : Nat) : Array String :=
  Array.ofFn fun index : Fin count => s!"{goalId}.{index.val + 1}"

private def continuationKind (childCount : Nat) : String :=
  if childCount == 0 then
    "solve"
  else if childCount == 1 then
    "refine"
  else
    "branch"

private def applicationTemplate (head : String) (childIds : Array String) : String :=
  if childIds.isEmpty then
    head
  else
    let holes := childIds.toList.map fun childId => s!"?{childId}"
    s!"{head}({String.intercalate ", " holes})"

private def childObligations
    (children : Array MVarId) (childIds : Array String) : MetaM (Array ChildObligation) := do
  let mut result := #[]
  for h : index in *...children.size do
    let child := children[index]
    let target ← child.withContext child.getType
    let targetText ← child.withContext (ppExprString target)
    let targetIr ← child.withContext (reifyProp target)
    result := result.push { goalId := childIds[index]!, target := targetText, targetIr }
  return result

private def analyzeCoupling
    (children : Array MVarId) (childIds : Array String) : MetaM CouplingInfo := do
  if children.size <= 1 then
    return { kind := "none" }

  let mut edges : Array (String × String) := #[]
  let mut occurrences : Array MVarOccurrence := #[]

  for h : targetIndex in *...children.size do
    let child := children[targetIndex]
    let targetMVars ← child.withContext do
      getMVars (← child.getType)
    for targetMVar in targetMVars do
      let mut isChildGoal := false
      for hSource : sourceIndex in *...children.size do
        if children[sourceIndex] == targetMVar then
          isChildGoal := true
          if sourceIndex != targetIndex then
            edges := edges.push (childIds[sourceIndex]!, childIds[targetIndex]!)
      unless isChildGoal do
        match occurrences.findIdx? (fun occurrence => occurrence.id == targetMVar) with
        | some occurrenceIndex =>
            if hOccurrence : occurrenceIndex < occurrences.size then
              let occurrence := occurrences[occurrenceIndex]
              if !occurrence.childIds.contains childIds[targetIndex]! then
                occurrences := occurrences.set occurrenceIndex {
                  occurrence with childIds := occurrence.childIds.push childIds[targetIndex]!
                }
            else
              throwError "internal coupling occurrence index is out of bounds"
        | none =>
            occurrences := occurrences.push {
              id := targetMVar
              childIds := #[childIds[targetIndex]!]
            }

  let sharedOccurrences := occurrences.filter fun occurrence => occurrence.childIds.size > 1
  let sharedMetavars := Array.ofFn fun index : Fin sharedOccurrences.size => s!"shared.{index.val}"
  let hasUnexplained := occurrences.any fun occurrence => occurrence.childIds.size == 1
  let kind :=
    if !edges.isEmpty || !sharedMetavars.isEmpty then
      "coupled"
    else if hasUnexplained then
      "unknown"
    else
      "independent"
  return { kind, sharedMetavars, dependencyEdges := edges }

private def resolveConstructorName (goal : MVarId) : MetaM String := do
  let partialExpr ← instantiateMVars (mkMVar goal)
  match partialExpr.getAppFn.constName? with
  | some name => pure name.toString
  | none => throwError "constructor produced a residual term without a constant head"

private partial def executeProgram
    (program : Program)
    (goal : MVarId)
    (goalId : String)
    (locals : NameMap Expr)
    (contextTypes : Array String) : MetaM (Array StepTrace) :=
  goal.withContext do
    goal.checkNotAssigned `tacticBridge
    let target ← goal.getType
    let targetText ← ppExprString target
    let targetIr ← reifyProp target
    let partialBefore := s!"?{goalId}"

    let (programChildren, children, operator, resolvedTerm, dependencies, effects, certificates) ←
      match program with
      | .exactStep hypothesis => do
          let some localExpr := locals.find? hypothesis.toName
            | throwError "unknown exact hypothesis '{hypothesis}'"
          unless ← goal.checkedAssign localExpr do
            throwError "exact '{hypothesis}' failed to close goal {goalId}"
          pure (#[], #[], "exact", hypothesis, #[hypothesis],
            #["discharges_goal", "completes_term", "uses_hypotheses"],
            #["Lean.MVarId.checkedAssign"])
      | .applyStep term programChildren => do
          let expression ← term.resolve locals
          let children := (← goal.apply expression { newGoals := .all }).toArray
          let effects :=
            if children.isEmpty then
              #["instantiates_goal", "discharges_goal", "completes_term"]
            else
              #["instantiates_goal", "opens_goals", "refines_term"]
          let dependencies := match term with
            | .local name => #[name]
            | .constant _ => #[]
          let effects :=
            if dependencies.isEmpty then effects else effects.push "uses_hypotheses"
          pure (programChildren, children, "apply", term.display, dependencies, effects,
            #["Lean.MVarId.apply"])
      | .constructorStep programChildren => do
          let children := (← goal.constructor { newGoals := .all }).toArray
          let resolvedTerm ← resolveConstructorName goal
          let effects :=
            if children.size > 1 then
              #["branches_goals", "opens_goals", "refines_term"]
            else if children.isEmpty then
              #["discharges_goal", "completes_term"]
            else
              #["opens_goals", "refines_term"]
          pure (programChildren, children, "constructor", resolvedTerm, #[], effects,
            #["Lean.MVarId.constructor"])

    unless programChildren.size == children.size do
      throwError "program child count {programChildren.size} does not match Lean goal count {children.size} at {goalId}"

    let childIds := stableChildIds goalId children.size
    let childInfo ← childObligations children childIds
    let coupling ← analyzeCoupling children childIds
    let partialAfter :=
      if operator == "exact" then resolvedTerm else applicationTemplate resolvedTerm childIds
    let step : StepTrace := {
      goalId
      operator
      resolvedTerm
      target := targetText
      targetIr
      contextTypes
      children := childInfo
      continuationKind := continuationKind children.size
      coupling
      partialTermBefore := partialBefore
      partialTermAfter := partialAfter
      residualBuilderId := s!"rb:{goalId}"
      childOrder := childIds
      effectFlags := effects
      tacticDependsOn := dependencies
      certificates
    }

    let mut traces := #[step]
    for h : index in *...children.size do
      let some childProgram := programChildren[index]?
        | throwError "validated program child index {index} is missing"
      let childTraces ←
        executeProgram childProgram children[index] childIds[index]! locals contextTypes
      traces := traces ++ childTraces
    return traces

private def provenanceToJson (request : Request) (env : Environment) : Json :=
  Json.mkObj [
    ("lean_version", Lean.versionString),
    ("lean_git_hash", Lean.githash),
    ("lean_toolchain", Lean.toolchain),
    ("target", System.Platform.target),
    ("trust_level", env.header.trustLevel.toNat),
    ("direct_imports", stringArrayJson request.imports),
    ("loaded_direct_imports", stringArrayJson <|
      env.header.imports.map fun imported => imported.module.toString),
    ("loaded_module_count", env.header.moduleNames.size),
    ("options", Json.mkObj [
      ("debug.skipKernelTC", false),
      ("maxHeartbeats", 200000),
      ("maxRecDepth", 1000),
      ("pp.unicode", true),
      ("pp.universes", false),
      ("pp.width", 120),
    ]),
  ]

private def successfulResponse
    (request : Request)
    (env : Environment)
    (traces : Array StepTrace)
    (proofText targetText inferredTypeText : String)
    (usedConstants : Array String) : Json :=
  Json.mkObj [
    ("schema_version", 1),
    ("status", "success"),
    ("request_id", request.requestId),
    ("provenance", provenanceToJson request env),
    ("serialization", Json.mkObj [
      ("round_trip_checked", true),
      ("canonical_request", toJson request),
    ]),
    ("execution", Json.mkObj [
      ("root_goal_id", "g0"),
      ("steps", Json.arr (traces.map stepTraceToJson)),
      ("completed_proof_term", proofText),
    ]),
    ("kernel_certificate", Json.mkObj [
      ("checker", "Lean.Kernel.check"),
      ("kernel_checked", true),
      ("definitionally_equal", true),
      ("target_type", targetText),
      ("inferred_type", inferredTypeText),
      ("open_metavariables", 0),
      ("uses_sorry", false),
      ("used_constants", stringArrayJson usedConstants),
    ]),
  ]

def interpreterOptions : Options :=
  (({} : Options)
    |>.setBool `debug.skipKernelTC false
    |>.setNat `maxHeartbeats 200000
    |>.setNat `maxRecDepth 1000
    |>.setBool `pp.unicode true
    |>.setBool `pp.universes false
    |>.setNat `pp.width 120)

def executeRequest (request : Request) : MetaM Json := do
  let canonicalRequest := toJson request
  let reparsed : Request ←
    match fromJson? canonicalRequest with
    | .ok value => pure value
    | .error message => throwError "canonical request failed to parse: {message}"
  unless reparsed == request do
    throwError "request serialization round-trip changed the typed program"

  withAtoms request.problem.atoms.toList {} fun atoms =>
    withHypotheses request.problem.hypotheses.toList atoms {} fun locals => do
      let target ← compileProp atoms request.problem.target
      let root ← mkFreshExprSyntheticOpaqueMVar target (tag := `g0)
      let rootId := root.mvarId!
      let rootDecl ← rootId.getDecl
      let atomContextTypes := request.problem.atoms.map fun _ => "Prop"
      let hypothesisContextTypes ← request.problem.hypotheses.mapM fun hypothesis => do
        ppExprString (← compileProp atoms hypothesis.type)
      let contextTypes := atomContextTypes ++ hypothesisContextTypes
      let traces ← executeProgram request.program rootId "g0" locals contextTypes
      let proof ← instantiateMVars root
      if proof.hasExprMVar || proof.hasLevelMVar then
        throwError "execution finished with unresolved metavariables"
      if proof.hasSorry then
        throwError "execution produced a proof containing sorryAx"

      let env ← getEnv
      unless env.header.trustLevel == 0 do
        throwError "kernel environment trust level is {env.header.trustLevel}; expected 0"
      let inferredType ←
        match Kernel.check env rootDecl.lctx proof with
        | .ok type => pure type
        | .error exception => throwError "Lean.Kernel.check rejected the proof: {exception.toMessageData {}}"
      match Kernel.isDefEq env rootDecl.lctx inferredType target with
      | .ok true => pure ()
      | .ok false => throwError "kernel inferred a type that is not definitionally equal to the target"
      | .error exception => throwError "Lean.Kernel.isDefEq failed: {exception.toMessageData {}}"

      let proofText ← ppExprString proof
      let targetText ← ppExprString target
      let inferredTypeText ← ppExprString inferredType
      let usedConstants := proof.getUsedConstants.map Name.toString |>.qsort (fun left right => left < right)
      return successfulResponse request env traces proofText targetText inferredTypeText usedConstants

end LeanTacticRepresentation
