module GraphRecovery

using ..RD: RDParameters
using ..RDGraph: RDGraphConfig,
    RD_GRAPH_SOLVER_ALGORITHM,
    RD_GRAPH_ABSTOL,
    RD_GRAPH_RELTOL,
    RD_GRAPH_MAXITERS,
    graph_residual_linf,
    graph_connected_components,
    graph_subconfig,
    graph_substate,
    graph_without_edges,
    grid_graph_config,
    make_rd_graph_state,
    settle_rd_graph!
using ..GridLesions: graph_morphology_snapshot,
    isolate_rectangle_edges

export GraphRecoveryConfig,
    GraphComponentReference,
    ComponentRecoveryMetrics,
    RecoveryEvaluation,
    ComponentFeasibility,
    RecoveryFeasibilitySurface,
    RecoveryTraceEntry,
    RecoveryPolicyRun,
    GraphRecoveryExperiment,
    GridPatchRecoveryResult,
    count_error_action,
    global_count_actions,
    componentwise_count_actions,
    diffusion_parameters_at_exponent,
    graph_recovery_experiment,
    grid_patch_recovery_demo

Base.@kwdef struct GraphRecoveryConfig
    exponent_min::Int = -11
    exponent_max::Int = 11
    step_factor::Float64 = 1.21
    active_fraction::Float64 = 0.5
    meaningful_improvement::Float64 = 0.20
    max_count_selection_regret::Float64 = 0.10
    max_iterations::Int = 8
    steady_stop::Bool = true
    allow_sham::Bool = false
    include_delayed_capacity::Bool = true
    include_feedback::Bool = true
end

struct GraphComponentReference
    component_id::Int
    nodes::Vector{Int}
    threshold::Float64
    target_domain_count::Int
    reference_active_cell_count::Int
    reference_A::Vector{Float64}
    reference_I::Vector{Float64}
end

struct ComponentRecoveryMetrics
    component_id::Int
    nodes::Vector{Int}
    exponent::Int
    D_a::Float64
    D_i::Float64
    solver_retcode::String
    integration_end_time::Float64
    terminal_residual_linf::Float64
    reached_steady::Bool
    target_domain_count::Int
    observed_domain_count::Int
    count_error::Int
    reference_active_cell_count::Int
    observed_active_cell_count::Int
    profile_l1_mean::Float64
    profile_l2_rms::Float64
    profile_relative_rmse::Float64
    inhibitor_profile_l1_mean::Float64
    inhibitor_profile_l2_rms::Float64
    inhibitor_profile_relative_rmse::Float64
    shape_rmse::Float64
    mask_hamming_fraction::Float64
    profile_squared_error::Float64
    reference_energy::Float64
    inhibitor_profile_squared_error::Float64
    inhibitor_reference_energy::Float64
    observed_A::Vector{Float64}
    observed_I::Vector{Float64}
end

struct RecoveryEvaluation
    exponents::Vector{Int}
    components::Vector{ComponentRecoveryMetrics}
    total_abs_count_error::Int
    aggregate_count_error::Int
    component_count_targets_met::Bool
    all_components_steady::Bool
    max_terminal_residual_linf::Float64
    profile_l1_mean::Float64
    profile_l2_rms::Float64
    profile_relative_rmse::Float64
    inhibitor_profile_l1_mean::Float64
    inhibitor_profile_l2_rms::Float64
    inhibitor_profile_relative_rmse::Float64
    shape_rmse::Float64
    mask_hamming_fraction::Float64
end

struct ComponentFeasibility
    component_id::Int
    nodes::Vector{Int}
    evaluations::Vector{ComponentRecoveryMetrics}
    count_feasible_exponents::Vector{Int}
    preferred_exponent::Int
end

struct RecoveryFeasibilitySurface
    exponents::Vector{Int}
    components::Vector{ComponentFeasibility}
    global_diagonal::Vector{RecoveryEvaluation}
    factorized_loss_surface::Vector{Vector{Float64}}
    factorized_count_error_surface::Vector{Vector{Int}}
    global_count_feasible_exponents::Vector{Int}
    factorized_count_feasible::Bool
    global_best::RecoveryEvaluation
    factorized_best::RecoveryEvaluation
    global_count_constrained_best::Union{Nothing,RecoveryEvaluation}
    factorized_count_constrained_best::Union{Nothing,RecoveryEvaluation}
    global_count_selected::RecoveryEvaluation
    factorized_count_selected::Union{Nothing,RecoveryEvaluation}
    preferred_exponent_span::Int
    relative_loss_improvement::Float64
    count_constrained_absolute_loss_reduction::Union{Nothing,Float64}
    count_constrained_relative_loss_reduction::Union{Nothing,Float64}
    factorized_count_selection_regret::Union{Nothing,Float64}
    count_selection_sufficient::Union{Nothing,Bool}
    outcome_class::Symbol
    meaningful_improvement::Float64
    max_count_selection_regret::Float64
    global_best_on_boundary::Bool
    factorized_best_on_boundary::Bool
    global_count_constrained_on_boundary::Union{Nothing,Bool}
    factorized_count_constrained_on_boundary::Union{Nothing,Bool}
end

struct RecoveryTraceEntry
    iteration::Int
    exponents::Vector{Int}
    actions::Vector{Int}
    observed_domain_counts::Vector{Int}
    target_domain_counts::Vector{Int}
    count_errors::Vector{Int}
    controller_converged::Bool
    component_count_targets_met::Bool
    all_components_steady::Bool
    max_terminal_residual_linf::Float64
    profile_relative_rmse::Float64
    inhibitor_profile_relative_rmse::Float64
    shape_rmse::Float64
    mask_hamming_fraction::Float64
end

struct RecoveryPolicyRun
    policy::Symbol
    termination::Symbol
    controller_converged::Bool
    component_count_targets_met::Bool
    iterations::Int
    final_exponents::Vector{Int}
    final_evaluation::RecoveryEvaluation
    trace::Vector{RecoveryTraceEntry}
end

