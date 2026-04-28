# Config Map

Config families are organized by use-case, not by entrypoint. The filenames below are the canonical inputs used by the CLI, Studio resources, and smoke scripts.

## Families

| Folder | Purpose | Typical files |
| --- | --- | --- |
| `base/` | Base runtime configs and smoke baselines. | `paper_base_1c_128.json`, `paper_base_2c_128.json`, `paper_search_random.json` |
| `search/` | Search definitions, filters, and run schedules. | `search_smoke.json`, `search_motion.json`, `search_corpus_v1_core_neutral.json` |
| `presets/` | Ready-to-run simulation presets exposed in Studio and paper-grounded lanes. | `orbium_like_classic_1c_128.json`, `flow_motile_2c_128.json`, `crossmap_1c_128.json` |
| `sweeps/` | Sweep manifests that expand into many jobs. | `discovery_sweeps.json`, `glider_sweeps.json`, `mover_sweeps.json` |
| `campaigns/` | Campaign templates for orchestrated runs. | `exploration.json`, `full-discovery.json`, `intervention-battery.json` |
| `es/` | Evolution-strategy configs. | `es_directed_motion.json`, `es_directed_compact.json` |
| `imgep/` | IMGEP-specific configs and corpus variants. | `imgep_motile.json`, `imgep_complexity.json`, `imgep_corpus_v1_dense.json` |

## Shortcuts

- Start from `base/paper_base_1c_128.json` and `search/search_smoke.json` for deterministic smoke runs.
- Use `presets/` when you want a named starting point that the Studio can load directly.
- Use `sweeps/` and `campaigns/` when you want the CLI to fan out work rather than hand-curate individual runs.
- Use `es/` and `imgep/` for discovery protocols that layer optimization on top of a base config.

## Notes

- The CLI and Studio both treat these folders as the source of truth for run inputs.
- Paper-grounded modes are documented in [ResearchModes](../contracts/ResearchModes.md); this map covers the reusable config families they consume.
