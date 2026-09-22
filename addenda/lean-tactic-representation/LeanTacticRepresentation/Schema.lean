import Lean

open Lean

namespace LeanTacticRepresentation

inductive PropExpr where
  | atom (name : String)
  | andExpr (left right : PropExpr)
  | arrow (domain codomain : PropExpr)
  deriving Repr, BEq

structure Hypothesis where
  name : String
  type : PropExpr
  deriving Repr, BEq

inductive TermRef where
  | local (name : String)
  | constant (name : String)
  deriving Repr, BEq

inductive Program where
  | exactStep (hypothesis : String)
  | applyStep (term : TermRef) (children : Array Program)
  | constructorStep (children : Array Program)
  deriving Repr, BEq

structure Problem where
  atoms : Array String
  hypotheses : Array Hypothesis
  target : PropExpr
  deriving Repr, BEq

structure Request where
  schemaVersion : Nat
  requestId : String
  imports : Array String
  problem : Problem
  program : Program
  deriving Repr, BEq

private def expectFields (label : String) (json : Json) (allowed : Array String) : Except String Unit := do
  let object ← json.getObj?
  object.foldlM (init := ()) fun _ key _ =>
    if allowed.contains key then
      pure ()
    else
      throw s!"{label}: unknown field '{key}'"

private def field [FromJson α] (json : Json) (name : String) : Except String α := do
  let value ← json.getObjVal? name
  match fromJson? value with
  | .ok result => pure result
  | .error message => throw s!"field '{name}': {message}"

private def rawField (json : Json) (name : String) : Except String Json :=
  json.getObjVal? name

private partial def propExprFromJson (json : Json) : Except String PropExpr := do
  let kind : String ← field json "kind"
  match kind with
  | "atom" =>
      expectFields "PropExpr.atom" json #["kind", "name"]
      return .atom (← field json "name")
  | "and" =>
      expectFields "PropExpr.and" json #["kind", "left", "right"]
      return .andExpr
        (← propExprFromJson (← rawField json "left"))
        (← propExprFromJson (← rawField json "right"))
  | "arrow" =>
      expectFields "PropExpr.arrow" json #["kind", "domain", "codomain"]
      return .arrow
        (← propExprFromJson (← rawField json "domain"))
        (← propExprFromJson (← rawField json "codomain"))
  | other => throw s!"PropExpr: unknown kind '{other}'"

private partial def propExprToJson : PropExpr → Json
  | .atom name => Json.mkObj [
      ("kind", "atom"),
      ("name", name),
    ]
  | .andExpr left right => Json.mkObj [
      ("kind", "and"),
      ("left", propExprToJson left),
      ("right", propExprToJson right),
    ]
  | .arrow domain codomain => Json.mkObj [
      ("kind", "arrow"),
      ("domain", propExprToJson domain),
      ("codomain", propExprToJson codomain),
    ]

instance : FromJson PropExpr where
  fromJson? := propExprFromJson

instance : ToJson PropExpr where
  toJson := propExprToJson

private def hypothesisFromJson (json : Json) : Except String Hypothesis := do
  expectFields "Hypothesis" json #["name", "type"]
  return {
    name := ← field json "name"
    type := ← field json "type"
  }

private def hypothesisToJson (hypothesis : Hypothesis) : Json :=
  Json.mkObj [
    ("name", hypothesis.name),
    ("type", toJson hypothesis.type),
  ]

instance : FromJson Hypothesis where
  fromJson? := hypothesisFromJson

instance : ToJson Hypothesis where
  toJson := hypothesisToJson

private def termRefFromJson (json : Json) : Except String TermRef := do
  expectFields "TermRef" json #["kind", "name"]
  let kind : String ← field json "kind"
  let name : String ← field json "name"
  match kind with
  | "local" => return .local name
  | "constant" => return .constant name
  | other => throw s!"TermRef: unknown kind '{other}'"

private def termRefToJson : TermRef → Json
  | .local name => Json.mkObj [
      ("kind", "local"),
      ("name", name),
    ]
  | .constant name => Json.mkObj [
      ("kind", "constant"),
      ("name", name),
    ]

instance : FromJson TermRef where
  fromJson? := termRefFromJson

instance : ToJson TermRef where
  toJson := termRefToJson

private partial def programFromJson (json : Json) : Except String Program := do
  let op : String ← field json "op"
  match op with
  | "exact" =>
      expectFields "Program.exact" json #["op", "hypothesis"]
      return .exactStep (← field json "hypothesis")
  | "apply" =>
      expectFields "Program.apply" json #["op", "term", "children"]
      let childJson : Array Json ← field json "children"
      return .applyStep (← field json "term") (← childJson.mapM programFromJson)
  | "constructor" =>
      expectFields "Program.constructor" json #["op", "children"]
      let childJson : Array Json ← field json "children"
      return .constructorStep (← childJson.mapM programFromJson)
  | other => throw s!"Program: unknown op '{other}'"

private partial def programToJson : Program → Json
  | .exactStep hypothesis => Json.mkObj [
      ("op", "exact"),
      ("hypothesis", hypothesis),
    ]
  | .applyStep term children => Json.mkObj [
      ("op", "apply"),
      ("term", toJson term),
      ("children", Json.arr (children.map programToJson)),
    ]
  | .constructorStep children => Json.mkObj [
      ("op", "constructor"),
      ("children", Json.arr (children.map programToJson)),
    ]

