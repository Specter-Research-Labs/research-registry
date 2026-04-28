module RDGraph

using OrdinaryDiffEq
using Random
using SciMLBase

using ..RD: RDParameters

export RDGraphConfig,
    grid_graph_config,
    grid_node_index,
    make_rd_graph_state,
    direct_rd_graph_step,
    settle_rd_graph!,
    graph_connected_components,
    graph_subconfig,
    graph_substate,
    graph_embed_substate!

Base.@kwdef struct RDGraphConfig
    n_cells::Int
    x::Vector{Float64}
    y::Vector{Float64}
    edges::Vector{NTuple{2,Int}}
    edge_weights::Vector{Float64}
    tspan::Tuple{Float64,Float64} = (0.0, 300.0)
    seed::Int = 0
    steady_tol::Float64 = 1.0e-5
end

function _normalize_graph_edges(
    n_cells::Int,
    edges::Vector{NTuple{2,Int}},
    edge_weights::Vector{Float64},
)
    length(edges) == length(edge_weights) || error("edge_weights must match edges length")
    pairs = Tuple{NTuple{2,Int},Float64}[]
    seen = Set{NTuple{2,Int}}()
    for (edge, weight) in zip(edges, edge_weights)
        left, right = edge
        1 <= left <= n_cells || error("edge endpoint $(left) must be in 1:n_cells")
        1 <= right <= n_cells || error("edge endpoint $(right) must be in 1:n_cells")
        left != right || error("self-edges are not allowed")
        weight > 0 || error("edge weights must be > 0")
        normalized = left < right ? (left, right) : (right, left)
        normalized in seen && error("duplicate undirected edge $(normalized)")
        push!(pairs, (normalized, Float64(weight)))
        push!(seen, normalized)
    end
    sort!(pairs; by=first)
    return [pair[1] for pair in pairs], [pair[2] for pair in pairs]
end

function _validate_rd_graph_config(config::RDGraphConfig)
    config.n_cells >= 1 || error("n_cells must be >= 1")
    length(config.x) == config.n_cells || error("x length must match n_cells")
    length(config.y) == config.n_cells || error("y length must match n_cells")
    config.steady_tol > 0 || error("steady_tol must be > 0")
    config.tspan[2] >= config.tspan[1] || error("tspan end must be >= tspan start")
    edges, weights = _normalize_graph_edges(config.n_cells, config.edges, config.edge_weights)
    return RDGraphConfig(
        n_cells=config.n_cells,
        x=Float64.(config.x),
        y=Float64.(config.y),
        edges=edges,
        edge_weights=weights,
        tspan=config.tspan,
        seed=config.seed,
        steady_tol=config.steady_tol,
    )
end

function _validate_rd_graph_state(state::AbstractVector{<:Real}, config::RDGraphConfig)
    expected_length = 2 * config.n_cells
    length(state) == expected_length || error("expected state length $expected_length for n_cells=$(config.n_cells)")
    return state
end

grid_node_index(rows::Int, cols::Int, row::Int, col::Int) = (row - 1) * cols + col

function grid_graph_config(
    rows::Int,
    cols::Int;
    field_width::Float64=40.0,
    field_height::Float64=40.0,
    severed_edges::Vector{NTuple{2,Int}}=NTuple{2,Int}[],
    tspan::Tuple{Float64,Float64}=(0.0, 300.0),
    seed::Int=0,
    steady_tol::Float64=1.0e-5,
)
    rows >= 1 || error("rows must be >= 1")
    cols >= 1 || error("cols must be >= 1")
    field_width > 0 || error("field_width must be > 0")
    field_height > 0 || error("field_height must be > 0")

    n_cells = rows * cols
    dx = field_width / cols
    dy = field_height / rows
    x = Float64[]
    y = Float64[]
    for row in 1:rows
        for col in 1:cols
            push!(x, (col - 0.5) * dx)
            push!(y, (row - 0.5) * dy)
        end
    end

    removed = Set{NTuple{2,Int}}()
    for edge in severed_edges
        left, right = edge
        normalized = left < right ? (left, right) : (right, left)
        push!(removed, normalized)
    end

    edges = NTuple{2,Int}[]
    weights = Float64[]
    for row in 1:rows
        for col in 1:cols
            node = grid_node_index(rows, cols, row, col)
            if col < cols
                neighbor = grid_node_index(rows, cols, row, col + 1)
                edge = (node, neighbor)
                if edge ∉ removed
                    push!(edges, edge)
                    push!(weights, 1.0 / (dx * dx))
                end
            end
            if row < rows
                neighbor = grid_node_index(rows, cols, row + 1, col)
                edge = (node, neighbor)
                if edge ∉ removed
                    push!(edges, edge)
                    push!(weights, 1.0 / (dy * dy))
                end
            end
        end
    end

    return _validate_rd_graph_config(
        RDGraphConfig(
            n_cells=n_cells,
            x=x,
            y=y,
            edges=edges,
            edge_weights=weights,
            tspan=tspan,
            seed=seed,
            steady_tol=steady_tol,
        ),
    )
end

function make_rd_graph_state(config::RDGraphConfig; rng_seed::Int=config.seed)
    config = _validate_rd_graph_config(config)
    rng = MersenneTwister(rng_seed)
    x_min = minimum(config.x)
    x_span = max(maximum(config.x) - x_min, eps(Float64))
    A = [(config.x[idx] - x_min) / x_span for idx in 1:config.n_cells]
    A .+= 0.002 .* randn(rng, config.n_cells)
    A = clamp.(A, 0.0, Inf)
    I = zeros(config.n_cells)
    return vcat(A, I)
end

