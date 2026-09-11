# Website handoff

**Workspace:** `/Users/ludwig/dev/specter-labs/research-registry-workspaces/morphospace-editorial`  
**Preview:** `http://127.0.0.1:8897/`  
Website checkpoint: `715e2a78`. Committed locally; not deployed. The broader Flow Lenia organism search is paused.

## Reports, code, and data

Report paths below are relative to `site/dossiers/lenia-swarm/` in the website workspace. Other paths are relative to `/Users/ludwig/dev/specter-labs/`.

| Reports | Code and datasets |
| --- | --- |
| `morphospace/` and `fiber-theory/` | Analysis code: website workspace's `dossiers/lenia-swarm/lenia_swarm_analysis/morphospace/` and `fiber/`. Data: `research-registry/dossiers/lenia-swarm/artifacts/`, especially `morphospace-analysis/`, `external/biological-morphospaces/`, and `canonical-sources/`. Public figure data: `site/assets/blog/lenia-morphospace-report/` in the website workspace. |
| `morphospace/obstacle-response/` | `research-registry-workspaces/morphospace-response-pilot/dossiers/lenia-swarm/`: native code under `Sources/`; datasets, analysis scripts, and runs under `.codex/unseen-obstacle-response-v2/`. Final run: `new-discoveries-allmatter-obstacle-grid-512x512-final/`. |
| `anatomical-compiler/` | `research-registry-workspaces/slim-anatomical/dossiers/lenia-swarm/`: code under `lenia_swarm_analysis/anatomical_compiler/`; reruns under `outputs/anatomical-compiler/`. Historical datasets: `research-registry/dossiers/lenia-swarm/outputs/anatomical-compiler/`. |
| `causal-emergence/reports/` — current synthesis is `synthesis-v7/` | `research-registry-workspaces/lenia-perturbation-recovery/dossiers/lenia-swarm/`: experiment code, plans, and results under `.codex/gard-compositional-causal-emergence-v1/`; raw runs under `artifacts/replication-precursor/gard-compositional-causal-emergence-v1/`; native engine under `Sources/`. |

The historical Morphospace DuckDB is on **`ssh macmini`**, under `/Volumes/Addenda/archive/specter/lenia-swarm/warehouse-retention/v8/`. The website used `morphospace-v8-schema8-pre-v9-20260712.duckdb` in the `a09f700c…` directory.

Optional exact file mappings: [source index](report-reanalysis-index.json).

## Homepage and design changes

The homepage keeps its existing composition and soft grid. Changes add refined typography, ink headlines, ultramarine/apricot accents, and native Lenia motion. The accepted direction is instrument-style; the research-plate, monograph, and journal studies are retained for publication layouts.

Homepage source: `site/templates/index.html` and `site/assets/home.css`. Shared publication styles: `site/assets/publication-layout.css` and `publication-formats.css`. Design experiments remain at `/style-study/`; local review pages are under `/review/`.