struct GraphRecoveryExperiment
    schema_version::Int
    package_version::String
    julia_version::String
    code_revision::String
    n_cells::Int
    connected_component_count::Int
    severed_component_count::Int
    connected_edge_count::Int
    severed_edge_count::Int
    component_sizes::Vector{Int}
    severed_edges::Vector{NTuple{2,Int}}
    baseline_parameters::RDParameters
    baseline_D_a::Float64
    baseline_D_i::Float64
    diffusion_ratio::Float64
    settle_tspan::Tuple{Float64,Float64}
    steady_tol::Float64
    solver_algorithm::String
    solver_abstol::Float64
    solver_reltol::Float64
    solver_maxiters::Int
    reference_solver_retcode::Union{Nothing,String}
    reference_integration_end_time::Union{Nothing,Float64}
    reference_terminal_residual_linf::Float64
    reference_reached_steady::Bool
    step_factor::Float64
    active_fraction::Float64
    exponent_bounds::Tuple{Int,Int}
    max_iterations::Int
    steady_stop::Bool
    allow_sham::Bool
    feedback_calibration::Union{Nothing,String}
    evidence_scope::String
    capacity_intervention_timing::String
    feedback_intervention_timing::Union{Nothing,String}
    primary_outcome::String
    meaningful_improvement_threshold::Float64
    max_count_selection_regret::Float64
    references::Vector{GraphComponentReference}
    immediate_feasibility::RecoveryFeasibilitySurface
    delayed_feasibility::Union{Nothing,RecoveryFeasibilitySurface}
    fixed::RecoveryPolicyRun
    global_feedback::Union{Nothing,RecoveryPolicyRun}
    componentwise_feedback::Union{Nothing,RecoveryPolicyRun}
    immediate_capacity_at_equilibrium::Bool
    delayed_capacity_at_equilibrium::Union{Nothing,Bool}
    feedback_at_equilibrium::Union{Nothing,Bool}
    all_evaluations_at_equilibrium::Bool
    matched_feedback_initialization::Union{Nothing,Bool}
    notes::Vector{String}
end

struct GridPatchRecoveryResult
    schema_version::Int
    rows::Int
    cols::Int
    patch_top::Int
    patch_left::Int
    patch_rows::Int
    patch_cols::Int
    field_width::Float64
    field_height::Float64
    settle_time::Float64
    seed::Int
    settled_reference_A::Vector{Float64}
    settled_reference_I::Vector{Float64}
    experiment::GraphRecoveryExperiment
end

struct _PreparedComponent
    reference::GraphComponentReference
    config::RDGraphConfig
    lesion_state::Vector{Float64}
end

function _validate_recovery_config(config::GraphRecoveryConfig)
    config.exponent_min <= 0 <= config.exponent_max ||
        error("exponent bounds must include the baseline exponent 0")
    config.step_factor > 1 || error("step_factor must be > 1")
    0 < config.active_fraction <= 1 || error("active_fraction must lie in (0, 1]")
    0 <= config.meaningful_improvement <= 1 ||
        error("meaningful_improvement must lie in [0, 1]")
    0 <= config.max_count_selection_regret <= 1 ||
        error("max_count_selection_regret must lie in [0, 1]")
    config.max_iterations >= 1 || error("max_iterations must be >= 1")
    config.include_feedback && !config.include_delayed_capacity && error(
        "include_feedback=true requires include_delayed_capacity=true for matched calibration",
    )
    return config
end

function _validate_graph_pair(connected::RDGraphConfig, severed::RDGraphConfig)
    connected_components = graph_connected_components(connected)
    length(connected_components) == 1 ||
        error("connected reference graph must contain exactly one connected component")
    severed_components = graph_connected_components(severed)
    connected.n_cells == severed.n_cells || error("connected and severed graphs must have the same nodes")
    connected.x == severed.x || error("connected and severed graphs must preserve x coordinates")
    connected.y == severed.y || error("connected and severed graphs must preserve y coordinates")
    connected.tspan == severed.tspan || error("connected and severed graphs must preserve tspan")
    connected.seed == severed.seed || error("connected and severed graphs must preserve seed")
    connected.steady_tol == severed.steady_tol ||
        error("connected and severed graphs must preserve steady_tol")
    connected_weights = Dict(edge => weight for (edge, weight) in zip(connected.edges, connected.edge_weights))
    for (edge, weight) in zip(severed.edges, severed.edge_weights)
        haskey(connected_weights, edge) || error("severed graph contains added edge $edge")
        connected_weights[edge] == weight || error("severed graph changes the weight of edge $edge")
    end
    return (
        removed_edges=sort!(collect(setdiff(Set(connected.edges), Set(severed.edges)))),
        connected_component_count=length(connected_components),
        severed_component_count=length(severed_components),
    )
end

function _normalize_reported_edges(edges::Vector{NTuple{2,Int}})
    normalized = [left < right ? (left, right) : (right, left) for (left, right) in edges]
    length(unique(normalized)) == length(normalized) || error("severed_edges must not contain duplicates")
    return sort!(normalized)
end

function count_error_action(error::Integer)
    error > 0 && return 1
    error < 0 && return -1
    return 0
end

function diffusion_parameters_at_exponent(
    baseline::RDParameters,
    exponent::Int,
    step_factor::Float64=1.21,
)
    step_factor > 1 || error("step_factor must be > 1")
    baseline.D_a > 0 || error("baseline D_a must be > 0")
    baseline.D_i > 0 || error("baseline D_i must be > 0")
    scale = step_factor ^ exponent
    params = deepcopy(baseline)
    params.D_a = baseline.D_a * scale
    params.D_i = baseline.D_i * scale
    return params
end

function _mean(values)
    isempty(values) && return 0.0
    return sum(values) / length(values)
end

function _shape_profile(values::AbstractVector{<:Real})
    isempty(values) && return Float64[]
    low = minimum(values)
    span = maximum(values) - low
    span <= eps(Float64) && return zeros(Float64, length(values))
    return [(Float64(value) - low) / span for value in values]
end

