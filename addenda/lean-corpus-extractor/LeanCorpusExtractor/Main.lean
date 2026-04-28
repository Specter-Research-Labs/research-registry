import Lean
import Lean.PrivateName

open Lean

namespace LeanCorpusExtractor

structure Config where
  imports : Array Name := #[]
  modulePrefixes : Array String := #[]
  names : Array Name := #[]
  limit : Option Nat := none
  out : Option System.FilePath := none
  includeInternal : Bool := false
  includePrivate : Bool := false
  ppWidth : Nat := 200
  ppUnicode : Bool := false
  deriving Inhabited

def nameFromDotted (s : String) : Name :=
  (s.splitOn ".").foldl (fun acc part => Name.mkStr acc part) .anonymous

def startsWithAny (s : String) (prefixes : Array String) : Bool :=
  if prefixes.isEmpty then
    true
  else
    prefixes.any (fun p => s.startsWith p)

def hexDigit (n : Nat) : Char :=
  if n < 10 then
    Char.ofNat (n + ('0'.toNat))
  else
    Char.ofNat (n - 10 + ('a'.toNat))

def toHex (n : Nat) (width : Nat) : String :=
  let rec go (n : Nat) (k : Nat) (acc : List Char) : List Char :=
    match k with
    | 0 => acc
    | k + 1 =>
        let d := n % 16
        go (n / 16) k (hexDigit d :: acc)
  String.mk (go n width [])

