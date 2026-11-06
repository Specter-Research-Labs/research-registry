import LeanTacticRepresentation.Compiler.Semantics

open Lean

namespace LeanTacticRepresentation.Compiler

structure CliConfig where
  input : Option System.FilePath := none
  pretty : Bool := false

def usage : String :=
  String.intercalate "\n" [
    "tactic_compile (pure structured-tactic compiler)",
    "",
    "Usage:",
    "  tactic_compile [--input PATH] [--pretty]",
    "",
    "Reads one compiler source request from PATH or stdin.",
    "Writes the checked target request and static prediction as JSON.",
  ]

partial def parseArgs (args : List String) (config : CliConfig := {}) : IO CliConfig := do
  match args with
  | [] => pure config
  | "--help" :: _ =>
      IO.println usage
      IO.Process.exit 0
  | "--pretty" :: rest =>
      if config.pretty then
        throw <| IO.userError "--pretty may only be provided once"
      parseArgs rest { config with pretty := true }
  | "--input" :: path :: rest =>
      if config.input.isSome then
        throw <| IO.userError "--input may only be provided once"
      parseArgs rest { config with input := some (System.FilePath.mk path) }
  | "--input" :: [] => throw <| IO.userError "--input requires a path"
  | flag :: _ => throw <| IO.userError s!"unknown argument '{flag}'\n\n{usage}"

def readSourceText (config : CliConfig) : IO String := do
  match config.input with
  | some path => IO.FS.readFile path
  | none =>
      let stdin ← IO.getStdin
      stdin.readToEnd

def parseSource (text : String) : IO SourceRequest := do
  let json ← match Json.parse text with
    | .ok value => pure value
    | .error message => throw <| IO.userError s!"invalid JSON: {message}"
  match fromJson? json with
  | .ok source => pure source
  | .error message => throw <| IO.userError s!"invalid compiler source: {message}"

def successfulResponse (source : SourceRequest) (compilation : Compilation) : Json :=
  Json.mkObj [
    ("schema_version", 1),
    ("status", "success"),
    ("provenance", Json.mkObj [
      ("compiler", "tactic_compile/v0"),
      ("lean_version", Lean.versionString),
      ("lean_git_hash", Lean.githash),
      ("lean_toolchain", Lean.toolchain),
      ("target", System.Platform.target),
    ]),
    ("source", Json.mkObj [
      ("round_trip_checked", true),
      ("canonical_source", toJson source),
    ]),
    ("compilation", compilation.toJsonObject),
  ]

def errorResponse (message : String) : Json :=
  Json.mkObj [
    ("schema_version", 1),
    ("status", "error"),
    ("message", message),
  ]

def main (args : List String) : IO Unit := do
  try
    let config ← parseArgs args
    let sourceText ← readSourceText config
    let source ← parseSource sourceText
    let canonical := toJson source
    let reparsed : SourceRequest ← match fromJson? canonical with
      | .ok value => pure value
      | .error message => throw <| IO.userError s!"canonical source failed to parse: {message}"
    unless reparsed == source do
      throw <| IO.userError "source serialization round-trip changed the program"
    let compilation ← match compile source with
      | .ok value => pure value
      | .error message => throw <| IO.userError s!"compile error: {message}"
    let response := successfulResponse source compilation
    if config.pretty then
      IO.println (Json.pretty response)
    else
      IO.println (Json.compress response)
  catch exception =>
    IO.eprintln (Json.compress <| errorResponse (toString exception))
    IO.Process.exit 1

end LeanTacticRepresentation.Compiler

def main (args : List String) : IO Unit :=
  LeanTacticRepresentation.Compiler.main args