function _mask_hamming_fraction(left::BitVector, right::BitVector)
    length(left) == length(right) || error("masks must have the same length")
    isempty(left) && return 0.0
    return count(idx -> left[idx] != right[idx], eachindex(left)) / length(left)
end

function _component_metrics(
    prepared::_PreparedComponent,
    state::Vector{Float64},
    exponent::Int,
    params::RDParameters,
    solution,
)
    reference = prepared.reference
    snapshot = graph_morphology_snapshot(
        state,
        prepared.config;
        threshold=reference.threshold,
    )
    delta = snapshot.A .- reference.reference_A
    squared_error = sum(delta .^ 2)
    reference_energy = sum(reference.reference_A .^ 2)
    inhibitor_delta = snapshot.I .- reference.reference_I
    inhibitor_squared_error = sum(inhibitor_delta .^ 2)
    inhibitor_reference_energy = sum(reference.reference_I .^ 2)
    l1 = _mean(abs.(delta))
    l2 = sqrt(_mean(delta .^ 2))
    relative = sqrt(squared_error / max(reference_energy, eps(Float64)))
    inhibitor_l1 = _mean(abs.(inhibitor_delta))
    inhibitor_l2 = sqrt(_mean(inhibitor_delta .^ 2))
    inhibitor_relative = sqrt(
        inhibitor_squared_error / max(inhibitor_reference_energy, eps(Float64)),
    )
    shape_delta = _shape_profile(snapshot.A) .- _shape_profile(reference.reference_A)
    reference_mask = BitVector(reference.reference_A .>= reference.threshold)
    terminal_residual = graph_residual_linf(state, params, prepared.config)
    return ComponentRecoveryMetrics(
        reference.component_id,
        copy(reference.nodes),
        exponent,
        params.D_a,
        params.D_i,
        string(solution.retcode),
        Float64(solution.t[end]),
        terminal_residual,
        terminal_residual <= prepared.config.steady_tol,
        reference.target_domain_count,
        snapshot.component_count,
        snapshot.component_count - reference.target_domain_count,
        reference.reference_active_cell_count,
        snapshot.active_cell_count,
        l1,
        l2,
        relative,
        inhibitor_l1,
        inhibitor_l2,
        inhibitor_relative,
        sqrt(_mean(shape_delta .^ 2)),
        _mask_hamming_fraction(reference_mask, snapshot.active_mask),
        squared_error,
        reference_energy,
        inhibitor_squared_error,
        inhibitor_reference_energy,
        snapshot.A,
        snapshot.I,
    )
end

function _aggregate_evaluation(metrics::Vector{ComponentRecoveryMetrics})
    isempty(metrics) && error("recovery evaluation requires at least one component")
    total_cells = sum(length(metric.nodes) for metric in metrics)
    total_cells > 0 || error("recovery components must contain nodes")
    total_squared_error = sum(metric.profile_squared_error for metric in metrics)
    total_reference_energy = sum(metric.reference_energy for metric in metrics)
    total_inhibitor_squared_error = sum(
        metric.inhibitor_profile_squared_error for metric in metrics
    )
    total_inhibitor_reference_energy = sum(
        metric.inhibitor_reference_energy for metric in metrics
    )
    l1 = sum(metric.profile_l1_mean * length(metric.nodes) for metric in metrics) / total_cells
    l2 = sqrt(sum(metric.profile_l2_rms ^ 2 * length(metric.nodes) for metric in metrics) / total_cells)
    inhibitor_l1 = sum(
        metric.inhibitor_profile_l1_mean * length(metric.nodes) for metric in metrics
    ) / total_cells
    inhibitor_l2 = sqrt(
        sum(
            metric.inhibitor_profile_l2_rms ^ 2 * length(metric.nodes)
            for metric in metrics
        ) / total_cells,
    )
    shape = sqrt(sum(metric.shape_rmse ^ 2 * length(metric.nodes) for metric in metrics) / total_cells)
    hamming = sum(metric.mask_hamming_fraction * length(metric.nodes) for metric in metrics) / total_cells
    errors = [metric.count_error for metric in metrics]
    return RecoveryEvaluation(
        [metric.exponent for metric in metrics],
        metrics,
        sum(abs, errors),
        sum(errors),
        all(iszero, errors),
        all(metric.reached_steady for metric in metrics),
        maximum(metric.terminal_residual_linf for metric in metrics),
        l1,
        l2,
        sqrt(total_squared_error / max(total_reference_energy, eps(Float64))),
        inhibitor_l1,
        inhibitor_l2,
        sqrt(
            total_inhibitor_squared_error /
            max(total_inhibitor_reference_energy, eps(Float64)),
        ),
        shape,
        hamming,
    )
end

function _prepare_components(
    connected_state::Vector{Float64},
    severed::RDGraphConfig,
    active_fraction::Float64,
)
    components = graph_connected_components(severed)
    prepared = _PreparedComponent[]
    for (component_id, nodes) in enumerate(components)
        subconfig = graph_subconfig(severed, nodes)
        reference_state = graph_substate(connected_state, severed, nodes)
        n = subconfig.n_cells
        reference_A = collect(@view reference_state[1:n])
        reference_I = collect(@view reference_state[(n + 1):end])
        threshold = active_fraction * maximum(reference_A)
        snapshot = graph_morphology_snapshot(
            reference_state,
            subconfig;
            threshold=threshold,
        )
        reference = GraphComponentReference(
            component_id,
            copy(nodes),
            threshold,
            snapshot.component_count,
            snapshot.active_cell_count,
            reference_A,
            reference_I,
        )
        push!(prepared, _PreparedComponent(reference, subconfig, reference_state))
    end
    return prepared
end

function _settled_component_metrics(
    prepared::_PreparedComponent,
    baseline::RDParameters,
    exponent::Int,
    config::GraphRecoveryConfig;
    initial_state::Vector{Float64}=prepared.lesion_state,
)
    params = diffusion_parameters_at_exponent(baseline, exponent, config.step_factor)
    state = copy(initial_state)
    solution = settle_rd_graph!(state, params, prepared.config; steady_stop=config.steady_stop)
    metrics = _component_metrics(prepared, state, exponent, params, solution)
    config.steady_stop && !metrics.reached_steady && error(
        "component $(prepared.reference.component_id) did not reach steady_tol=$(prepared.config.steady_tol); " *
        "increase the settle interval or set steady_stop=false for an explicit finite-horizon run",
    )
    return state, metrics
