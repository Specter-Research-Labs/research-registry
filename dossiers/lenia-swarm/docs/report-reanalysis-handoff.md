# Report re-analysis handoff

Checked 10–11 September 2026 against website checkpoint `715e2a78`. Scope: Morphospace and its Obstacle Response/Fiber Theory companions, Anatomical Compiler, and all 81 current/historical causal-emergence reports. This is an entry map for scientific re-analysis, not an instruction to publish or restart the paused organism search.

## Workspaces and roots

Resolve these paths from the `morphospace-editorial` repository root. The roots refer to existing local workspaces/data, not contents included in a fresh website clone.

| Alias | Location relative to website workspace | Role |
| --- | --- | --- |
| WEB | `.` | Accepted website sources and report projections; checkpoint `715e2a78` |
| CAUSAL | `../lenia-perturbation-recovery/dossiers/lenia-swarm` | Original causal experiment code, plans, results, and raw captures |
| OBSTACLE | `../morphospace-response-pilot/dossiers/lenia-swarm` | Original obstacle experiment workspace and local run outputs |
| HISTORICAL | `../../research-registry/dossiers/lenia-swarm` | Historical archives, morphology sources, and compiler outputs |
| COMPILER | `../slim-anatomical/dossiers/lenia-swarm` | September compiler/inverse reruns |
| AUDIT | `../morphospace-audit/dossiers/lenia-swarm` | Warehouse migration/retention receipts and analysis code |

Observed code workspace revisions: CAUSAL `d02f919bce11c6d6f4bee8f971b85929699cf11c`; OBSTACLE `ef4585eccf78a8e8d427edeb0c5c27b074ffcc4f`; COMPILER `42fff008e1062c058cea6c01bf88221aaf98ccee`. These identify the inspected checkouts, not necessarily the revisions that produced historical runs. Use each frozen plan's code and runner hashes to establish that binding. Local `.codex/` and raw artifacts must be preserved or transferred separately from a repository clone.

## Morphospace: shape comparison and transport

Report: `WEB/site/dossiers/lenia-swarm/morphospace/index.html`.

Immediately available figure data:

- `WEB/site/assets/blog/lenia-morphospace-report/visual-data.json`: 25,167 Lenia observations, 859 EmbryoMaker observations, 232 fish observations, selected-region membership, PCA loadings/centering, portraits, comparison results, and source hashes.
- `WEB/site/assets/blog/lenia-morphospace-report/fish-explainer.json`: measured fish landmarks and twelve-coordinate distance decomposition, including the original source hash.
- `WEB/site/assets/blog/lenia-morphospace-report/motion/provenance.json`: movie provenance. The moving specimens belong to the separate obstacle cohort.

Analysis code is in `WEB/dossiers/lenia-swarm/lenia_swarm_analysis/morphospace/`: start with `common_morphology.py`, `feature_matrix.py`, `ingest_dryad_fish.py`, `ingest_embryomaker.py`, `run_topology.py`, `derive_fibers.py`, and `high_fiber_null_validation.py`. Also inspect `lenia_swarm_analysis/fiber/` and `morphospace_cli.py`. `ops/render_morphospace_report.py` renders the public packet; it does not reconstruct the raw warehouse analysis.

Original input locations under HISTORICAL:

- Fish: `artifacts/external/biological-morphospaces/dryad-fish-body-shape-20240112/extracted/gpa/Slicer_GPA_output/OutputData.csv`. Dataset DOI `10.5061/dryad.n2z34tn2t`; eleven 3D landmarks per specimen.
- Tissue snapshots: `artifacts/canonical-sources/embryomaker-legacy-snapshots-20260506/embryomaker-ic2-snapshots/`.
- May analysis packets: `artifacts/morphospace-analysis/common-morphology-v1/`, `track1-pro-review-followup-20260527/`, and `track1-research-program-20260527/`. The latter two include perturbation/transport controls and their result packets. Inspect their source bindings before choosing a packet by date or filename.
- Experiment orchestration: `.codex/run_track1_next4_experiments.py`, `.codex/run_track1_pro_review_followup.py`, and `.codex/advance_track1_research_program.py`.

The exact warehouse used for the website reconstruction has SHA-256 `a09f700ca1e89a7b6a6c7266c7b8b482c9ccd52ecbe7fec2f765a4a5759dc0b9`. Its retention path under the Addenda archive volume is `archive/specter/lenia-swarm/warehouse-retention/v8/a09f700ca1e89a7b6a6c7266c7b8b482c9ccd52ecbe7fec2f765a4a5759dc0b9/morphospace-v8-schema8-pre-v9-20260712.duckdb`. The archive is available over `ssh macmini` at `/Volumes/Addenda/`; it does not need to be mounted on the website machine. Remote existence and size (281,098,072,064 bytes) were verified on 11 September 2026. The checksum above comes from the recorded source binding; this correction did not rehash the entire database. Query it on that host with a read-only DuckDB connection. AUDIT's `.codex/` contains retention/cutover receipts. Do not substitute a current warehouse version silently.

