using PolyMorphogenesis
using Test

@testset "grid graph config builds weighted 2D adjacency" begin
    config = grid_graph_config(3, 4, field_width=8.0, field_height=6.0)
    @test config.n_cells == 12
    @test length(config.edges) == 17
    @test length(config.edge_weights) == 17
    @test grid_node_index(3, 4, 2, 3) == 7
    @test all(weight > 0 for weight in config.edge_weights)
end

@testset "graph RD step is finite and dimensionally consistent" begin
    params = RDParameters()
    config = grid_graph_config(2, 3, field_width=6.0, field_height=4.0, seed=3)
    state = make_rd_graph_state(config; rng_seed=3)
    delta = direct_rd_graph_step(state, params, config)
    @test length(delta) == length(state)
    @test all(isfinite, delta)
end

@testset "graph edge removal preserves graph metadata and edge weights" begin
    config = grid_graph_config(
        2,
        3;
        field_width=9.0,
        field_height=4.0,
        tspan=(2.0, 17.0),
        seed=19,
        steady_tol=2.0e-6,
    )
    removed_edge = (grid_node_index(2, 3, 2, 1), grid_node_index(2, 3, 1, 1))
    severed = PolyMorphogenesis.RDGraph.graph_without_edges(config, [removed_edge])
    normalized = (removed_edge[2], removed_edge[1])
    retained_indices = findall(!=(normalized), config.edges)

    @test severed.n_cells == config.n_cells
    @test severed.x == config.x
    @test severed.y == config.y
    @test severed.edges == config.edges[retained_indices]
    @test severed.edge_weights == config.edge_weights[retained_indices]
    @test severed.tspan == config.tspan
    @test severed.seed == config.seed
    @test severed.steady_tol == config.steady_tol
    @test normalized in config.edges
    @test normalized ∉ severed.edges
end

@testset "graph edge removal rejects absent edges" begin
    config = grid_graph_config(2, 2)
    @test_throws ErrorException PolyMorphogenesis.RDGraph.graph_without_edges(config, [(1, 4)])
    @test_throws ErrorException PolyMorphogenesis.RDGraph.graph_without_edges(
        config,
        [(1, 2), (2, 1)],
    )
end

@testset "severed 2D grid factorizes over disconnected components" begin
    severed_edges = NTuple{2,Int}[
        (grid_node_index(2, 4, 1, 2), grid_node_index(2, 4, 1, 3)),
        (grid_node_index(2, 4, 2, 2), grid_node_index(2, 4, 2, 3)),
    ]
    config = grid_graph_config(
        2,
        4;
        field_width=8.0,
        field_height=4.0,
        severed_edges=severed_edges,
        tspan=(0.0, 20.0),
        seed=11,
    )
    params = RDParameters()
    initial_state = make_rd_graph_state(config; rng_seed=11)

    components = graph_connected_components(config)
    @test components == [[1, 2, 5, 6], [3, 4, 7, 8]]

    full_state = copy(initial_state)
    settle_rd_graph!(full_state, params, config; steady_stop=false)

    factorized_state = zeros(Float64, length(full_state))
    for component in components
        subconfig = graph_subconfig(config, component)
        substate = graph_substate(initial_state, config, component)
        settle_rd_graph!(substate, params, subconfig; steady_stop=false)
        graph_embed_substate!(factorized_state, substate, config, component)
    end

    @test factorized_state ≈ full_state atol=1.0e-8
end