end

function _evaluation_sort_key(evaluation::RecoveryEvaluation)
    return (
        evaluation.profile_relative_rmse,
        evaluation.total_abs_count_error,
        sum(abs, evaluation.exponents),
        Tuple(evaluation.exponents),
    )
end

function _component_sort_key(metric::ComponentRecoveryMetrics)
    return (
        metric.profile_squared_error,
        abs(metric.count_error),
        abs(metric.exponent),
        metric.exponent,
    )
end

function _minimum_by(values::AbstractVector, key::Function)
    isempty(values) && error("cannot select a minimum from an empty collection")
    return values[argmin(key.(values))]
end

function _on_exponent_boundary(evaluation::RecoveryEvaluation, config::GraphRecoveryConfig)
    return any(
        exponent == config.exponent_min || exponent == config.exponent_max
        for exponent in evaluation.exponents
    )
end

function _count_constrained_outcome_class(
    factorized_count_feasible::Bool,
    global_count_constrained_best::Union{Nothing,RecoveryEvaluation},
    relative_reduction::Union{Nothing,Float64},
    meaningful_improvement::Float64,
)
    !factorized_count_feasible && return :neither_count_feasible
    isnothing(global_count_constrained_best) && return :factorized_feasibility_rescue
    relative_reduction isa Float64 || error("count-constrained reduction is missing")
    relative_reduction > 10 * eps(Float64) &&
        relative_reduction + 10 * eps(Float64) >= meaningful_improvement &&
        return :factorized_quality_rescue
    return :no_material_factorized_advantage
end

function _validate_count_calibration(
    exponent_grid::AbstractVector{<:Integer},
    calibrated_count_errors::AbstractVector{<:AbstractVector{<:Integer}},
    current_exponents::AbstractVector{<:Integer},
    current_errors::AbstractVector{<:Integer},
)
    !isempty(exponent_grid) || error("count calibration requires at least one exponent")
    issorted(exponent_grid) || error("count calibration exponents must be sorted")
    length(unique(exponent_grid)) == length(exponent_grid) ||
        error("count calibration exponents must be unique")
    all(exponent_grid[idx + 1] - exponent_grid[idx] == 1 for idx in 1:(length(exponent_grid) - 1)) ||
        error("count calibration exponents must be consecutive unit steps")
    component_count = length(calibrated_count_errors)
    component_count >= 1 || error("count calibration requires at least one component")
    length(current_exponents) == component_count ||
        error("current_exponents must match calibrated component count")
    length(current_errors) == component_count ||
        error("current_errors must match calibrated component count")
    all(length(row) == length(exponent_grid) for row in calibrated_count_errors) ||
        error("each calibrated count-error row must match exponent_grid")
    all(exponent in exponent_grid for exponent in current_exponents) ||
        error("current exponents must belong to exponent_grid")
    return nothing
end

function _predicted_count_error(
    exponent_grid::AbstractVector{<:Integer},
    calibration_row::AbstractVector{<:Integer},
    current_exponent::Integer,
    current_error::Integer,
    candidate_exponent::Integer,
)
    current_index = findfirst(==(current_exponent), exponent_grid)
    candidate_index = findfirst(==(candidate_exponent), exponent_grid)
    return current_error + calibration_row[candidate_index] - calibration_row[current_index]
end

function componentwise_count_actions(
    exponent_grid::AbstractVector{<:Integer},
    calibrated_count_errors::AbstractVector{<:AbstractVector{<:Integer}},
    current_exponents::AbstractVector{<:Integer},
    current_errors::AbstractVector{<:Integer},
)
    _validate_count_calibration(
        exponent_grid,
        calibrated_count_errors,
        current_exponents,
        current_errors,
    )
    return [
        begin
            current = current_exponents[idx]
            best = _minimum_by(
                collect(exponent_grid),
                candidate -> (
                    abs(
                        _predicted_count_error(
                            exponent_grid,
                            calibrated_count_errors[idx],
                            current,
                            current_errors[idx],
                            candidate,
                        ),
                    ),
                    abs(candidate - current),
                    abs(candidate),
                    candidate,
                ),
            )
            count_error_action(best - current)
        end for idx in eachindex(current_exponents)
    ]
end

function global_count_actions(
    exponent_grid::AbstractVector{<:Integer},
    calibrated_count_errors::AbstractVector{<:AbstractVector{<:Integer}},
    current_exponents::AbstractVector{<:Integer},
    current_errors::AbstractVector{<:Integer},
)
    _validate_count_calibration(
        exponent_grid,
        calibrated_count_errors,
        current_exponents,
        current_errors,
    )
    all(==(first(current_exponents)), current_exponents) ||
        error("global count control requires one shared current exponent")
    current = first(current_exponents)
    best = _minimum_by(
        collect(exponent_grid),
        candidate -> (
            sum(
                abs(
                    _predicted_count_error(
                        exponent_grid,
                        calibrated_count_errors[idx],
                        current,
                        current_errors[idx],
                        candidate,
                    ),
                ) for idx in eachindex(current_errors)
            ),
            abs(candidate - current),
            abs(candidate),
            candidate,
        ),
    )
    return fill(count_error_action(best - current), length(current_exponents))
end

