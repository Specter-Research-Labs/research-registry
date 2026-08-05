module GridLesions

using ..RD: RDParameters
using ..RDGraph: RDGraphConfig,
    graph_connected_components,
    graph_embed_substate!,
    graph_subconfig,
    graph_substate,
    grid_graph_config,
    grid_node_index,
    make_rd_graph_state,
    settle_rd_graph!

export GraphMorphologySnapshot,
    GridPatchPlacement,
    GridLesionEvaluation,
    GridPatchIsolationResult,
    GridPatchSweepCase,
    GridPatchSweepResult,
    GridMetricSensitivityCase,
    GridPatchMetricSensitivityResult,
    GridThresholdSensitivityCase,
    GridPatchThresholdSensitivityResult,
    graph_active_domain_count,
    graph_morphology_snapshot,
    isolate_rectangle_edges,
    grid_patch_placements,
    grid_patch_isolation_demo,
    grid_patch_sweep_demo,
    grid_patch_metric_sensitivity_demo,
    grid_patch_threshold_sensitivity_demo

struct GraphMorphologySnapshot
    component_count::Int
    active_cell_count::Int
    active_mask::BitVector
    A::Vector{Float64}
    I::Vector{Float64}
end

struct GridPatchPlacement
    top::Int
    left::Int
    height::Int
    width::Int
    nodes::Vector{Int}
    severed_edges::Vector{NTuple{2,Int}}
end

Base.@kwdef mutable struct GridLesionEvaluation
    placement::GridPatchPlacement
    severed_component_sizes::Vector{Int}
    disconnected_pairs::Int
    component_count::Int
    active_cell_count::Int
    active_cell_delta_abs::Int
    profile_l1_mean::Float64
    profile_l2_rms::Float64
    active_mask_hamming_fraction::Float64
    component_delta_abs::Int
    severity_score::Float64 = 0.0
end

struct FactorizationCheck
    top::Int
    left::Int
    profile_linf_error::Float64
    active_mask_match::Bool
    component_count_error::Int
end

struct GridPatchIsolationResult
    rows::Int
    cols::Int
    patch_rows::Int
    patch_cols::Int
    seed::Int
    D_a::Float64
    connected::GraphMorphologySnapshot
    evaluations::Vector{GridLesionEvaluation}
    ranking_connectivity::Vector{GridLesionEvaluation}
    ranking_severity::Vector{GridLesionEvaluation}
    validation::Union{Nothing,Vector{FactorizationCheck}}
end

struct GridPatchSweepCase
    rows::Int
    cols::Int
    patch_rows::Int
    patch_cols::Int
    seed::Int
    D_a::Float64
    D_i::Float64
    placement_count::Int
    distinct_connectivity_scores::Int
    connectivity_flat::Bool
    largest_connectivity_tie_score::Int
    largest_connectivity_tie_size::Int
    largest_connectivity_tie_severity_span::Float64
    global_severity_span::Float64
    top_severity_margin::Float64
    top_severity_top::Int
    top_severity_left::Int
    top_connectivity_top::Int
    top_connectivity_left::Int
end

struct GridPatchSweepResult
    rows::Int
    cols::Int
    seed::Int
    D_a_values::Vector{Float64}
    D_i_values::Vector{Float64}
    patch_sizes::Vector{Tuple{Int,Int}}
    cases::Vector{GridPatchSweepCase}
    ranking_tie_span::Vector{GridPatchSweepCase}
end

struct GridMetricSensitivityCase
    metric::Symbol
    placement_count::Int
    distinct_connectivity_scores::Int
    connectivity_flat::Bool
    largest_connectivity_tie_score::Int
    largest_connectivity_tie_size::Int
    largest_connectivity_tie_severity_span::Float64
    global_severity_span::Float64
    top_severity_margin::Float64
    top_severity_top::Int
    top_severity_left::Int
    top_connectivity_top::Int
    top_connectivity_left::Int
end

struct GridPatchMetricSensitivityResult
    rows::Int
    cols::Int
    patch_rows::Int
    patch_cols::Int
    seed::Int
    D_a::Float64
    D_i::Float64
    metrics::Vector{Symbol}
    cases::Vector{GridMetricSensitivityCase}
end

