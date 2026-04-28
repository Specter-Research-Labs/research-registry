module PolyMorphogenesis

include("algebra.jl")
include("rd.jl")
include("rd_graph.jl")
include("grid_lesions.jl")
include("wave.jl")
include("controller.jl")
include("wiring.jl")
include("diagrams.jl")
include("cli.jl")

using .RD: RDParameters,
    RDChainConfig,
    spread_pattern!,
    linear_spread!,
    preseed_lxh!,
    settle_rd_source!,
    settle_rd_composed!
using .RDGraph: RDGraphConfig,
    grid_graph_config,
    grid_node_index,
    make_rd_graph_state,
    direct_rd_graph_step,
    settle_rd_graph!,
    graph_connected_components,
    graph_subconfig,
    graph_substate,
    graph_embed_substate!
using .GridLesions: GraphMorphologySnapshot,
    GridPatchPlacement,
    GridLesionEvaluation,
    GridPatchIsolationResult,
    GridPatchSweepCase,
    GridPatchSweepResult,
    GridMetricSensitivityCase,
    GridPatchMetricSensitivityResult,
    GridThresholdSensitivityCase,
    GridPatchThresholdSensitivityResult,
    isolate_rectangle_edges,
    grid_patch_placements,
    grid_patch_isolation_demo,
    grid_patch_sweep_demo,
    grid_patch_metric_sensitivity_demo,
    grid_patch_threshold_sensitivity_demo
using .Wave: WaveConfig, wave_count
using .Controller: ClosedLoopConfig,
    compile_closed_loop_machine,
    run_closed_loop_machine,
    closed_loop
using .Wiring: cut_connectivity_loss,
    wiring_cut_sweep_demo,
    wiring_fragment_family_demo,
    wiring_severity_phase_scan_demo,
    wiring_intervention_k_demo,
    wiring_intervention_order,
    wiring_bistability_demo
using .Diagrams: save_diagrams
using .CLI: main

export RDParameters,
    RDChainConfig,
    RDGraphConfig,
    GraphMorphologySnapshot,
    GridPatchPlacement,
    GridLesionEvaluation,
    GridPatchIsolationResult,
    GridPatchSweepCase,
    GridPatchSweepResult,
    GridMetricSensitivityCase,
    GridPatchMetricSensitivityResult,
    GridThresholdSensitivityCase,
    GridPatchThresholdSensitivityResult,
    spread_pattern!,
    linear_spread!,
    preseed_lxh!,
    settle_rd_source!,
    settle_rd_composed!,
    grid_graph_config,
    grid_node_index,
    make_rd_graph_state,
    direct_rd_graph_step,
    settle_rd_graph!,
    graph_connected_components,
    graph_subconfig,
    graph_substate,
    graph_embed_substate!,
    isolate_rectangle_edges,
    grid_patch_placements,
    grid_patch_isolation_demo,
    grid_patch_sweep_demo,
    grid_patch_metric_sensitivity_demo,
    grid_patch_threshold_sensitivity_demo,
    WaveConfig,
    ClosedLoopConfig,
    wave_count,
    compile_closed_loop_machine,
    run_closed_loop_machine,
    closed_loop,
    cut_connectivity_loss,
    wiring_intervention_order,
    wiring_cut_sweep_demo,
    wiring_fragment_family_demo,
    wiring_severity_phase_scan_demo,
    wiring_intervention_k_demo,
    wiring_bistability_demo,
    save_diagrams,
    main

end