function _feasibility_surface(
    prepared::Vector{_PreparedComponent},
    baseline::RDParameters,
    config::GraphRecoveryConfig,
    ;
    baseline_metrics::Union{Nothing,Vector{ComponentRecoveryMetrics}}=nothing,
)
    exponents = collect(config.exponent_min:config.exponent_max)
    if baseline_metrics isa Vector{ComponentRecoveryMetrics}
        length(baseline_metrics) == length(prepared) ||
            error("baseline metrics must align with prepared components")
        all(iszero(metric.exponent) for metric in baseline_metrics) ||
            error("baseline metrics must use exponent 0")
        all(
            baseline_metrics[idx].nodes == prepared[idx].reference.nodes
            for idx in eachindex(prepared)
        ) || error("baseline metric nodes must align with prepared components")
    end
    component_metrics = Vector{Vector{ComponentRecoveryMetrics}}(undef, length(prepared))
    components = ComponentFeasibility[]
    for (component_index, component) in enumerate(prepared)
        rows = ComponentRecoveryMetrics[]
        for exponent in exponents
            metrics = if iszero(exponent) && baseline_metrics isa Vector{ComponentRecoveryMetrics}
                baseline_metrics[component_index]
            else
                _, settled_metrics = _settled_component_metrics(
                    component,
                    baseline,
                    exponent,
                    config,
                )
                settled_metrics
            end
            push!(rows, metrics)
        end
        component_metrics[component_index] = rows
        feasible = [row.exponent for row in rows if row.count_error == 0]
        preferred = _minimum_by(rows, _component_sort_key).exponent
        push!(
            components,
            ComponentFeasibility(
                component.reference.component_id,
                copy(component.reference.nodes),
                rows,
                feasible,
                preferred,
            ),
        )
    end

    global_diagonal = RecoveryEvaluation[]
    for exponent_index in eachindex(exponents)
        rows = [component_metrics[idx][exponent_index] for idx in eachindex(prepared)]
        push!(global_diagonal, _aggregate_evaluation(rows))
    end
    global_best = _minimum_by(global_diagonal, _evaluation_sort_key)

    factorized_rows = [_minimum_by(rows, _component_sort_key) for rows in component_metrics]
    factorized_best = _aggregate_evaluation(factorized_rows)
    preferred_exponents = factorized_best.exponents
    preferred_span = maximum(preferred_exponents) - minimum(preferred_exponents)

    factorized_loss_surface = Vector{Vector{Float64}}()
    factorized_count_error_surface = Vector{Vector{Int}}()
    if length(component_metrics) == 2
        for left in component_metrics[1]
            loss_row = Float64[]
            count_row = Int[]
            for right in component_metrics[2]
                evaluation = _aggregate_evaluation([left, right])
                push!(loss_row, evaluation.profile_relative_rmse)
                push!(count_row, evaluation.total_abs_count_error)
            end
            push!(factorized_loss_surface, loss_row)
            push!(factorized_count_error_surface, count_row)
        end
    end

    global_feasible = [
        evaluation.exponents[1]
        for evaluation in global_diagonal
        if evaluation.component_count_targets_met
    ]
    factorized_feasible = all(!isempty(component.count_feasible_exponents) for component in components)
    !isempty(global_feasible) && !factorized_feasible && error(
        "shared count feasibility must imply factorized count feasibility",
    )
    global_count_constrained_candidates = [
        evaluation for evaluation in global_diagonal if evaluation.component_count_targets_met
    ]
    global_count_constrained_best = if isempty(global_count_constrained_candidates)
        nothing
    else
        _minimum_by(global_count_constrained_candidates, _evaluation_sort_key)
    end
    factorized_count_constrained_best = if factorized_feasible
        count_constrained_rows = [
            [row for row in rows if iszero(row.count_error)] for rows in component_metrics
        ]
        _aggregate_evaluation([
            _minimum_by(rows, _component_sort_key) for rows in count_constrained_rows
        ])
    else
        nothing
    end
    global_count_selected = _minimum_by(
        global_diagonal,
        evaluation -> (
            evaluation.total_abs_count_error,
            abs(first(evaluation.exponents)),
            first(evaluation.exponents),
        ),
    )
    factorized_count_selected = if factorized_feasible
        _aggregate_evaluation([
            _minimum_by(
                rows,
                metric -> (abs(metric.count_error), abs(metric.exponent), metric.exponent),
            ) for rows in component_metrics
        ])
    else
        nothing
    end
    improvement = if global_best.profile_relative_rmse <= eps(Float64)
        0.0
    else
        (global_best.profile_relative_rmse - factorized_best.profile_relative_rmse) /
        global_best.profile_relative_rmse
    end
    count_constrained_absolute_reduction = if global_count_constrained_best isa RecoveryEvaluation &&
        factorized_count_constrained_best isa RecoveryEvaluation
        global_count_constrained_best.profile_relative_rmse -
        factorized_count_constrained_best.profile_relative_rmse
    else
        nothing
    end
    count_constrained_relative_reduction = if count_constrained_absolute_reduction isa Float64
        global_loss = global_count_constrained_best.profile_relative_rmse
        factorized_loss = factorized_count_constrained_best.profile_relative_rmse
        tolerance = 100 * eps(Float64) * max(1.0, global_loss)
        factorized_loss <= global_loss + tolerance || error(
            "factorized count-constrained authority cannot be worse than its shared diagonal subset",
        )
        global_loss <= eps(Float64) ? 0.0 : count_constrained_absolute_reduction / global_loss
    else
        nothing
    end
    factorized_count_selection_regret = if factorized_count_selected isa RecoveryEvaluation &&
        factorized_count_constrained_best isa RecoveryEvaluation
        zero_index = findfirst(iszero, exponents)
        fixed_loss = global_diagonal[zero_index].profile_relative_rmse
        oracle_loss = factorized_count_constrained_best.profile_relative_rmse
        selected_loss = factorized_count_selected.profile_relative_rmse
        tolerance = 100 * eps(Float64) * max(1.0, fixed_loss, selected_loss)
        selected_loss + tolerance >= oracle_loss || error(
            "count-selected factorized loss cannot beat the profile oracle",
        )
        available_improvement = fixed_loss - oracle_loss
        if available_improvement > tolerance
            max(0.0, selected_loss - oracle_loss) / available_improvement
        else
            nothing
        end
    else
        nothing
    end
    count_selection_sufficient = if factorized_count_selection_regret isa Float64
        factorized_count_selected.component_count_targets_met &&
            factorized_count_selection_regret <= config.max_count_selection_regret
    else
        nothing
    end
    outcome_class = _count_constrained_outcome_class(
        factorized_feasible,
        global_count_constrained_best,
        count_constrained_relative_reduction,
        config.meaningful_improvement,
    )
    return RecoveryFeasibilitySurface(
        exponents,
        components,
        global_diagonal,
        factorized_loss_surface,
        factorized_count_error_surface,
        global_feasible,
        factorized_feasible,
        global_best,
        factorized_best,
        global_count_constrained_best,
        factorized_count_constrained_best,
        global_count_selected,
        factorized_count_selected,
        preferred_span,
        improvement,
        count_constrained_absolute_reduction,
        count_constrained_relative_reduction,
        factorized_count_selection_regret,
        count_selection_sufficient,
        outcome_class,
        config.meaningful_improvement,
        config.max_count_selection_regret,
        _on_exponent_boundary(global_best, config),
        _on_exponent_boundary(factorized_best, config),
        if isnothing(global_count_constrained_best)
            nothing
        else
            _on_exponent_boundary(global_count_constrained_best, config)
        end,
        if isnothing(factorized_count_constrained_best)
            nothing
        else
            _on_exponent_boundary(factorized_count_constrained_best, config)
        end,
    )