struct GridThresholdSensitivityCase
    active_fraction::Float64
    metric::Symbol
    placement_count::Int
    distinct_connectivity_scores::Int
    connectivity_flat::Bool
    largest_connectivity_tie_score::Int
    largest_connectivity_tie_size::Int
    largest_connectivity_tie_severity_span::Float64
    global_severity_span::Float64
    top_severity_margin::Float64
    top_severity_top::Int
    top_severity_left::Int
    top_connectivity_top::Int
    top_connectivity_left::Int
end

struct GridPatchThresholdSensitivityResult
    rows::Int
    cols::Int
    patch_rows::Int
    patch_cols::Int
    seed::Int
    D_a::Float64
    D_i::Float64
    active_fractions::Vector{Float64}
    metrics::Vector{Symbol}
    cases::Vector{GridThresholdSensitivityCase}
end

function _grid_neighbors(rows::Int, cols::Int, row::Int, col::Int)
    neighbors = NTuple{2,Int}[]
    row > 1 && push!(neighbors, (row - 1, col))
    row < rows && push!(neighbors, (row + 1, col))
    col > 1 && push!(neighbors, (row, col - 1))
    col < cols && push!(neighbors, (row, col + 1))
    return neighbors
end

function _rectangle_node_set(rows::Int, cols::Int, top::Int, left::Int, height::Int, width::Int)
    1 <= top <= rows || error("top must lie in 1:rows")
    1 <= left <= cols || error("left must lie in 1:cols")
    height >= 1 || error("height must be >= 1")
    width >= 1 || error("width must be >= 1")
    top + height - 1 <= rows || error("rectangle extends past bottom boundary")
    left + width - 1 <= cols || error("rectangle extends past right boundary")
    nodes = Int[]
    for row in top:(top + height - 1)
        for col in left:(left + width - 1)
            push!(nodes, grid_node_index(rows, cols, row, col))
        end
    end
    return sort(nodes)
end

function isolate_rectangle_edges(rows::Int, cols::Int, top::Int, left::Int, height::Int, width::Int)
    nodes = Set(_rectangle_node_set(rows, cols, top, left, height, width))
    severed = Set{NTuple{2,Int}}()
    for row in top:(top + height - 1)
        for col in left:(left + width - 1)
            node = grid_node_index(rows, cols, row, col)
            for (nbr_row, nbr_col) in _grid_neighbors(rows, cols, row, col)
                neighbor = grid_node_index(rows, cols, nbr_row, nbr_col)
                if neighbor ∉ nodes
                    edge = node < neighbor ? (node, neighbor) : (neighbor, node)
                    push!(severed, edge)
                end
            end
        end
    end
    return sort(collect(severed))
end

function grid_patch_placements(rows::Int, cols::Int, patch_rows::Int, patch_cols::Int)
    patch_rows >= 1 || error("patch_rows must be >= 1")
    patch_cols >= 1 || error("patch_cols must be >= 1")
    patch_rows <= rows || error("patch_rows must be <= rows")
    patch_cols <= cols || error("patch_cols must be <= cols")
    placements = GridPatchPlacement[]
    for top in 1:(rows - patch_rows + 1)
        for left in 1:(cols - patch_cols + 1)
            nodes = _rectangle_node_set(rows, cols, top, left, patch_rows, patch_cols)
            push!(
                placements,
                GridPatchPlacement(
                    top,
                    left,
                    patch_rows,
                    patch_cols,
                    nodes,
                    isolate_rectangle_edges(rows, cols, top, left, patch_rows, patch_cols),
                ),
            )
        end
    end
    return placements
end

function graph_active_domain_count(config::RDGraphConfig, active_mask::AbstractVector{Bool})
    length(active_mask) == config.n_cells || error("active_mask length must match n_cells")
    adjacency = [Int[] for _ in 1:config.n_cells]
    for edge in config.edges
        left, right = edge
        if active_mask[left] && active_mask[right]
            push!(adjacency[left], right)
            push!(adjacency[right], left)
        end
    end

    seen = falses(config.n_cells)
    count = 0
    for node in 1:config.n_cells
        (!active_mask[node] || seen[node]) && continue
        count += 1
        queue = [node]
        seen[node] = true
        while !isempty(queue)
            current = popfirst!(queue)
            for neighbor in adjacency[current]
                if !seen[neighbor]
                    seen[neighbor] = true
                    push!(queue, neighbor)
                end
            end
        end
    end
    return count