function _graph_laplacian!(
    lap::AbstractVector{Float64},
    values::AbstractVector{<:Real},
    config::RDGraphConfig,
)
    fill!(lap, 0.0)
    for (edge, weight) in zip(config.edges, config.edge_weights)
        left, right = edge
        delta = weight * (Float64(values[right]) - Float64(values[left]))
        lap[left] += delta
        lap[right] -= delta
    end
    return lap
end

function direct_rd_graph_step(
    state::AbstractVector{<:Real},
    params::RDParameters,
    config::RDGraphConfig,
)
    config = _validate_rd_graph_config(config)
    _validate_rd_graph_state(state, config)
    n = config.n_cells
    A = @view state[1:n]
    I = @view state[n + 1:end]
    ratio = (I ./ (A .+ 1.0e-20)) .^ params.hill_n
    gen = 1.0 ./ (1.0 .+ ratio)
    lap_a = zeros(Float64, n)
    lap_i = zeros(Float64, n)
    _graph_laplacian!(lap_a, A, config)
    _graph_laplacian!(lap_i, I, config)
    dA = params.gen_a .* gen .- params.decay_a .* A .+ params.D_a .* lap_a
    dI = params.gen_i .* gen .- params.decay_i .* I .+ params.D_i .* lap_i
    return vcat(dA, dI)
end

function _rd_graph_rhs!(du, u, params, t)
    rd_params, rd_config = params
    du .= direct_rd_graph_step(u, rd_params, rd_config)
    return nothing
end

function _steady_state_callback(u0::Vector{Float64}, tol::Float64)
    du = similar(u0)
    condition = function (u, t, integrator)
        integrator.f(du, u, integrator.p, t)
        return maximum(abs, du) <= tol
    end
    affect! = integrator -> SciMLBase.terminate!(integrator)
    return SciMLBase.DiscreteCallback(condition, affect!; save_positions=(false, false))
end

function settle_rd_graph!(
    state::Vector{Float64},
    params::RDParameters,
    config::RDGraphConfig;
    tspan::Tuple{Float64,Float64}=config.tspan,
    steady_stop::Bool=true,
)
    config = _validate_rd_graph_config(config)
    _validate_rd_graph_state(state, config)
    callback = steady_stop ? _steady_state_callback(state, config.steady_tol) : nothing
    problem = ODEProblem(_rd_graph_rhs!, state, tspan, (params, config))
    solution = solve(
        problem,
        Tsit5();
        callback=callback,
        save_everystep=false,
        save_start=false,
        save_end=true,
        dense=false,
        abstol=1.0e-8,
        reltol=1.0e-8,
        maxiters=10_000_000,
    )
    copyto!(state, solution.u[end])
    return solution
end

function _graph_adjacency(config::RDGraphConfig)
    adjacency = [Int[] for _ in 1:config.n_cells]
    for edge in config.edges
        left, right = edge
        push!(adjacency[left], right)
        push!(adjacency[right], left)
    end
    return adjacency
end

function graph_connected_components(config::RDGraphConfig)
    config = _validate_rd_graph_config(config)
    adjacency = _graph_adjacency(config)
    seen = falses(config.n_cells)
    components = Vector{Vector{Int}}()
    for start in 1:config.n_cells
        seen[start] && continue
        queue = [start]
        seen[start] = true
        component = Int[]
        while !isempty(queue)
            node = popfirst!(queue)
            push!(component, node)
            for neighbor in adjacency[node]
                if !seen[neighbor]
                    seen[neighbor] = true
                    push!(queue, neighbor)
                end
            end
        end
        sort!(component)
        push!(components, component)
    end
    sort!(components; by=component -> (length(component), component[1]))
    return components
end

function graph_subconfig(config::RDGraphConfig, nodes::Vector{Int})
    config = _validate_rd_graph_config(config)
    !isempty(nodes) || error("nodes must be non-empty")
    sorted_nodes = sort(unique(nodes))
    all(1 <= node <= config.n_cells for node in sorted_nodes) || error("nodes must lie in 1:n_cells")
    index_map = Dict(node => idx for (idx, node) in enumerate(sorted_nodes))
    edges = NTuple{2,Int}[]
    weights = Float64[]
    node_set = Set(sorted_nodes)
    for (edge, weight) in zip(config.edges, config.edge_weights)
        left, right = edge
        if left in node_set && right in node_set
            push!(edges, (index_map[left], index_map[right]))
            push!(weights, weight)
        end
    end
    return _validate_rd_graph_config(
        RDGraphConfig(
            n_cells=length(sorted_nodes),
            x=config.x[sorted_nodes],
            y=config.y[sorted_nodes],
            edges=edges,
            edge_weights=weights,
            tspan=config.tspan,
            seed=config.seed,
            steady_tol=config.steady_tol,
        ),
    )
end

function graph_substate(
    state::AbstractVector{<:Real},
    config::RDGraphConfig,
    nodes::Vector{Int},
)
    config = _validate_rd_graph_config(config)
    _validate_rd_graph_state(state, config)
    sorted_nodes = sort(unique(nodes))
    A = collect(@view state[sorted_nodes])
    I = collect(@view state[config.n_cells .+ sorted_nodes])
    return vcat(A, I)
end

function graph_embed_substate!(
    state::Vector{Float64},
    substate::AbstractVector{<:Real},
    config::RDGraphConfig,
    nodes::Vector{Int},
)
    config = _validate_rd_graph_config(config)
    _validate_rd_graph_state(state, config)
    sorted_nodes = sort(unique(nodes))
    expected_length = 2 * length(sorted_nodes)
    length(substate) == expected_length || error("substate length $expected_length expected for $(length(sorted_nodes)) nodes")
    offset = length(sorted_nodes)
    for (idx, node) in enumerate(sorted_nodes)
        state[node] = substate[idx]
        state[config.n_cells + node] = substate[offset + idx]
    end
    return state
end

end