Recompute normalization and selection in twelve dimensions before PCA. The selected 256 observations are nearest to eight vertices of H1 cocycle 274, from a 2,048-landmark Ripser calculation. Separate observation counts from independent specimens and family-level replication. The fish inputs are landmarks, not outlines; transport controls address a different question from nearest-neighbor resemblance.

Fiber Theory (`WEB/site/dossiers/lenia-swarm/fiber-theory/`) is a companion explanation using these sources, not a separate empirical cohort.

## Obstacle Response

Report: `WEB/site/dossiers/lenia-swarm/morphospace/obstacle-response/index.html`.

Set `RUN = OBSTACLE/.codex/unseen-obstacle-response-v2`.

- Primary summary: `RUN/new-discoveries-allmatter-obstacle-grid-512x512-final/analysis.json`.
- Exact trial results and protocol: `RUN/new-discoveries-allmatter-obstacle-grid-512x512-final/obstacle-response-512-final-20260902/{results.jsonl,protocol.json}`. Both hashes match the summary receipts.
- Candidate corpus: `RUN/new-discoveries-allmatter-obstacle-corpora-512/grid-512x512-2271cba2/corpus.jsonl`.
- Source screening and replays: `RUN/new-discoveries-allmatter-long-input/`, `new-discoveries-allmatter-long-replay/`, `new-discoveries-allmatter-long-screen/`, and `new-discoveries-allmatter-validate/`.
- Analysis and selection: `RUN/analyze_qualified_obstacle_response.py`, `make_obstacle_corpus_from_screen.py`, and `screen_long_horizon_replays.py`.
- Native code: `OBSTACLE/Sources/LeniaCLI/ObstacleResponseCommand.swift` and `Sources/LeniaCore/Layer/Experiments/UnseenObstacleResponse.swift`.

The sequence is 626 screened specimens, nine qualified movers, five with valid paired encounters, and fifteen obstacle branches. Recompute the report summaries from paired branches, retaining the four calibration exclusions. The protocol uses a 1,200-step checkpoint and 3,600-step continuation; do not combine the earlier 128/256 pilot directories with the final 512-grid assay.

## Anatomical Compiler

Report: `WEB/site/dossiers/lenia-swarm/anatomical-compiler/index.html`. Its `source-manifest.json` lists exact inputs, asset hashes, and provenance limits.

All 65 non-schematic source artifacts were located and matched to their manifest SHA-256 values:

- **22 historical artifacts:** `HISTORICAL/outputs/anatomical-compiler/`. Start with `stage1_fresh_fiber.json`, `stage1_jacobian_fiber.json`, `stage2_cinn.json`, `stage3_refine.json`, `compiled/`, `qd_archive/`, `functional-morphospace/`, and `3c15/functional_map_mlx/`.
- **43 rerun artifacts:** `COMPILER/outputs/anatomical-compiler/`. Start with `compiled/descriptor-organic-2876-final/`, `compiled/organic-2876-trial/`, `media/organic-2876/`, `orbium-system-id-v5/`, and `orbium-system-id-v6-refine/`.
- Additional historical training/trajectory inputs live alongside these artifacts, including `forward_dataset_3k_1c_128.jsonl`, `canalization_3k_1c_128.jsonl`, `cinn.pt`, `2c20/`, and `3c15/`; this pass did not independently hash-bind all training inputs.

Code: `COMPILER/lenia_swarm_analysis/anatomical_compiler/`, especially `compile_phenotype.py`, `cinn_inverse.py`, `refine.py`, `functional_morphospace.py`, `shape_function_coupling.py`, `functional_map_mlx.py`, `trajectory_inverse.py`, and `forward_sim.py`. Native runtime code lives under `COMPILER/Sources/`; examine the saved search/config files to choose the implementation.

The historical producing revision is unknown in the manifest. Descriptor matching, dynamical maintenance, and within-family inverse recovery are separate tests. The September Orbium inverse uses `qd24_additive_v1`; it is not a Flow Lenia replication. The 8,174-creature regressions are descriptive until the original evaluation protocol establishes out-of-sample performance.

## Causal emergence: synthesis and all 81 reports

Set `CAMPAIGN = CAUSAL/.codex/gard-compositional-causal-emergence-v1` and `RAW = CAUSAL/artifacts/replication-precursor/gard-compositional-causal-emergence-v1`.

**All 81 original HTML files match their website catalog source hashes.** [report-reanalysis-index.json](report-reanalysis-index.json) maps every report ID to its original HTML and associated analysis directories, including available Python scripts, plans, result JSON, and compressed per-organism records. Directory links discovered from the report are navigation aids; the frozen plans/manifests define exact scientific dependencies.