end

function _trace_entry(
    iteration::Int,
    evaluation::RecoveryEvaluation,
    actions::Vector{Int},
    controller_converged::Bool,
)
    return RecoveryTraceEntry(
        iteration,
        copy(evaluation.exponents),
        copy(actions),
        [metric.observed_domain_count for metric in evaluation.components],
        [metric.target_domain_count for metric in evaluation.components],
        [metric.count_error for metric in evaluation.components],
        controller_converged,
        evaluation.component_count_targets_met,
        evaluation.all_components_steady,
        evaluation.max_terminal_residual_linf,
        evaluation.profile_relative_rmse,
        evaluation.inhibitor_profile_relative_rmse,
        evaluation.shape_rmse,
        evaluation.mask_hamming_fraction,
    )
end

function _settle_policy_iteration!(
    prepared::Vector{_PreparedComponent},
    states::Vector{Vector{Float64}},
    baseline::RDParameters,
    exponents::Vector{Int},
    config::GraphRecoveryConfig,
)
    metrics = ComponentRecoveryMetrics[]
    for idx in eachindex(prepared)
        params = diffusion_parameters_at_exponent(baseline, exponents[idx], config.step_factor)
        solution = settle_rd_graph!(
            states[idx],
            params,
            prepared[idx].config;
            steady_stop=config.steady_stop,
        )
        component_metrics = _component_metrics(
            prepared[idx],
            states[idx],
            exponents[idx],
            params,
            solution,
        )
        config.steady_stop && !component_metrics.reached_steady && error(
            "component $(prepared[idx].reference.component_id) did not reach steady_tol=$(prepared[idx].config.steady_tol); " *
            "increase the settle interval or set steady_stop=false for an explicit finite-horizon run",
        )
        push!(
            metrics,
            component_metrics,
        )
    end
    return _aggregate_evaluation(metrics)
end

function _run_fixed_policy(
    prepared::Vector{_PreparedComponent},
    baseline::RDParameters,
    config::GraphRecoveryConfig,
)
    states = [copy(component.lesion_state) for component in prepared]
    exponents = zeros(Int, length(prepared))
    evaluation = _settle_policy_iteration!(prepared, states, baseline, exponents, config)
    trace = [_trace_entry(1, evaluation, zeros(Int, length(prepared)), false)]
    run = RecoveryPolicyRun(
        :fixed,
        :fixed,
        false,
        evaluation.component_count_targets_met,
        1,
        exponents,
        evaluation,
        trace,
    )
    return run, states
end

function _prepared_from_states(
    prepared::Vector{_PreparedComponent},
    states::Vector{Vector{Float64}},
)
    length(prepared) == length(states) || error("prepared components and states must align")
    return [
        _PreparedComponent(
            component.reference,
            component.config,
            copy(states[idx]),
        ) for (idx, component) in enumerate(prepared)
    ]
end

function _bounded_actions(
    exponents::Vector{Int},
    actions::Vector{Int},
    config::GraphRecoveryConfig,
)
    next_exponents = [
        clamp(exponents[idx] + actions[idx], config.exponent_min, config.exponent_max)
        for idx in eachindex(exponents)
    ]
    applied = next_exponents .- exponents
    return next_exponents, applied
end

function _run_feedback_policy(
    policy::Symbol,
    prepared::Vector{_PreparedComponent},
    baseline::RDParameters,
    config::GraphRecoveryConfig,
    feasibility::RecoveryFeasibilitySurface,
    fixed_states::Vector{Vector{Float64}},
    fixed_evaluation::RecoveryEvaluation,
)
    policy in (:global_feedback, :componentwise_feedback) || error("unknown recovery policy $policy")
    length(prepared) == length(fixed_states) ||
        error("fixed states must align with prepared components")
    fixed_evaluation.exponents == zeros(Int, length(prepared)) ||
        error("fixed feedback initialization must use baseline exponent 0")
    states = [copy(state) for state in fixed_states]
    exponents = zeros(Int, length(prepared))
    trace = RecoveryTraceEntry[]
    final_evaluation::Union{Nothing,RecoveryEvaluation} = nothing
    termination = :max_iterations
    calibrated_count_errors = [
        [metrics.count_error for metrics in component.evaluations]
        for component in feasibility.components
    ]

    for iteration in 1:config.max_iterations
        evaluation = if iteration == 1
            fixed_evaluation
        else
            _settle_policy_iteration!(prepared, states, baseline, exponents, config)
        end
        final_evaluation = evaluation
        if evaluation.component_count_targets_met
            push!(trace, _trace_entry(iteration, evaluation, zeros(Int, length(prepared)), true))
            termination = :component_count_targets
            break
        end
        if iteration == config.max_iterations
            push!(trace, _trace_entry(iteration, evaluation, zeros(Int, length(prepared)), false))
            termination = :max_iterations
            break
        end

        errors = [metric.count_error for metric in evaluation.components]
        requested = if policy == :global_feedback
            global_count_actions(
                feasibility.exponents,
                calibrated_count_errors,
                exponents,
                errors,
            )
        else
            componentwise_count_actions(
                feasibility.exponents,
                calibrated_count_errors,
                exponents,
                errors,
            )
        end
        next_exponents, actions = _bounded_actions(exponents, requested, config)
        push!(trace, _trace_entry(iteration, evaluation, actions, false))
        if all(iszero, actions)
            termination = :count_calibration_stall
            break
        end
        exponents = next_exponents
    end

    final_evaluation isa RecoveryEvaluation || error("feedback policy produced no evaluation")
    return RecoveryPolicyRun(
        policy,
        termination,
        final_evaluation.component_count_targets_met,
        final_evaluation.component_count_targets_met,
        length(trace),
        copy(final_evaluation.exponents),
        final_evaluation,
        trace,
    )
