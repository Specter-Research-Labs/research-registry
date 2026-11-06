import LeanTacticRepresentation.Schema

open Lean

namespace LeanTacticRepresentation.Compiler

inductive Instr where
  | exactStep (hypothesis : String)
  | applyStep (term : TermRef)
  | constructorStep
  deriving Repr, BEq

structure SourceRequest where
  schemaVersion : Nat
  requestId : String
  imports : Array String
  problem : Problem
  code : Array Instr
  deriving Repr, BEq

private def expectFields
    (label : String) (json : Json) (allowed : Array String) : Except String Unit := do
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

private def instrFromJson (json : Json) : Except String Instr := do
  let op : String ← field json "op"
  match op with
  | "exact" =>
      expectFields "Instr.exact" json #["op", "hypothesis"]
      return .exactStep (← field json "hypothesis")
  | "apply" =>
      expectFields "Instr.apply" json #["op", "term"]
      return .applyStep (← field json "term")
  | "constructor" =>
      expectFields "Instr.constructor" json #["op"]
      return .constructorStep
  | other => throw s!"Instr: unknown op '{other}'"

private def instrToJson : Instr → Json
  | .exactStep hypothesis => Json.mkObj [
      ("op", "exact"),
      ("hypothesis", hypothesis),
    ]
  | .applyStep term => Json.mkObj [
      ("op", "apply"),
      ("term", toJson term),
    ]
  | .constructorStep => Json.mkObj [("op", "constructor")]

instance : FromJson Instr where
  fromJson? := instrFromJson

instance : ToJson Instr where
  toJson := instrToJson

private def sourceRequestFromJson (json : Json) : Except String SourceRequest := do
  expectFields "SourceRequest" json #[
    "schema_version", "request_id", "imports", "problem", "code"
  ]
  let request : SourceRequest := {
    schemaVersion := ← field json "schema_version"
    requestId := ← field json "request_id"
    imports := ← field json "imports"
    problem := ← field json "problem"
    code := ← field json "code"
  }
  unless request.schemaVersion == 1 do
    throw s!"unsupported schema_version {request.schemaVersion}; expected 1"
  if request.requestId.trim.isEmpty then
    throw "request_id must not be empty"
  unless request.imports == #["Lean"] do
    throw "compiler v0 supports exactly one static import set: ['Lean']"
  if request.code.isEmpty then
    throw "code must contain at least one instruction"
  return request

private def sourceRequestToJson (request : SourceRequest) : Json :=
  Json.mkObj [
    ("schema_version", request.schemaVersion),
    ("request_id", request.requestId),
    ("imports", toJson request.imports),
    ("problem", toJson request.problem),
    ("code", toJson request.code),
  ]

instance : FromJson SourceRequest where
  fromJson? := sourceRequestFromJson

instance : ToJson SourceRequest where
  toJson := sourceRequestToJson

end LeanTacticRepresentation.Compiler

