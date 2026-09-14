import LeanTacticRepresentation

open Lean Meta

namespace LeanTacticRepresentation

structure CliConfig where
  input : Option System.FilePath := none
  pretty : Bool := false

def usage : String :=
  String.intercalate "\n" [
    "tactic_bridge (structured Lean tactic executor)",
    "",
    "Usage:",
    "  tactic_bridge [--input PATH] [--pretty]",
    "",
    "Reads one v1 JSON request from PATH, or from stdin when --input is omitted.",
    "Writes one JSON response to stdout. Errors are JSON on stderr with exit code 1.",
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
  | "--input" :: [] =>
      throw <| IO.userError "--input requires a path"
  | flag :: _ =>
      throw <| IO.userError s!"unknown argument '{flag}'\n\n{usage}"

def readRequestText (config : CliConfig) : IO String := do
  match config.input with
  | some path => IO.FS.readFile path
  | none =>
      let stdin ← IO.getStdin
      stdin.readToEnd

def parseRequest (text : String) : IO Request := do
  let json ← match Json.parse text with
    | .ok value => pure value
    | .error message => throw <| IO.userError s!"invalid JSON: {message}"
  match fromJson? json with
  | .ok request => pure request
  | .error message => throw <| IO.userError s!"invalid v1 request: {message}"

def loadEnvironment : IO Environment := do
  initSearchPath (← findSysroot)
  unsafe
    enableInitializersExecution
  importModules (loadExts := true) #[{ module := `Lean : Import }] interpreterOptions

def runRequest (request : Request) (sourceText : String) : IO Json := do
  let env ← loadEnvironment
  let coreContext : Core.Context := {
    fileName := "<tactic_bridge>"
    fileMap := FileMap.ofString sourceText
    options := interpreterOptions
    currNamespace := .anonymous
    openDecls := []
  }
  let coreState : Core.State := { env }
  let (response, _, _) ← MetaM.toIO (executeRequest request) coreContext coreState
  return response

def errorResponse (message : String) : Json :=
  Json.mkObj [
    ("schema_version", 1),
    ("status", "error"),
    ("message", message),
  ]

def main (args : List String) : IO Unit := do
  try
    let config ← parseArgs args
    let sourceText ← readRequestText config
    let request ← parseRequest sourceText
    let response ← runRequest request sourceText
    if config.pretty then
      IO.println (Json.pretty response)
    else
      IO.println (Json.compress response)
  catch exception =>
    IO.eprintln (Json.compress <| errorResponse (toString exception))
    IO.Process.exit 1

end LeanTacticRepresentation

def main (args : List String) : IO Unit :=
  LeanTacticRepresentation.main args
