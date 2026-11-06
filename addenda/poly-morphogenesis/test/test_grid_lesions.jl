using PolyMorphogenesis
using Test

@testset "rectangle isolation severs only the patch boundary" begin
    edges = isolate_rectangle_edges(4, 5, 2, 3, 2, 2)
    expected = sort(map(edge -> edge[1] < edge[2] ? edge : (edge[2], edge[1]), [
        (grid_node_index(4, 5, 1, 3), grid_node_index(4, 5, 2, 3)),
        (grid_node_index(4, 5, 1, 4), grid_node_index(4, 5, 2, 4)),
        (grid_node_index(4, 5, 2, 2), grid_node_index(4, 5, 2, 3)),
        (grid_node_index(4, 5, 2, 4), grid_node_index(4, 5, 2, 5)),
        (grid_node_index(4, 5, 3, 2), grid_node_index(4, 5, 3, 3)),
        (grid_node_index(4, 5, 3, 4), grid_node_index(4, 5, 3, 5)),
        (grid_node_index(4, 5, 4, 3), grid_node_index(4, 5, 3, 3)),
        (grid_node_index(4, 5, 4, 4), grid_node_index(4, 5, 3, 4)),
    ]))
    @test edges == expected
end

@testset "grid patch placements enumerate valid positions" begin
    placements = grid_patch_placements(3, 4, 2, 2)
    @test length(placements) == 6
    @test placements[1].top == 1
    @test placements[1].left == 1
    @test placements[end].top == 2
    @test placements[end].left == 3
    @test all(length(entry.nodes) == 4 for entry in placements)
end

@testset "graph morphology uses a fixed absolute threshold" begin
    config = grid_graph_config(2, 3)
    state = vcat([0.8, 0.7, 0.1, 0.9, 0.2, 0.8], fill(0.25, 6))
    snapshot = PolyMorphogenesis.GridLesions.graph_morphology_snapshot(
        state,
        config;
        threshold=0.5,
    )

    @test snapshot.active_mask == BitVector([true, true, false, true, false, true])
    @test snapshot.active_cell_count == 4
    @test snapshot.component_count == 2
    @test snapshot.A == state[1:6]
    @test snapshot.I == state[7:12]
    @test PolyMorphogenesis.GridLesions.graph_active_domain_count(config, snapshot.active_mask) == 2
end

@testset "relative graph snapshots delegate without changing morphology" begin
    config = grid_graph_config(1, 4)
    state = vcat([10.0, 7.0, 4.0, 1.0], [1.0, 2.0, 3.0, 4.0])
    relative = PolyMorphogenesis.GridLesions._graph_snapshot(state, config; active_fraction=0.5)
    fixed = PolyMorphogenesis.GridLesions.graph_morphology_snapshot(state, config; threshold=5.0)

    @test relative.component_count == fixed.component_count
    @test relative.active_cell_count == fixed.active_cell_count
    @test relative.active_mask == fixed.active_mask
    @test relative.A == fixed.A
    @test relative.I == fixed.I
    @test_throws ErrorException PolyMorphogenesis.GridLesions.graph_active_domain_count(config, trues(3))
    @test_throws ErrorException PolyMorphogenesis.GridLesions.graph_morphology_snapshot(
        zeros(7),
        config;
        threshold=0.5,
    )
end

@testset "patch-isolation demo produces severity and connectivity rankings" begin
    result = grid_patch_isolation_demo(
        rows=3,
        cols=4,
        patch_rows=1,
        patch_cols=1,
        seed=0,
        D_a=1.0,
        D_i=30.0,
        steady_stop=false,
        validate=false,
    )
    @test result.rows == 3
    @test result.cols == 4
    @test length(result.evaluations) == 12
    @test length(result.ranking_connectivity) == 12
    @test length(result.ranking_severity) == 12
    @test all(entry.disconnected_pairs == 11 for entry in result.evaluations)
    @test all(0.0 <= entry.severity_score <= 1.0 for entry in result.evaluations)
    @test result.validation === nothing
end

@testset "grid patch placements reject impossible patch sizes" begin
    @test_throws ErrorException grid_patch_placements(3, 4, 4, 1)
    @test_throws ErrorException grid_patch_placements(3, 4, 1, 5)
end

@testset "grid patch sweep reports severity spread inside connectivity ties" begin
    result = grid_patch_sweep_demo(
        rows=4,
        cols=6,
        patch_sizes=[(2, 2)],
        D_a_values=[1.0],
        D_i_values=[30.0],
        seed=33,
        steady_stop=false,
    )
    @test length(result.cases) == 1
    case = only(result.cases)
    @test case.connectivity_flat
    @test case.distinct_connectivity_scores == 1
    @test case.largest_connectivity_tie_size == 15
    @test case.largest_connectivity_tie_severity_span > 0.0
    @test case.global_severity_span >= case.largest_connectivity_tie_severity_span
    @test case.top_severity_margin > 0.0
end

@testset "grid patch metric sensitivity compares alternative severity policies" begin
    result = grid_patch_metric_sensitivity_demo(
        rows=4,
        cols=6,
        patch_rows=2,
        patch_cols=2,
        D_a=1.0,
        D_i=30.0,
        seed=33,
        steady_stop=false,
        metrics=[:balanced, :structure, :profile],
    )
    @test length(result.cases) == 3
    @test Set(case.metric for case in result.cases) == Set([:balanced, :structure, :profile])
    @test all(case.connectivity_flat for case in result.cases)
    @test all(case.largest_connectivity_tie_severity_span > 0.0 for case in result.cases)
end

@testset "grid patch threshold sensitivity compares active-mask thresholds" begin
    result = grid_patch_threshold_sensitivity_demo(
        rows=4,
        cols=6,
        patch_rows=2,
        patch_cols=2,
        D_a=1.0,
        D_i=30.0,
        seed=33,
        active_fractions=[0.4, 0.5, 0.6],
        metrics=[:balanced, :structure, :profile],
        steady_stop=false,
    )
    @test length(result.cases) == 9
    @test Set(case.metric for case in result.cases) == Set([:balanced, :structure, :profile])
    @test Set(case.active_fraction for case in result.cases) == Set([0.4, 0.5, 0.6])
    @test all(case.connectivity_flat for case in result.cases)
    @test all(case.largest_connectivity_tie_severity_span > 0.0 for case in result.cases)
end