end

function graph_morphology_snapshot(
    state::Vector{Float64},
    config::RDGraphConfig;
    threshold::Float64,
)
    expected_length = 2 * config.n_cells
    length(state) == expected_length || error("expected state length $expected_length for n_cells=$(config.n_cells)")
    n = config.n_cells
    A = collect(@view state[1:n])
    I = collect(@view state[n + 1:end])
    active_mask = BitVector(A .>= threshold)
    return GraphMorphologySnapshot(
        graph_active_domain_count(config, active_mask),
        count(identity, active_mask),
        active_mask,
        A,
        I,
    )
end

function _graph_snapshot(state::Vector{Float64}, config::RDGraphConfig; active_fraction::Float64=0.5)
    active_fraction > 0 || error("active_fraction must be > 0")
    n = config.n_cells
    threshold = active_fraction * maximum(@view state[1:n])
    return graph_morphology_snapshot(state, config; threshold=threshold)
end

function _settled_graph_snapshot(
    initial_state::Vector{Float64},
    params::RDParameters,
    config::RDGraphConfig;
    steady_stop::Bool=true,
    active_fraction::Float64=0.5,
)
    state = copy(initial_state)
    settle_rd_graph!(state, params, config; steady_stop=steady_stop)
    return _graph_snapshot(state, config; active_fraction=active_fraction)
end

function _factorized_graph_snapshot(
    initial_state::Vector{Float64},
    params::RDParameters,
    config::RDGraphConfig;
    steady_stop::Bool=true,
    active_fraction::Float64=0.5,
)
    state = zeros(Float64, length(initial_state))
    for component in graph_connected_components(config)
        subconfig = graph_subconfig(config, component)
        substate = graph_substate(initial_state, config, component)
        settle_rd_graph!(substate, params, subconfig; steady_stop=steady_stop)
        graph_embed_substate!(state, substate, config, component)
    end
    return _graph_snapshot(state, config; active_fraction=active_fraction)
end

function _mean_abs_difference(left::Vector{Float64}, right::Vector{Float64})
    length(left) == length(right) || error("profiles must have the same length")
    return sum(abs.(left .- right)) / length(left)
end

function _root_mean_squared_difference(left::Vector{Float64}, right::Vector{Float64})
    length(left) == length(right) || error("profiles must have the same length")
    return sqrt(sum((left .- right) .^ 2) / length(left))
end

function _mask_hamming_fraction(left::BitVector, right::BitVector)
    length(left) == length(right) || error("masks must have the same length")
    mismatches = count(i -> left[i] != right[i], eachindex(left))
    return mismatches / length(left)
end

function _disconnected_pairs(component_sizes::Vector{Int})
    total = sum(component_sizes)
    within = sum(size * (size - 1) ÷ 2 for size in component_sizes)
    return total * (total - 1) ÷ 2 - within
end

function _normalized(value::Real, max_value::Real)
    max_value == 0 && return 0.0
    return Float64(value) / Float64(max_value)
end

function _clone_evaluations(evaluations::Vector{GridLesionEvaluation})
    return [
        GridLesionEvaluation(
            placement=entry.placement,
            severed_component_sizes=copy(entry.severed_component_sizes),
            disconnected_pairs=entry.disconnected_pairs,
            component_count=entry.component_count,
            active_cell_count=entry.active_cell_count,
            active_cell_delta_abs=entry.active_cell_delta_abs,
            profile_l1_mean=entry.profile_l1_mean,
            profile_l2_rms=entry.profile_l2_rms,
            active_mask_hamming_fraction=entry.active_mask_hamming_fraction,
            component_delta_abs=entry.component_delta_abs,
            severity_score=entry.severity_score,
        ) for entry in evaluations
    ]
end

function _metric_components(entry::GridLesionEvaluation, metric::Symbol)
    if metric == :balanced
        return (
            entry.component_delta_abs,
            entry.profile_l1_mean,
            entry.active_mask_hamming_fraction,
        )
    elseif metric == :structure
        return (
            entry.component_delta_abs,
            entry.active_cell_delta_abs,
            entry.active_mask_hamming_fraction,
        )
    elseif metric == :profile
        return (
            entry.profile_l1_mean,
            entry.profile_l2_rms,
            entry.active_mask_hamming_fraction,
        )
    end
    error("unknown grid lesion severity metric: $metric")