instance : FromJson Program where
  fromJson? := programFromJson

instance : ToJson Program where
  toJson := programToJson

private def problemFromJson (json : Json) : Except String Problem := do
  expectFields "Problem" json #["atoms", "hypotheses", "target"]
  return {
    atoms := ← field json "atoms"
    hypotheses := ← field json "hypotheses"
    target := ← field json "target"
  }

private def problemToJson (problem : Problem) : Json :=
  Json.mkObj [
    ("atoms", toJson problem.atoms),
    ("hypotheses", toJson problem.hypotheses),
    ("target", toJson problem.target),
  ]

instance : FromJson Problem where
  fromJson? := problemFromJson

instance : ToJson Problem where
  toJson := problemToJson

private def ensureNonempty (label value : String) : Except String Unit :=
  if value.trim.isEmpty then
    throw s!"{label} must not be empty"
  else
    pure ()

private def ensureCanonicalLeanName (label value : String) : Except String Unit := do
  ensureNonempty label value
  let parsed := value.toName
  if parsed.isAnonymous then
    throw s!"{label} must not parse as an anonymous Lean name"
  unless parsed.toString == value do
    throw s!"{label} '{value}' is not canonical; use '{parsed}'"

private def ensureDistinct (label : String) (values : Array String) : Except String Unit := do
  let mut seen : Array String := #[]
  for value in values do
    if seen.contains value then
      throw s!"{label}: duplicate value '{value}'"
    seen := seen.push value

private def ensureDistinctLeanNames
    (label : String) (values : Array String) : Except String Unit := do
  let mut seen : Array Name := #[]
  for value in values do
    ensureCanonicalLeanName label value
    let parsed := value.toName
    if seen.contains parsed then
      throw s!"{label}: values collide as Lean name '{parsed}'"
    seen := seen.push parsed

private partial def validatePropExpr
    (atoms : Array String) (path : String) : PropExpr → Except String Unit
  | .atom name => do
      ensureNonempty s!"{path}.name" name
      unless atoms.contains name do
        throw s!"{path}: unknown atom '{name}'"
  | .andExpr left right => do
      validatePropExpr atoms s!"{path}.left" left
      validatePropExpr atoms s!"{path}.right" right
  | .arrow domain codomain => do
      validatePropExpr atoms s!"{path}.domain" domain
      validatePropExpr atoms s!"{path}.codomain" codomain

private partial def validateProgram
    (hypotheses : Array String) (path : String) : Program → Except String Unit
  | .exactStep hypothesis => do
      ensureCanonicalLeanName s!"{path}.hypothesis" hypothesis
      unless hypotheses.contains hypothesis do
        throw s!"{path}: unknown hypothesis '{hypothesis}'"
  | .applyStep term children => do
      match term with
      | .local name =>
          ensureCanonicalLeanName s!"{path}.term.name" name
          unless hypotheses.contains name do
            throw s!"{path}: unknown local apply term '{name}'"
      | .constant name => ensureCanonicalLeanName s!"{path}.term.name" name
      for h : index in *...children.size do
        validateProgram hypotheses s!"{path}.children[{index}]" children[index]
  | .constructorStep children =>
      for h : index in *...children.size do
        validateProgram hypotheses s!"{path}.children[{index}]" children[index]

def Request.validate (request : Request) : Except String Unit := do
  unless request.schemaVersion == 1 do
    throw s!"unsupported schema_version {request.schemaVersion}; expected 1"
  ensureNonempty "request_id" request.requestId
  unless request.imports == #["Lean"] do
    throw "v1 supports exactly one static import set: ['Lean']"
  ensureDistinct "imports" request.imports
  for importName in request.imports do
    ensureNonempty "import name" importName

  ensureDistinct "problem.atoms" request.problem.atoms
  ensureDistinctLeanNames "problem.atoms" request.problem.atoms

  let hypothesisNames := request.problem.hypotheses.map (fun hypothesis => hypothesis.name)
  ensureDistinct "problem.hypotheses" hypothesisNames
  ensureDistinctLeanNames "problem.hypotheses" hypothesisNames
  for hypothesis in request.problem.hypotheses do
    if request.problem.atoms.contains hypothesis.name then
      throw s!"hypothesis name '{hypothesis.name}' collides with an atom name"
    validatePropExpr request.problem.atoms s!"hypothesis '{hypothesis.name}'" hypothesis.type

  validatePropExpr request.problem.atoms "problem.target" request.problem.target
  validateProgram hypothesisNames "program" request.program

private def requestFromJson (json : Json) : Except String Request := do
  expectFields "Request" json #["schema_version", "request_id", "imports", "problem", "program"]
  let request : Request := {
    schemaVersion := ← field json "schema_version"
    requestId := ← field json "request_id"
    imports := ← field json "imports"
    problem := ← field json "problem"
    program := ← field json "program"
  }
  request.validate
  return request

private def requestToJson (request : Request) : Json :=
  Json.mkObj [
    ("schema_version", request.schemaVersion),
    ("request_id", request.requestId),
    ("imports", toJson request.imports),
    ("problem", toJson request.problem),
    ("program", toJson request.program),
  ]

instance : FromJson Request where
  fromJson? := requestFromJson

instance : ToJson Request where
  toJson := requestToJson

end LeanTacticRepresentation
