import Lake

open Lake DSL

package lean_corpus_extractor

@[default_target]
lean_exe lean_corpus_extract where
  root := `LeanCorpusExtractor.Main