end

function _calibrate_severity!(evaluations::Vector{GridLesionEvaluation}, metric::Symbol)
    maxima = ntuple(
        idx -> maximum(_metric_components(entry, metric)[idx] for entry in evaluations),
        3,
    )
    for entry in evaluations
        components = _metric_components(entry, metric)
        entry.severity_score =
            sum(_normalized(components[idx], maxima[idx]) for idx in 1:3) / 3
    end
    return evaluations
end

function _metric_rankings(evaluations::Vector{GridLesionEvaluation}, metric::Symbol)
    scored = _clone_evaluations(evaluations)
    _calibrate_severity!(scored, metric)
    ranking_severity = sort(
        copy(scored);
        by=entry -> (-entry.severity_score, -entry.profile_l1_mean, entry.placement.top, entry.placement.left),
    )
    return scored, ranking_severity
end

function _metric_sensitivity_case(
    evaluations::Vector{GridLesionEvaluation},
    ranking_connectivity::Vector{GridLesionEvaluation},
    metric::Symbol,
)
    scored, ranking_severity = _metric_rankings(evaluations, metric)
    tie_score, tie_group = _largest_connectivity_tie(scored)
    distinct_scores = length(unique(entry.disconnected_pairs for entry in scored))
    return GridMetricSensitivityCase(
        metric,
        length(scored),
        distinct_scores,
        distinct_scores == 1,
        tie_score,
        length(tie_group),
        _severity_span(tie_group),
        _severity_span(scored),
        _top_margin(ranking_severity),
        ranking_severity[1].placement.top,
        ranking_severity[1].placement.left,
        ranking_connectivity[1].placement.top,
        ranking_connectivity[1].placement.left,
    )
end

function _threshold_sensitivity_case(
    active_fraction::Float64,
    evaluations::Vector{GridLesionEvaluation},
    ranking_connectivity::Vector{GridLesionEvaluation},
    metric::Symbol,
)
    metric_case = _metric_sensitivity_case(evaluations, ranking_connectivity, metric)
    return GridThresholdSensitivityCase(
        active_fraction,
        metric_case.metric,
        metric_case.placement_count,
        metric_case.distinct_connectivity_scores,
        metric_case.connectivity_flat,
        metric_case.largest_connectivity_tie_score,
        metric_case.largest_connectivity_tie_size,
        metric_case.largest_connectivity_tie_severity_span,
        metric_case.global_severity_span,
        metric_case.top_severity_margin,
        metric_case.top_severity_top,
        metric_case.top_severity_left,
        metric_case.top_connectivity_top,
        metric_case.top_connectivity_left,
    )
end

function _largest_connectivity_tie(evaluations::Vector{GridLesionEvaluation})
    groups = Dict{Int,Vector{GridLesionEvaluation}}()
    for entry in evaluations
        push!(get!(groups, entry.disconnected_pairs, GridLesionEvaluation[]), entry)
    end

    best_score = typemin(Int)
    best_group = GridLesionEvaluation[]
    for (score, group) in groups
        if length(group) > length(best_group) || (length(group) == length(best_group) && score > best_score)
            best_score = score
            best_group = group
        end
    end
    return best_score, best_group
end

function _severity_span(evaluations::Vector{GridLesionEvaluation})
    isempty(evaluations) && return 0.0
    severities = [entry.severity_score for entry in evaluations]
    return maximum(severities) - minimum(severities)
end

function _top_margin(evaluations::Vector{GridLesionEvaluation})
    length(evaluations) <= 1 && return 0.0
    return evaluations[1].severity_score - evaluations[2].severity_score
end

function _factorization_check(
    placement::GridPatchPlacement,
    initial_state::Vector{Float64},
    params::RDParameters,
    config::RDGraphConfig;
    steady_stop::Bool=true,
    active_fraction::Float64=0.5,
)
    direct = _settled_graph_snapshot(initial_state, params, config; steady_stop=steady_stop, active_fraction=active_fraction)
    factorized = _factorized_graph_snapshot(initial_state, params, config; steady_stop=steady_stop, active_fraction=active_fraction)
    return FactorizationCheck(
        placement.top,
        placement.left,
        maximum(abs.(direct.A .- factorized.A)),
        direct.active_mask == factorized.active_mask,
        abs(direct.component_count - factorized.component_count),
    )