Start the current synthesis at:

- `CAMPAIGN/synthesis-v7/source-manifest.local.json`: original source paths, evidence IDs, expected hashes, roles, and decision boundaries. All **49 source entries** match their recorded hashes. The machine-readable handoff preserves that verification. It does not claim to have hashed every raw trajectory.
- `CAMPAIGN/synthesis-v7/build_report.py`: original synthesis generator.
- `CAMPAIGN/synthesis-v7/the-organism-appears-first-in-possibility-space.html`: original report matching the website's catalog binding.

| Website report | Experiment directories below CAMPAIGN |
| --- | --- |
| `organism-birth-signal` | `organism-birth-signal-v1/`: `prospective.py`, `analysis.py`, `birth_detector.py`, `prospective-plan.json`, `prospective-results.json`, `prospective-analyzed-specimens.jsonl.gz` |
| `initial-action-world` | `initial-action-world-v1/`: `experiment.py`, `analysis.py`, `plan.json`, `future-freeze.json`, `results.json`, `analyzed-organisms.jsonl.gz` |
| `spatial-scale-action-world` | `spatial-scale-action-world-v1/`: corresponding plan/results/analysis plus `baselines.py` and `state-transformations.json` |
| `organism-hardens-without-narrowing` | `fresh-cohort-fine-shape-confirmation-v1/`, `steerability-age-profile-v1/`, `basin-width-init-variation-v1/`, `history-disambiguation-curve-v1/` |
| `fresh-phase-operator` | `fresh-phase-operator-v1/`: `experiment.py`, `analysis.py`, `results.json`, `results-v2.json`, `results-v3.json`, `analyzed-organisms.jsonl.gz`; use the bound result version |
| `preinjury-recovery-confirmation` | `preinjury-recovery-confirmation-v2/`: `protocol.md`, `freeze.json`, feature/outcome receipts, `features.json`, `outcome-report.json`, `association-report.json`, and extraction/analysis scripts |
| Synthesis age/impedance comparison | `developmental-causal-impedance-v1/`: `experiment.py`, `analysis.py`, `plan.json`, `freeze.json`, `dose-selections.json`, `results.json` |
| Synthesis controller comparison | `developmental-whole-control-tournament-v1/`; follow the synthesis manifest's **corrected** tournament result, which includes the sham comparator |
| Synthesis fingerprint/transplant comparison | `birth-of-causal-individuality-v1/`; original plans, freeze receipt, analysis and response data; the synthesis manifest binds the exact primary and exploration results |

RAW has the corresponding experiment folders with captures, checkpoint state patches, continuations, and native receipts. Plans/completion records link exact runs; do not equate a directory's presence with a complete or qualified cohort. The native implementation is in `CAUSAL/Sources/LeniaCore/` and `Sources/LeniaCLI/`; the standalone campaign scripts import one another, so preserve the full CAMPAIGN tree rather than copying just one `analysis.py`.

The website publication code is `WEB/ops/spctr/src/site/causal_emergence_release.rs` with templates under `WEB/site/templates/dossiers/lenia-swarm/causal-emergence/`. This transforms presentation and bindings; it is not the scientific estimator. Public report/receipt integrity is indexed in `WEB/site/dossiers/lenia-swarm/causal-emergence/reports/manifest.json`.

## HQ coherent-body pilot — separate from the report cohort

`WEB/dossiers/lenia-swarm/docs/coherent-body-pilot.md` gives the protocol and CLI invocation. Code is `WEB/dossiers/lenia-swarm/ops/coherent_body_pilot.py`; completed pilot output is `WEB/dossiers/lenia-swarm/.codex/coherent-body-pilot-v1b/`. Render provenance is `WEB/site/assets/causal-emergence/collection/coherent-bodies.json`.

The three selected bodies and their 24 pilot trials are distinct from the original developmental cohort. Keep their exploratory responses separate from the original age-response estimator. The broader Flow-only organism search remains paused.

## Instructions to the re-analysis model

1. Read the report and original plan together. Identify the independent experimental unit, selection/exclusion rules, primary statistic, uncertainty method, and controls before running analysis.
2. Use the index to find exact sources, then verify hashes against original manifests. Recover a missing source or report the gap; do not infer raw data from plotted values.
3. Recompute published statistics from per-organism/paired trial records first. Separate numerical reproduction from new sensitivity analyses, alternative interpretations, and new experiments.
4. Preserve family/genotype grouping, shared-cohort dependencies, sham corrections, frozen-primary versus post-hoc distinctions, and differences between Flow and additive implementations. Do not treat later website prose edits as new data.
5. Write outputs to a fresh directory and report commands, environment, input hashes, reproduced numbers, discrepancies, and proposed claim revisions. Do not overwrite frozen records, start a new organism search, or publish website changes.