end

function graph_recovery_experiment(
    connected_state::Vector{Float64},
    connected::RDGraphConfig,
    severed::RDGraphConfig,
    baseline::RDParameters=RDParameters();
    severed_edges::Vector{NTuple{2,Int}}=NTuple{2,Int}[],
    recovery_config::GraphRecoveryConfig=GraphRecoveryConfig(),
    reference_solver_retcode::Union{Nothing,String}=nothing,
    reference_integration_end_time::Union{Nothing,Float64}=nothing,
    evidence_scope::String="exploratory_single_regime",
)
    recovery_config = _validate_recovery_config(recovery_config)
    graph_pair = _validate_graph_pair(connected, severed)
    removed_edges = graph_pair.removed_edges
    if !recovery_config.allow_sham
        !isempty(removed_edges) ||
            error("recovery experiment requires at least one removed edge; set allow_sham=true for a no-lesion control")
        graph_pair.severed_component_count > graph_pair.connected_component_count || error(
            "recovery experiment requires a lesion that increases connected-component count; " *
            "set allow_sham=true for a non-disconnecting control",
        )
    end
    if !isempty(severed_edges)
        _normalize_reported_edges(severed_edges) == removed_edges ||
            error("severed_edges must exactly describe the edges removed from the connected graph")
    end
    length(connected_state) == 2 * connected.n_cells ||
        error("connected_state length must be 2 * n_cells")
    baseline.D_a > 0 || error("baseline D_a must be > 0")
    baseline.D_i > 0 || error("baseline D_i must be > 0")
    reference_residual = graph_residual_linf(connected_state, baseline, connected)
    reference_reached_steady = reference_residual <= connected.steady_tol
    recovery_config.steady_stop && !reference_reached_steady && error(
        "connected reference did not reach steady_tol=$(connected.steady_tol); " *
        "increase the settle interval or set steady_stop=false for an explicit finite-horizon run",
    )
    prepared = _prepare_components(
        connected_state,
        severed,
        recovery_config.active_fraction,
    )
    fixed, damaged_states = _run_fixed_policy(prepared, baseline, recovery_config)
    immediate_feasibility = _feasibility_surface(
        prepared,
        baseline,
        recovery_config;
        baseline_metrics=fixed.final_evaluation.components,
    )
    immediate_capacity_at_equilibrium = reference_reached_steady && all(
        metrics.reached_steady
        for component in immediate_feasibility.components
        for metrics in component.evaluations
    )
    delayed_feasibility::Union{Nothing,RecoveryFeasibilitySurface} = nothing
    delayed_capacity_at_equilibrium::Union{Nothing,Bool} = nothing
    global_feedback::Union{Nothing,RecoveryPolicyRun} = nothing
    componentwise_feedback::Union{Nothing,RecoveryPolicyRun} = nothing
    feedback_at_equilibrium::Union{Nothing,Bool} = nothing
    if recovery_config.include_delayed_capacity
        delayed_prepared = _prepared_from_states(prepared, damaged_states)
        delayed_baseline_metrics = if recovery_config.steady_stop
            fixed.final_evaluation.components
        else
            nothing
        end
        delayed_feasibility = _feasibility_surface(
            delayed_prepared,
            baseline,
            recovery_config;
            baseline_metrics=delayed_baseline_metrics,
        )
        delayed_capacity_at_equilibrium = fixed.final_evaluation.all_components_steady && all(
            metrics.reached_steady
            for component in delayed_feasibility.components
            for metrics in component.evaluations
        )
        if recovery_config.include_feedback
            global_feedback = _run_feedback_policy(
                :global_feedback,
                prepared,
                baseline,
                recovery_config,
                delayed_feasibility,
                damaged_states,
                fixed.final_evaluation,
            )
            componentwise_feedback = _run_feedback_policy(
                :componentwise_feedback,
                prepared,
                baseline,
                recovery_config,
                delayed_feasibility,
                damaged_states,
                fixed.final_evaluation,
            )
            feedback_at_equilibrium = fixed.final_evaluation.all_components_steady &&
                all(entry.all_components_steady for entry in global_feedback.trace) &&
                all(entry.all_components_steady for entry in componentwise_feedback.trace)
        end
    end
    all_evaluations_at_equilibrium = immediate_capacity_at_equilibrium &&
        something(delayed_capacity_at_equilibrium, true) &&
        something(feedback_at_equilibrium, true)
    notes = String[
        "The immediate capacity surface starts from the restricted intact equilibrium at lesion time.",
    ]
    if recovery_config.include_delayed_capacity
        push!(
            notes,
            "The delayed capacity surface starts from the settled fixed post-lesion state.",
        )
    end
    if recovery_config.include_feedback
        append!(
            notes,
            [
                "The delayed capacity surface provides the matched calibration surface for feedback.",
                "Feedback first settles the lesion at baseline, then applies count-calibrated unit steps; feedback-to-delayed-oracle gaps therefore isolate policy path dependence after the matched delay.",
                "Feedback predicts count error from the offline count-response surface, chooses the best calibrated exponent, and moves one unit step; shared control minimizes total absolute count error while componentwise control minimizes each component independently.",
            ],
        )
    end
    append!(
        notes,
        [
            "With steady_stop=true, every reference and recovery evaluation must satisfy steady_tol; finite-horizon runs record residuals without claiming equilibrium.",
            "Finite-horizon runs record equilibrium flags but are not time-matched and must not be interpreted as controller-quality evidence.",
            "Active-domain thresholds are fixed from each component's restricted intact reference.",
            "The shared diagonal is a subset of factorized authority; evidence therefore concerns strict, materially large, count-constrained improvements rather than non-inferiority.",
            "The count-constrained outcome class uses activator profile-relative RMSE as its primary quality measure and records shape, mask, and inhibitor metrics separately.",
            "Count-control ties prefer no movement, then the exponent closest to baseline; profile and mask metrics never guide actions.",
            "component_count_targets_met refers only to the count readout, not full phenotype recovery.",
            "Single-case results do not support robustness claims; cohort interpretation belongs to a predeclared cohort analysis.",
            "The count readout is an oracle proxy, not a claim of biological sensing.",
        ],
    )
    return GraphRecoveryExperiment(
        2,
        string(something(Base.pkgversion(parentmodule(@__MODULE__)), v"0.0.0")),
        string(VERSION),
        get(ENV, "POLY_MORPHOGENESIS_REVISION", "unrecorded"),
        connected.n_cells,
        graph_pair.connected_component_count,
        graph_pair.severed_component_count,
        length(connected.edges),
        length(severed.edges),
        [length(component.reference.nodes) for component in prepared],
        removed_edges,
        deepcopy(baseline),
        baseline.D_a,
        baseline.D_i,
        baseline.D_i / baseline.D_a,
        connected.tspan,
        connected.steady_tol,
        RD_GRAPH_SOLVER_ALGORITHM,
        RD_GRAPH_ABSTOL,
        RD_GRAPH_RELTOL,
        RD_GRAPH_MAXITERS,
        reference_solver_retcode,
        reference_integration_end_time,
        reference_residual,
        reference_reached_steady,
        recovery_config.step_factor,
        recovery_config.active_fraction,
        (recovery_config.exponent_min, recovery_config.exponent_max),
        recovery_config.max_iterations,
        recovery_config.steady_stop,
        recovery_config.allow_sham,
        recovery_config.include_feedback ?
            "delayed_count_response_model_predictive_unit_step" : nothing,
        evidence_scope,
        "immediate_post_lesion_from_restricted_intact_equilibrium",
        recovery_config.include_feedback ?
            "after_one_baseline_post_lesion_settle_with_delayed_count_calibration" : nothing,
        "activator_profile_relative_rmse_subject_to_component_count_targets",
        recovery_config.meaningful_improvement,
        recovery_config.max_count_selection_regret,
        [component.reference for component in prepared],
        immediate_feasibility,
        delayed_feasibility,
        fixed,
        global_feedback,
        componentwise_feedback,
        immediate_capacity_at_equilibrium,
        delayed_capacity_at_equilibrium,
        feedback_at_equilibrium,
        all_evaluations_at_equilibrium,
        recovery_config.include_feedback ? true : nothing,
        notes,
    )