end

function grid_patch_isolation_demo(;
    rows::Int=8,
    cols::Int=8,
    patch_rows::Int=2,
    patch_cols::Int=2,
    field_width::Float64=40.0,
    field_height::Float64=40.0,
    seed::Int=0,
    D_a::Float64=1.0,
    D_i::Float64=30.0,
    steady_stop::Bool=true,
    active_fraction::Float64=0.5,
    validate::Bool=false,
)
    placements = grid_patch_placements(rows, cols, patch_rows, patch_cols)
    connected_config = grid_graph_config(
        rows,
        cols;
        field_width=field_width,
        field_height=field_height,
        seed=seed,
    )
    initial_state = make_rd_graph_state(connected_config; rng_seed=seed)
    params = RDParameters(D_a=D_a, D_i=D_i)
    connected = _settled_graph_snapshot(initial_state, params, connected_config; steady_stop=steady_stop, active_fraction=active_fraction)

    evaluations = GridLesionEvaluation[]
    checks = validate ? FactorizationCheck[] : nothing
    for placement in placements
        severed_config = grid_graph_config(
            rows,
            cols;
            field_width=field_width,
            field_height=field_height,
            severed_edges=placement.severed_edges,
            seed=seed,
        )
        severed = _factorized_graph_snapshot(initial_state, params, severed_config; steady_stop=steady_stop, active_fraction=active_fraction)
        component_sizes = sort([length(component) for component in graph_connected_components(severed_config)])
        push!(
            evaluations,
            GridLesionEvaluation(
                placement=placement,
                severed_component_sizes=component_sizes,
                disconnected_pairs=_disconnected_pairs(component_sizes),
                component_count=severed.component_count,
                active_cell_count=severed.active_cell_count,
                active_cell_delta_abs=abs(severed.active_cell_count - connected.active_cell_count),
                profile_l1_mean=_mean_abs_difference(severed.A, connected.A),
                profile_l2_rms=_root_mean_squared_difference(severed.A, connected.A),
                active_mask_hamming_fraction=_mask_hamming_fraction(severed.active_mask, connected.active_mask),
                component_delta_abs=abs(severed.component_count - connected.component_count),
            ),
        )
        if validate
            push!(
                checks,
                _factorization_check(
                    placement,
                    initial_state,
                    params,
                    severed_config;
                    steady_stop=steady_stop,
                    active_fraction=active_fraction,
                ),
            )
        end
    end

    _calibrate_severity!(evaluations, :balanced)

    ranking_connectivity = sort(
        copy(evaluations);
        by=entry -> (-entry.disconnected_pairs, entry.placement.top, entry.placement.left),
    )
    ranking_severity = sort(
        copy(evaluations);
        by=entry -> (-entry.severity_score, -entry.profile_l1_mean, entry.placement.top, entry.placement.left),
    )

    return GridPatchIsolationResult(
        rows,
        cols,
        patch_rows,
        patch_cols,
        seed,
        D_a,
        connected,
        evaluations,
        ranking_connectivity,
        ranking_severity,
        checks,
    )
end