def encodeLeanIdent (raw : String) : String :=
  if raw.isEmpty then
    "anon"
  else
    let out :=
      raw.data.foldl (init := "") fun acc ch =>
        if ('A' <= ch && ch <= 'Z') || ('a' <= ch && ch <= 'z') || ('0' <= ch && ch <= '9') then
          acc.push ch
        else
          -- Encode all non-alphanumerics (including '_' '.' and ''') to avoid collisions.
          -- The output uses only [A-Za-z0-9_] characters.
          let code := ch.toNat
          let width := if code < 256 then 2 else 4
          acc ++ "_x" ++ toHex code width
    match out.data with
    | [] => "anon"
    | first :: _ =>
        if ('A' <= first && first <= 'Z') || ('a' <= first && first <= 'z') || first == '_' then
          out
        else
          "_" ++ out

def usage : String :=
  String.intercalate "\n" [
    "lean_corpus_extract (Lean environment extractor)",
    "",
    "Usage:",
    "  lean_corpus_extract --import Mathlib [--module-prefix Mathlib.Data.Nat.Basic] [--limit N] [--out PATH]",
    "",
    "Options:",
    "  --import <Module>          Module to import (repeatable). Default: Mathlib",
    "  --module-prefix <Prefix>   Keep only decls whose module starts with this prefix (repeatable)",
    "  --name <QualifiedName>     Extract only this theorem/lemma (repeatable)",
    "  --limit <N>                Max number of extracted theorems",
    "  --out <PATH>               Write JSONL to PATH (default: stdout)",
    "  --include-internal         Include internal names (default: false)",
    "  --include-private          Include private names (default: false)",
    "  --pp-width <N>             Pretty-printer width (default: 200)",
    "  --pp-unicode               Enable unicode pretty printing (default: false)",
  ]

partial def parseArgs (args : List String) (cfg : Config := {}) : IO Config := do
  match args with
  | [] => pure cfg
  | "--help" :: _ =>
      IO.println usage
      IO.Process.exit 0
  | "--import" :: mod :: rest =>
      parseArgs rest { cfg with imports := cfg.imports.push (nameFromDotted mod) }
  | "--module-prefix" :: p :: rest =>
      parseArgs rest { cfg with modulePrefixes := cfg.modulePrefixes.push p }
  | "--name" :: n :: rest =>
      parseArgs rest { cfg with names := cfg.names.push (nameFromDotted n) }
  | "--limit" :: n :: rest =>
      match n.toNat? with
      | none => throw <| IO.userError s!"Invalid --limit: {n}"
      | some v => parseArgs rest { cfg with limit := some v }
  | "--out" :: p :: rest =>
      parseArgs rest { cfg with out := some (System.FilePath.mk p) }
  | "--include-internal" :: rest =>
      parseArgs rest { cfg with includeInternal := true }
  | "--include-private" :: rest =>
      parseArgs rest { cfg with includePrivate := true }
  | "--pp-width" :: n :: rest =>
      match n.toNat? with
      | none => throw <| IO.userError s!"Invalid --pp-width: {n}"
      | some v => parseArgs rest { cfg with ppWidth := v }
  | "--pp-unicode" :: rest =>
      parseArgs rest { cfg with ppUnicode := true }
  | flag :: _ =>
      throw <| IO.userError s!"Unknown flag: {flag}\n\n{usage}"

def ppExprToString (env : Environment) (e : Expr) (cfg : Config) : IO String := do
  let opts :=
    (({} : Options)
      |>.setNat `pp.width cfg.ppWidth
      |>.setBool `pp.unicode cfg.ppUnicode
      |>.setBool `pp.all false
      |>.setBool `pp.universes false
      |>.setBool `pp.funBinderTypes true
      |>.setBool `pp.proofs true)
  let ctxCore : Core.Context := {
    fileName := "<lean_corpus_extract>",
    fileMap := FileMap.ofString "",
    options := opts,
    currNamespace := .anonymous,
    openDecls := [],
  }
  let sCore : Core.State := { env := env }
  let act : Lean.Meta.MetaM String := do
    let fmt ← Lean.Meta.ppExpr e
    return toString fmt
  let (out, _, _) ← Lean.Meta.MetaM.toIO act ctxCore sCore
  return out.trim

def loadEnv (imports : Array Name) : IO Environment := do
  let imps := imports.map (fun n => { module := n : Import })
  let opts : Options := {}
  unsafe
    enableInitializersExecution
  importModules (loadExts := true) imps opts

structure Item where
  itemId : String
  json : Json

def mkItemJson (itemId displayName stmt modName qualName : String) : Json :=
  Json.mkObj [
    ("item_id", Json.str itemId),
    ("display_name", Json.str displayName),
    ("payload", Json.mkObj [
      ("statement", Json.str stmt),
      ("source", Json.mkObj [
        ("kind", Json.str "lean_env"),
        ("module", Json.str modName),
        ("qualname", Json.str qualName),
      ]),
    ]),
  ]

def main (args : List String) : IO Unit := do
  let cfg0 ← parseArgs args
  let cfg :=
    if cfg0.imports.isEmpty then
      { cfg0 with imports := #[nameFromDotted "Mathlib"] }
    else
      cfg0
  initSearchPath (← findSysroot)

  let env ← loadEnv cfg.imports

  let mut items : Array Item := #[]
  let mut missing : Array Name := #[]
  if cfg.names.isEmpty then
    for (n, info) in env.constants.toList do
      match info with
      | ConstantInfo.thmInfo v =>
          if !cfg.includeInternal && n.isInternal then
            continue
          if !cfg.includePrivate && isPrivateName n then
            continue
          let modName :=
            match env.getModuleIdxFor? n with
            | none => env.mainModule.toString
            | some idx =>
                let mods := env.allImportedModuleNames
                mods.getD idx.toNat env.mainModule |>.toString
          if !startsWithAny modName cfg.modulePrefixes then
            continue
          let qual := n.toString
          let itemId := encodeLeanIdent qual
          let tyStr ← ppExprToString env v.type cfg
          let stmt := "theorem {name} : " ++ tyStr ++ " := by\n  sorry"
          let j := mkItemJson itemId qual stmt modName qual
          items := items.push { itemId := itemId, json := j }
      | _ => continue
  else
    let mut requested : Array Name := #[]
    for n in cfg.names do
      if requested.any (fun known => known == n) then
        continue
      requested := requested.push n
    for n in requested do
      match env.find? n with
      | some (ConstantInfo.thmInfo v) =>
          if !cfg.includeInternal && n.isInternal then
            missing := missing.push n
            continue
          if !cfg.includePrivate && isPrivateName n then
            missing := missing.push n
            continue
          let modName :=
            match env.getModuleIdxFor? n with
            | none => env.mainModule.toString
            | some idx =>
                let mods := env.allImportedModuleNames
                mods.getD idx.toNat env.mainModule |>.toString
          if !startsWithAny modName cfg.modulePrefixes then
            missing := missing.push n
            continue
          let qual := n.toString
          let itemId := encodeLeanIdent qual
          let tyStr ← ppExprToString env v.type cfg
          let stmt := "theorem {name} : " ++ tyStr ++ " := by\n  sorry"
          let j := mkItemJson itemId qual stmt modName qual
          items := items.push { itemId := itemId, json := j }
      | _ =>
          missing := missing.push n

  items := items.qsort (fun a b => a.itemId < b.itemId)
  if let some lim := cfg.limit then
    items := items.take lim

  if !cfg.names.isEmpty then
    for n in missing do
      IO.eprintln s!"[lean_corpus_extract] missing theorem: {n}"

  match cfg.out with
  | none =>
      for it in items do
        IO.println (Json.compress it.json)
  | some path =>
      let h ← IO.FS.Handle.mk path IO.FS.Mode.write
      for it in items do
        h.putStrLn (Json.compress it.json)
      h.flush

end LeanCorpusExtractor

def main (args : List String) : IO Unit :=
  LeanCorpusExtractor.main args