end

function grid_patch_recovery_demo(;
    rows::Int=4,
    cols::Int=6,
    patch_top::Int=2,
    patch_left::Int=1,
    patch_rows::Int=2,
    patch_cols::Int=2,
    field_width::Float64=40.0,
    field_height::Float64=40.0,
    settle_time::Float64=300.0,
    seed::Int=33,
    D_a::Float64=1.0,
    D_i::Float64=30.0,
    exponent_min::Int=-11,
    exponent_max::Int=11,
    step_factor::Float64=1.21,
    max_iterations::Int=8,
    active_fraction::Float64=0.5,
    meaningful_improvement::Float64=0.20,
    max_count_selection_regret::Float64=0.10,
    steady_tol::Float64=1.0e-6,
    steady_stop::Bool=true,
    include_delayed_capacity::Bool=true,
    include_feedback::Bool=true,
    evidence_scope::String="exploratory_single_regime",
)
    settle_time > 0 || error("settle_time must be > 0")
    severed_edges = isolate_rectangle_edges(
        rows,
        cols,
        patch_top,
        patch_left,
        patch_rows,
        patch_cols,
    )
    connected = grid_graph_config(
        rows,
        cols;
        field_width=field_width,
        field_height=field_height,
        tspan=(0.0, settle_time),
        steady_tol=steady_tol,
        seed=seed,
    )
    initial_state = make_rd_graph_state(connected; rng_seed=seed)
    baseline = RDParameters(D_a=D_a, D_i=D_i)
    settled_reference = copy(initial_state)
    reference_solution = settle_rd_graph!(
        settled_reference,
        baseline,
        connected;
        steady_stop=steady_stop,
    )
    severed = graph_without_edges(connected, severed_edges)
    experiment = graph_recovery_experiment(
        settled_reference,
        connected,
        severed,
        baseline;
        severed_edges=severed_edges,
        reference_solver_retcode=string(reference_solution.retcode),
        reference_integration_end_time=Float64(reference_solution.t[end]),
        evidence_scope=evidence_scope,
        recovery_config=GraphRecoveryConfig(
            exponent_min=exponent_min,
            exponent_max=exponent_max,
            step_factor=step_factor,
            active_fraction=active_fraction,
            meaningful_improvement=meaningful_improvement,
            max_count_selection_regret=max_count_selection_regret,
            max_iterations=max_iterations,
            steady_stop=steady_stop,
            include_delayed_capacity=include_delayed_capacity,
            include_feedback=include_feedback,
        ),
    )
    n = connected.n_cells
    return GridPatchRecoveryResult(
        2,
        rows,
        cols,
        patch_top,
        patch_left,
        patch_rows,
        patch_cols,
        field_width,
        field_height,
        settle_time,
        seed,
        collect(@view settled_reference[1:n]),
        collect(@view settled_reference[(n + 1):end]),
        experiment,
    )
end

end