function grid_patch_sweep_demo(;
    rows::Int=8,
    cols::Int=8,
    patch_sizes::Vector{Tuple{Int,Int}}=[(1, 1), (2, 2), (2, 3)],
    D_a_values::Vector{Float64}=[1.0],
    D_i_values::Vector{Float64}=[30.0],
    field_width::Float64=40.0,
    field_height::Float64=40.0,
    seed::Int=0,
    steady_stop::Bool=true,
    active_fraction::Float64=0.5,
)
    isempty(patch_sizes) && error("patch_sizes must not be empty")
    isempty(D_a_values) && error("D_a_values must not be empty")
    isempty(D_i_values) && error("D_i_values must not be empty")

    cases = GridPatchSweepCase[]
    for (patch_rows, patch_cols) in patch_sizes
        for D_a in D_a_values
            for D_i in D_i_values
                result = grid_patch_isolation_demo(
                    rows=rows,
                    cols=cols,
                    patch_rows=patch_rows,
                    patch_cols=patch_cols,
                    field_width=field_width,
                    field_height=field_height,
                    seed=seed,
                    D_a=D_a,
                    D_i=D_i,
                    steady_stop=steady_stop,
                    active_fraction=active_fraction,
                    validate=false,
                )
                tie_score, tie_group = _largest_connectivity_tie(result.evaluations)
                push!(
                    cases,
                    GridPatchSweepCase(
                        rows,
                        cols,
                        patch_rows,
                        patch_cols,
                        seed,
                        D_a,
                        D_i,
                        length(result.evaluations),
                        length(unique(entry.disconnected_pairs for entry in result.evaluations)),
                        length(unique(entry.disconnected_pairs for entry in result.evaluations)) == 1,
                        tie_score,
                        length(tie_group),
                        _severity_span(tie_group),
                        _severity_span(result.evaluations),
                        _top_margin(result.ranking_severity),
                        result.ranking_severity[1].placement.top,
                        result.ranking_severity[1].placement.left,
                        result.ranking_connectivity[1].placement.top,
                        result.ranking_connectivity[1].placement.left,
                    ),
                )
            end
        end
    end

    ranking_tie_span = sort(
        copy(cases);
        by=entry -> (
            -entry.largest_connectivity_tie_severity_span,
            -entry.top_severity_margin,
            entry.patch_rows,
            entry.patch_cols,
            entry.D_a,
            entry.D_i,
        ),
    )

    return GridPatchSweepResult(rows, cols, seed, copy(D_a_values), copy(D_i_values), copy(patch_sizes), cases, ranking_tie_span)
end

function grid_patch_metric_sensitivity_demo(;
    rows::Int=8,
    cols::Int=8,
    patch_rows::Int=2,
    patch_cols::Int=2,
    field_width::Float64=40.0,
    field_height::Float64=40.0,
    seed::Int=0,
    D_a::Float64=1.0,
    D_i::Float64=30.0,
    steady_stop::Bool=true,
    active_fraction::Float64=0.5,
    metrics::Vector{Symbol}=[:balanced, :structure, :profile],
)
    isempty(metrics) && error("metrics must not be empty")
    result = grid_patch_isolation_demo(
        rows=rows,
        cols=cols,
        patch_rows=patch_rows,
        patch_cols=patch_cols,
        field_width=field_width,
        field_height=field_height,
        seed=seed,
        D_a=D_a,
        D_i=D_i,
        steady_stop=steady_stop,
        active_fraction=active_fraction,
        validate=false,
    )
    cases = [
        _metric_sensitivity_case(result.evaluations, result.ranking_connectivity, metric)
        for metric in metrics
    ]
    return GridPatchMetricSensitivityResult(
        rows,
        cols,
        patch_rows,
        patch_cols,
        seed,
        D_a,
        D_i,
        copy(metrics),
        cases,
    )
end

function grid_patch_threshold_sensitivity_demo(;
    rows::Int=8,
    cols::Int=8,
    patch_rows::Int=2,
    patch_cols::Int=2,
    field_width::Float64=40.0,
    field_height::Float64=40.0,
    seed::Int=0,
    D_a::Float64=1.0,
    D_i::Float64=30.0,
    steady_stop::Bool=true,
    active_fractions::Vector{Float64}=[0.4, 0.5, 0.6],
    metrics::Vector{Symbol}=[:balanced, :structure, :profile],
)
    isempty(active_fractions) && error("active_fractions must not be empty")
    isempty(metrics) && error("metrics must not be empty")
    cases = GridThresholdSensitivityCase[]
    for active_fraction in active_fractions
        result = grid_patch_isolation_demo(
            rows=rows,
            cols=cols,
            patch_rows=patch_rows,
            patch_cols=patch_cols,
            field_width=field_width,
            field_height=field_height,
            seed=seed,
            D_a=D_a,
            D_i=D_i,
            steady_stop=steady_stop,
            active_fraction=active_fraction,
            validate=false,
        )
        for metric in metrics
            push!(cases, _threshold_sensitivity_case(active_fraction, result.evaluations, result.ranking_connectivity, metric))
        end
    end
    return GridPatchThresholdSensitivityResult(
        rows,
        cols,
        patch_rows,
        patch_cols,
        seed,
        D_a,
        D_i,
        copy(active_fractions),
        copy(metrics),
        cases,
    )
end

end
