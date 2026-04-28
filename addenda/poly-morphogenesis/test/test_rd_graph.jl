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
