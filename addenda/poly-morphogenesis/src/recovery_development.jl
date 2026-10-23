module RecoveryDevelopment

using SHA

using ..RD: RDParameters
using ..RDGraph: graph_connected_components,
    graph_without_edges,
    grid_graph_config,
    make_rd_graph_state
using ..GridLesions: isolate_rectangle_edges
import ..GraphRecovery
import ..RecoveryAdaptive
using ..RecoveryAdaptive: AdaptiveExponentProtocol,
    AdaptiveExponentStageDecision,
    AdaptiveSettleCheckpoint,
    AdaptiveSettlingProtocol,
    search_adaptive_exponent_bounds,
    settle_rd_graph_adaptive!
import ..RecoveryObservability
using ..RecoveryObservability: RECOVERY_READOUT_LEVELS,
    RecoveryObservabilityReport,
    observability_boundary_sides,
    recovery_observability_report,
    recovery_readout
import ..RecoveryCohort

export RecoveryDevelopmentProtocol,
    RecoveryDevelopmentSpec,
    RecoveryDevelopmentSurfaceRow,
    RecoveryDevelopmentSearchStage,
    RecoveryDevelopmentCase,
    RecoveryDevelopmentFailure,
    RecoveryDevelopmentCaseRecord,
    RecoveryDevelopmentResult,
    RecoveryDevelopmentSeedReadoutSummary,
    RecoveryDevelopmentReadoutSummary,
    RecoveryDevelopmentSummary,
    RecoveryDevelopmentProtocolManifest,
    RecoveryDevelopmentArtifacts,
    recovery_development_case_id,
    run_recovery_development,
    analyze_recovery_development,
    write_recovery_development_protocol,
    write_recovery_development_artifacts

const DEVELOPMENT_PROTOCOL_VERSION = 2
const DEVELOPMENT_RESULT_SCHEMA_VERSION = 1
const DEVELOPMENT_ARTIFACT_SCHEMA_VERSION = 1
const DEVELOPMENT_EVIDENCE_SCOPE = "development_only"
const RESERVED_HOLDOUT_A_SEEDS = 100:111
const RESERVED_HOLDOUT_B_SEEDS = 200:211

Base.@kwdef struct RecoveryDevelopmentProtocol
    steady_tol::Float64 = 1.0e-6
    settling::AdaptiveSettlingProtocol = AdaptiveSettlingProtocol()
    exponents::AdaptiveExponentProtocol = AdaptiveExponentProtocol()
    step_factor::Float64 = 1.21
    active_fraction::Float64 = 0.5
    max_selection_regret::Float64 = 0.10
    readout_levels::Vector{Symbol} = collect(RECOVERY_READOUT_LEVELS)
    alias_resolutions::Vector{Float64} = [1.0e-4, 1.0e-3, 1.0e-2]
    min_overall_sufficiency_rate::Float64 = 0.80
    required_sufficient_seed_fraction::Float64 = 5 / 6
    min_within_seed_sufficiency_rate::Float64 = 0.80
    evidence_scope::String = DEVELOPMENT_EVIDENCE_SCOPE
end

struct RecoveryDevelopmentSpec
    development_id::String
    regime::RecoveryCohort.RecoveryRegime
    protocol::RecoveryDevelopmentProtocol
    seeds::Vector{Int}
    placements::Vector{RecoveryCohort.RecoveryPlacement}
end

function RecoveryDevelopmentSpec(;
    development_id::String,
    regime::RecoveryCohort.RecoveryRegime=RecoveryCohort.RecoveryRegime(),
    protocol::RecoveryDevelopmentProtocol=RecoveryDevelopmentProtocol(),
    seeds::AbstractVector{<:Integer},
    placements::Union{
        Nothing,
        AbstractVector{RecoveryCohort.RecoveryPlacement},
    }=nothing,
)
    selected = isnothing(placements) ? RecoveryCohort.recovery_placements(regime) : placements
    return RecoveryDevelopmentSpec(
        development_id,
        regime,
        protocol,
        Int.(collect(seeds)),
        collect(selected),
    )
end

struct RecoveryDevelopmentSurfaceRow
    case_id::String
    evidence_scope::String
    regime_id::String
    seed::Int
    patch_top::Int
    patch_left::Int
    patch_rows::Int
    patch_cols::Int
    placement_stratum::Symbol
    component_id::Int
    component_size::Int
    exponent::Int
    D_a::Float64
    D_i::Float64
    target_domain_count::Int
    observed_domain_count::Int
    count_error::Int
    target_activator_mass::Float64
    observed_activator_mass::Float64
    target_centroid_x::Float64
    target_centroid_y::Float64
    observed_centroid_x::Float64
    observed_centroid_y::Float64
    profile_squared_error::Float64
    reference_energy::Float64
    profile_relative_rmse::Float64
    inhibitor_profile_relative_rmse::Float64
    shape_rmse::Float64
    mask_hamming_fraction::Float64
    settle_termination::Symbol
    settle_elapsed_time::Float64
    settle_chunk_count::Int
    terminal_residual_linf::Float64
    reached_steady::Bool
    settle_checkpoints::Vector{AdaptiveSettleCheckpoint}
    search_termination::Symbol
    unresolved_boundary::Bool
    case_numerical_ready::Bool
end

struct RecoveryDevelopmentSearchStage
    bounds::Tuple{Int,Int}
    newly_evaluated_exponents::Vector{Int}
    requested_sides::Vector{Symbol}
    objective::Float64
    unresolved_boundary::Bool
    materially_unchanged::Bool
    plateau_streak::Int
end

struct RecoveryDevelopmentCase
    case_id::String
    evidence_scope::String
    regime_id::String
    seed::Int
    patch_top::Int
    patch_left::Int
    patch_rows::Int
    patch_cols::Int
    placement_stratum::Symbol
    reference_settle_termination::Symbol
    reference_settle_elapsed_time::Float64
    reference_settle_chunk_count::Int
    reference_terminal_residual_linf::Float64
    reference_settle_checkpoints::Vector{AdaptiveSettleCheckpoint}
    search_termination::Symbol
    initial_exponent_bounds::Tuple{Int,Int}
    hard_exponent_bounds::Tuple{Int,Int}
    final_exponent_bounds::Tuple{Int,Int}
    unresolved_boundary::Bool
    exponent_evaluation_count::Int
    all_final_rows_reached_steady::Bool
    numerical_ready::Bool
    search_stages::Vector{RecoveryDevelopmentSearchStage}
    observability::RecoveryObservabilityReport
end

struct RecoveryDevelopmentFailure
    case_id::String
    evidence_scope::String
    regime_id::String
    seed::Int
    patch_top::Int
    patch_left::Int
    patch_rows::Int
    patch_cols::Int
    placement_stratum::Symbol
    stage::Symbol
    error_type::String
    message::String
    reference_reached_steady::Union{Nothing,Bool}
    reference_terminal_residual_linf::Union{Nothing,Float64}
    reference_settle_checkpoints::Union{Nothing,Vector{AdaptiveSettleCheckpoint}}
    search_termination::Union{Nothing,Symbol}
    final_exponent_bounds::Union{Nothing,Tuple{Int,Int}}
    unresolved_boundary::Union{Nothing,Bool}
    all_final_rows_reached_steady::Union{Nothing,Bool}
end

const RecoveryDevelopmentCaseRecord = Union{
    RecoveryDevelopmentCase,
    RecoveryDevelopmentFailure,
}

struct RecoveryDevelopmentSeedReadoutSummary
    level::Symbol
    seed::Int
    registered_case_count::Int
    completed_case_count::Int
    sufficient_case_count::Int
    sufficiency_rate_completed::Float64
    sufficiency_rate_registered::Float64
    meets_within_seed_threshold::Bool
end

struct RecoveryDevelopmentReadoutSummary
    level::Symbol
    registered_case_count::Int
    completed_case_count::Int
    sufficient_case_count::Int
    sufficiency_rate_completed::Float64
    sufficiency_rate_registered::Float64
    seeds_meeting_within_seed_threshold::Int
    required_seeds_meeting_within_seed_threshold::Int
    qualifies::Bool
    seed_summaries::Vector{RecoveryDevelopmentSeedReadoutSummary}
end

struct RecoveryDevelopmentSummary
    schema_version::Int
    protocol_version::Int
    development_id::String
    evidence_scope::String
    registered_case_count::Int
    completed_case_count::Int
    failed_case_count::Int
    reference_failure_case_count::Int
    equilibrium_failure_case_count::Int
    unresolved_boundary_case_count::Int
    numerical_ready_case_count::Int
    numerical_readiness_rate_registered::Float64
    response_surface_row_count::Int
    readout_summaries::Vector{RecoveryDevelopmentReadoutSummary}
    smallest_qualifying_readout::Union{Nothing,Symbol}
    notes::Vector{String}
end

struct RecoveryDevelopmentResult
    schema_version::Int
    protocol_version::Int
    development_id::String
    regime::RecoveryCohort.RecoveryRegime
    protocol::RecoveryDevelopmentProtocol
    seeds::Vector{Int}
    placements::Vector{RecoveryCohort.RecoveryPlacement}
    reference_preparation_count::Int
    response_surface_rows::Vector{RecoveryDevelopmentSurfaceRow}
    observability_cases::Vector{RecoveryDevelopmentCaseRecord}
    summary::RecoveryDevelopmentSummary
end

struct RecoveryDevelopmentProtocolManifest
    path::String
    sha256::String
end

struct RecoveryDevelopmentArtifacts
    response_surfaces_path::String
    observability_cases_path::String
    summary_path::String
    manifest_path::String
    response_surfaces_sha256::String
    observability_cases_sha256::String
    summary_sha256::String
    manifest_sha256::String
end

struct _DevelopmentExponentEvaluation
    metrics::Vector{GraphRecovery.ComponentRecoveryMetrics}
    settling::Vector{RecoveryAdaptive.AdaptiveSettleDiagnostics}
end

struct _DevelopmentStageValue
    component_min_count_errors::Vector{Int}
    component_count_constrained_best_exponents::Vector{Union{Nothing,Int}}
    global_min_count_error::Int
    global_count_constrained_best_exponent::Union{Nothing,Int}
end

function _validate_rate(value::Float64, label::String)
    isfinite(value) && 0 <= value <= 1 || error("$label must be finite and lie in [0, 1]")
    return value
end

function _validate_protocol(protocol::RecoveryDevelopmentProtocol)
    isfinite(protocol.steady_tol) && protocol.steady_tol > 0 ||
        error("steady_tol must be finite and > 0")
    RecoveryAdaptive._validate_settling_protocol(protocol.settling)
    RecoveryAdaptive._validate_exponent_protocol(protocol.exponents)
    isfinite(protocol.step_factor) && protocol.step_factor > 1 ||
        error("step_factor must be finite and > 1")
    isfinite(protocol.active_fraction) && 0 < protocol.active_fraction <= 1 ||
        error("active_fraction must be finite and lie in (0, 1]")
    _validate_rate(protocol.max_selection_regret, "max_selection_regret")
    _validate_rate(
        protocol.min_overall_sufficiency_rate,
        "min_overall_sufficiency_rate",
    )
    _validate_rate(
        protocol.required_sufficient_seed_fraction,
        "required_sufficient_seed_fraction",
    )
    _validate_rate(
        protocol.min_within_seed_sufficiency_rate,
        "min_within_seed_sufficiency_rate",
    )
    protocol.evidence_scope == DEVELOPMENT_EVIDENCE_SCOPE || error(
        "recovery development evidence_scope must be `development_only`",
    )
    isempty(protocol.readout_levels) && error("readout_levels must not be empty")
    length(unique(protocol.readout_levels)) == length(protocol.readout_levels) ||
        error("readout_levels must be unique")
    all(level in RECOVERY_READOUT_LEVELS for level in protocol.readout_levels) ||
        error("readout_levels contain an unsupported recovery readout")
    expected_order = [
        level for level in RECOVERY_READOUT_LEVELS if level in protocol.readout_levels
    ]
    protocol.readout_levels == expected_order ||
        error("readout_levels must follow increasing sensor richness")
    RecoveryObservability._validate_resolutions(protocol.alias_resolutions)
    return protocol
end

_reserved_seed(seed::Int) = seed in RESERVED_HOLDOUT_A_SEEDS ||
    seed in RESERVED_HOLDOUT_B_SEEDS

function _validate_seeds(seeds::Vector{Int})
    isempty(seeds) && error("recovery development requires at least one seed")
    all(seed >= 0 for seed in seeds) || error("development seeds must be nonnegative")
    length(unique(seeds)) == length(seeds) || error("development seeds must be unique")
    reserved = sort([seed for seed in seeds if _reserved_seed(seed)])
    isempty(reserved) || error(
        "development seeds overlap reserved Holdout A/B seeds: $(join(reserved, ", "))",
    )
    return seeds
end

function _canonical_spec(spec::RecoveryDevelopmentSpec)
    RecoveryCohort._validate_identifier(spec.development_id, "development_id")
    regime = deepcopy(RecoveryCohort._validate_regime(spec.regime))
    protocol = deepcopy(_validate_protocol(spec.protocol))
    seeds = sort(copy(_validate_seeds(spec.seeds)))
    placements = RecoveryCohort._canonical_placements(regime, spec.placements)
    return RecoveryDevelopmentSpec(
        spec.development_id,
        regime,
        protocol,
        seeds,
        placements,
    )
end

function _guard_output_dir(output_dir::String)
    absolute = normpath(abspath(output_dir))
    existing = absolute
    suffix = String[]
    while !ispath(existing) && !islink(existing)
        parent = dirname(existing)
        parent == existing && break
        pushfirst!(suffix, basename(existing))
        existing = parent
    end
    resolved_prefix = (ispath(existing) || islink(existing)) ? realpath(existing) : existing
    resolved = normpath(joinpath(resolved_prefix, suffix...))
    normalized = lowercase(resolved)
    (occursin(r"holdout[-_]?a", normalized) ||
     occursin(r"holdout[-_]?b", normalized)) &&
        error("development artifacts must not be written into Holdout A/B paths")
    return output_dir
end

function _guard_artifact_leaf(path::String)
    _guard_output_dir(dirname(path))
    islink(path) && error(
        "development artifact paths must not be symbolic links: $(basename(path))",
    )
    ispath(path) && !isfile(path) && error(
        "development artifact paths must be regular files: $(basename(path))",
    )
    return path
end

function recovery_development_case_id(
    spec::RecoveryDevelopmentSpec,
    seed::Int,
    placement::RecoveryCohort.RecoveryPlacement,
)
    return string(
        spec.development_id,
        "__",
        spec.regime.regime_id,
        "__seed-",
        lpad(seed, 10, '0'),
        "__top-",
        lpad(placement.top, 2, '0'),
        "__left-",
        lpad(placement.left, 2, '0'),
    )
end

function _copy_parameters(parameters::RDParameters)
    return RDParameters(
        hill_n=parameters.hill_n,
        gen_a=parameters.gen_a,
        gen_i=parameters.gen_i,
        decay_a=parameters.decay_a,
        decay_i=parameters.decay_i,
        D_a=parameters.D_a,
        D_i=parameters.D_i,
    )
end

function _prepare_reference(spec::RecoveryDevelopmentSpec, seed::Int)
    regime = spec.regime
    protocol = spec.protocol
    connected = grid_graph_config(
        regime.rows,
        regime.cols;
        field_width=regime.field_width,
        field_height=regime.field_height,
        tspan=(0.0, protocol.settling.max_time),
        seed=seed,
        steady_tol=protocol.steady_tol,
    )
    baseline = _copy_parameters(regime.baseline)
    settled = make_rd_graph_state(connected; rng_seed=seed)
    diagnostics = settle_rd_graph_adaptive!(
        settled,
        baseline,
        connected;
        protocol=protocol.settling,
    )
    return connected, baseline, settled, diagnostics
end

function _normalized_component_coordinates(prepared, regime::RecoveryCohort.RecoveryRegime)
    return (
        prepared.config.x ./ regime.field_width,
        prepared.config.y ./ regime.field_height,
    )
end

function _with_adaptive_settle_status(
    metrics::GraphRecovery.ComponentRecoveryMetrics,
    diagnostics::RecoveryAdaptive.AdaptiveSettleDiagnostics,
)
    return GraphRecovery.ComponentRecoveryMetrics(
        metrics.component_id,
        metrics.nodes,
        metrics.exponent,
        metrics.D_a,
        metrics.D_i,
        string(diagnostics.termination),
        diagnostics.elapsed_time,
        diagnostics.terminal_residual_linf,
        diagnostics.reached_steady,
        metrics.target_domain_count,
        metrics.observed_domain_count,
        metrics.count_error,
        metrics.reference_active_cell_count,
        metrics.observed_active_cell_count,
        metrics.profile_l1_mean,
        metrics.profile_l2_rms,
        metrics.profile_relative_rmse,
        metrics.inhibitor_profile_l1_mean,
        metrics.inhibitor_profile_l2_rms,
        metrics.inhibitor_profile_relative_rmse,
        metrics.shape_rmse,
        metrics.mask_hamming_fraction,
        metrics.profile_squared_error,
        metrics.reference_energy,
        metrics.inhibitor_profile_squared_error,
        metrics.inhibitor_reference_energy,
        metrics.observed_A,
        metrics.observed_I,
    )
end

function _evaluate_component_exponent(
    prepared,
    baseline::RDParameters,
    exponent::Int,
    protocol::RecoveryDevelopmentProtocol,
)
    params = GraphRecovery.diffusion_parameters_at_exponent(
        baseline,
        exponent,
        protocol.step_factor,
    )
    state = copy(prepared.lesion_state)
    diagnostics = settle_rd_graph_adaptive!(
        state,
        params,
        prepared.config;
        protocol=protocol.settling,
    )
    solution_record = (
        retcode=diagnostics.termination,
        t=[diagnostics.elapsed_time],
    )
    metrics = GraphRecovery._component_metrics(
        prepared,
        state,
        exponent,
        params,
        solution_record,
    )
    metrics = _with_adaptive_settle_status(metrics, diagnostics)
    return metrics, diagnostics
end

function _component_selection_key(row::GraphRecovery.ComponentRecoveryMetrics)
    return (
        abs(row.count_error),
        row.profile_squared_error,
        abs(row.exponent),
        row.exponent,
    )
end

function _component_constrained_key(row::GraphRecovery.ComponentRecoveryMetrics)
    return (
        row.profile_squared_error,
        abs(row.exponent),
        row.exponent,
    )
end

function _global_selection_key(evaluation::GraphRecovery.RecoveryEvaluation)
    return (
        evaluation.total_abs_count_error,
        evaluation.profile_relative_rmse,
        abs(first(evaluation.exponents)),
        first(evaluation.exponents),
    )
end

function _global_constrained_key(evaluation::GraphRecovery.RecoveryEvaluation)
    return (
        evaluation.profile_relative_rmse,
        abs(first(evaluation.exponents)),
        first(evaluation.exponents),
    )
end

function _minimum_by(values::AbstractVector, key::Function)
    isempty(values) && error("cannot select a minimum from an empty collection")
    return values[argmin(key.(values))]
end

function _request_boundary!(requested::Vector{Symbol}, exponent::Int, bounds::Tuple{Int,Int})
    exponent == bounds[1] && :lower ∉ requested && push!(requested, :lower)
    exponent == bounds[2] && :upper ∉ requested && push!(requested, :upper)
    return requested
end

function _request_improving_missing_component_sides!(
    requested::Vector{Symbol},
    rows::Vector{GraphRecovery.ComponentRecoveryMetrics},
)
    if length(rows) == 1
        :lower ∉ requested && push!(requested, :lower)
        :upper ∉ requested && push!(requested, :upper)
        return requested
    end
    abs(first(rows).count_error) < abs(rows[2].count_error) &&
        :lower ∉ requested && push!(requested, :lower)
    abs(last(rows).count_error) < abs(rows[end - 1].count_error) &&
        :upper ∉ requested && push!(requested, :upper)
    return requested
end

function _request_improving_missing_global_sides!(
    requested::Vector{Symbol},
    rows::Vector{GraphRecovery.RecoveryEvaluation},
)
    if length(rows) == 1
        :lower ∉ requested && push!(requested, :lower)
        :upper ∉ requested && push!(requested, :upper)
        return requested
    end
    first(rows).total_abs_count_error < rows[2].total_abs_count_error &&
        :lower ∉ requested && push!(requested, :lower)
    last(rows).total_abs_count_error < rows[end - 1].total_abs_count_error &&
        :upper ∉ requested && push!(requested, :upper)
    return requested
end

function _adaptive_stage_decision(
    bounds::Tuple{Int,Int},
    exponents::Vector{Int},
    values::Vector{_DevelopmentExponentEvaluation},
    ;
    extra_requested_sides::AbstractVector{Symbol}=Symbol[],
)
    component_count = length(first(values).metrics)
    all(length(value.metrics) == component_count for value in values) ||
        error("adaptive recovery exponent evaluations must have aligned components")
    component_rows = [
        [value.metrics[component_index] for value in values]
        for component_index in 1:component_count
    ]
    global_rows = [GraphRecovery._aggregate_evaluation(value.metrics) for value in values]
    requested = Symbol[]
    component_errors = Int[]
    component_constrained_exponents = Union{Nothing,Int}[]
    objective_infeasibility = 0
    objective_profile_loss = 0.0

    for rows in component_rows
        best_tier = _minimum_by(rows, _component_selection_key)
        push!(component_errors, abs(best_tier.count_error))
        objective_infeasibility += abs(best_tier.count_error)
        objective_profile_loss += best_tier.profile_relative_rmse
        constrained = [row for row in rows if iszero(row.count_error)]
        if isempty(constrained)
            push!(component_constrained_exponents, nothing)
            _request_improving_missing_component_sides!(requested, rows)
        else
            best = _minimum_by(constrained, _component_constrained_key)
            push!(component_constrained_exponents, best.exponent)
            _request_boundary!(requested, best.exponent, bounds)
        end
    end

    global_best_tier = _minimum_by(global_rows, _global_selection_key)
    global_min_count_error = global_best_tier.total_abs_count_error
    objective_infeasibility += global_min_count_error
    objective_profile_loss += global_best_tier.profile_relative_rmse
    global_constrained = [
        row for row in global_rows if row.component_count_targets_met
    ]
    global_constrained_exponent::Union{Nothing,Int} = nothing
    if isempty(global_constrained)
        _request_improving_missing_global_sides!(requested, global_rows)
    else
        best = _minimum_by(global_constrained, _global_constrained_key)
        global_constrained_exponent = first(best.exponents)
        _request_boundary!(requested, global_constrained_exponent, bounds)
    end
    all(side -> side in (:lower, :upper), extra_requested_sides) || error(
        "extra adaptive-search boundary requests must be :lower or :upper",
    )
    for side in extra_requested_sides
        side in requested || push!(requested, side)
    end
    requested = [side for side in (:lower, :upper) if side in requested]

    # The fractional loss term is strictly less than one, so a one-unit count
    # improvement always dominates any profile-loss change.
    bounded_profile_loss = objective_profile_loss / (1 + objective_profile_loss)
    objective = Float64(objective_infeasibility) + bounded_profile_loss
    value = _DevelopmentStageValue(
        component_errors,
        component_constrained_exponents,
        global_min_count_error,
        global_constrained_exponent,
    )
    missing_component_feasibility = any(isnothing, component_constrained_exponents)
    return AdaptiveExponentStageDecision(
        value;
        requested_sides=requested,
        objective=objective,
        unresolved_boundary=!isempty(requested) || missing_component_feasibility,
    )
end

function _certification_boundary_sides(
    bounds::Tuple{Int,Int},
    protocol::AdaptiveExponentProtocol,
)
    requested = Symbol[]
    bounds[1] > protocol.hard_min && push!(requested, :lower)
    bounds[2] < protocol.hard_max && push!(requested, :upper)
    return requested
end

function _search_surface(
    prepared,
    baseline::RDParameters,
    protocol::RecoveryDevelopmentProtocol,
    regime::RecoveryCohort.RecoveryRegime,
)
    coordinates = [
        _normalized_component_coordinates(component, regime)
        for component in prepared
    ]
    references = [component.reference for component in prepared]
    evaluate_exponent = exponent -> begin
        metrics = GraphRecovery.ComponentRecoveryMetrics[]
        settling = RecoveryAdaptive.AdaptiveSettleDiagnostics[]
        for component in prepared
            row, diagnostics = _evaluate_component_exponent(
                component,
                baseline,
                exponent,
                protocol,
            )
            push!(metrics, row)
            push!(settling, diagnostics)
        end
        _DevelopmentExponentEvaluation(metrics, settling)
    end
    evaluate_stage = (bounds, exponents, values) -> begin
        component_rows = [
            [value.metrics[component_index] for value in values]
            for component_index in eachindex(prepared)
        ]
        observability = recovery_observability_report(
            references,
            component_rows,
            [coordinate[1] for coordinate in coordinates],
            [coordinate[2] for coordinate in coordinates];
            levels=protocol.readout_levels,
            alias_resolutions=protocol.alias_resolutions,
            max_selection_regret=protocol.max_selection_regret,
        )
        requested_sides = unique(vcat(
            observability_boundary_sides(observability, bounds),
            _certification_boundary_sides(bounds, protocol.exponents),
        ))
        return _adaptive_stage_decision(
            bounds,
            exponents,
            values;
            extra_requested_sides=requested_sides,
        )
    end
    return search_adaptive_exponent_bounds(
        evaluate_exponent,
        evaluate_stage;
        protocol=protocol.exponents,
    )
end

function _search_stages(search)
    return [
        RecoveryDevelopmentSearchStage(
            stage.bounds,
            copy(stage.newly_evaluated_exponents),
            copy(stage.requested_sides),
            something(stage.objective, 0.0),
            stage.unresolved_boundary,
            stage.materially_unchanged,
            stage.plateau_streak,
        ) for stage in search.diagnostics.stages
    ]
end

function _surface_rows(
    spec::RecoveryDevelopmentSpec,
    seed::Int,
    placement::RecoveryCohort.RecoveryPlacement,
    case_id::String,
    prepared,
    search,
    ;
    search_termination::Symbol,
    unresolved_boundary::Bool,
    case_numerical_ready::Bool,
)
    rows = RecoveryDevelopmentSurfaceRow[]
    lower, upper = search.diagnostics.final_bounds
    stratum = RecoveryCohort._placement_stratum(spec.regime, placement)
    coordinates = [
        _normalized_component_coordinates(component, spec.regime)
        for component in prepared
    ]
    target_readouts = [
        recovery_readout(
            prepared[idx].reference,
            coordinates[idx][1],
            coordinates[idx][2],
        ) for idx in eachindex(prepared)
    ]
    for component_index in eachindex(prepared)
        target = target_readouts[component_index]
        for exponent in lower:upper
            value = search.cache[exponent]
            metrics = value.metrics[component_index]
            settling = value.settling[component_index]
            observed = recovery_readout(
                metrics,
                coordinates[component_index][1],
                coordinates[component_index][2],
            )
            push!(
                rows,
                RecoveryDevelopmentSurfaceRow(
                    case_id,
                    spec.protocol.evidence_scope,
                    spec.regime.regime_id,
                    seed,
                    placement.top,
                    placement.left,
                    spec.regime.patch_rows,
                    spec.regime.patch_cols,
                    stratum,
                    metrics.component_id,
                    length(metrics.nodes),
                    exponent,
                    metrics.D_a,
                    metrics.D_i,
                    target.domain_count,
                    observed.domain_count,
                    metrics.count_error,
                    target.activator_mass,
                    observed.activator_mass,
                    target.centroid_x,
                    target.centroid_y,
                    observed.centroid_x,
                    observed.centroid_y,
                    metrics.profile_squared_error,
                    metrics.reference_energy,
                    metrics.profile_relative_rmse,
                    metrics.inhibitor_profile_relative_rmse,
                    metrics.shape_rmse,
                    metrics.mask_hamming_fraction,
                    settling.termination,
                    settling.elapsed_time,
                    settling.chunk_count,
                    settling.terminal_residual_linf,
                    settling.reached_steady,
                    copy(settling.checkpoints),
                    search_termination,
                    unresolved_boundary,
                    case_numerical_ready,
                ),
            )
        end
    end
    sort!(rows; by=row -> (row.component_id, row.exponent))
    return rows
end

function _final_component_rows(prepared, search)
    lower, upper = search.diagnostics.final_bounds
    return [
        [search.cache[exponent].metrics[idx] for exponent in lower:upper]
        for idx in eachindex(prepared)
    ]
end

function _development_failure(
    spec::RecoveryDevelopmentSpec,
    seed::Int,
    placement::RecoveryCohort.RecoveryPlacement,
    stage::Symbol,
    error_type::String,
    message::String;
    reference_reached_steady::Union{Nothing,Bool}=nothing,
    reference_terminal_residual_linf::Union{Nothing,Float64}=nothing,
    reference_settle_checkpoints::Union{
        Nothing,
        Vector{AdaptiveSettleCheckpoint},
    }=nothing,
    search_termination::Union{Nothing,Symbol}=nothing,
    final_exponent_bounds::Union{Nothing,Tuple{Int,Int}}=nothing,
    unresolved_boundary::Union{Nothing,Bool}=nothing,
    all_final_rows_reached_steady::Union{Nothing,Bool}=nothing,
)
    return RecoveryDevelopmentFailure(
        recovery_development_case_id(spec, seed, placement),
        spec.protocol.evidence_scope,
        spec.regime.regime_id,
        seed,
        placement.top,
        placement.left,
        spec.regime.patch_rows,
        spec.regime.patch_cols,
        RecoveryCohort._placement_stratum(spec.regime, placement),
        stage,
        error_type,
        message,
        reference_reached_steady,
        reference_terminal_residual_linf,
        reference_settle_checkpoints,
        search_termination,
        final_exponent_bounds,
        unresolved_boundary,
        all_final_rows_reached_steady,
    )
end

function _run_case(
    spec::RecoveryDevelopmentSpec,
    seed::Int,
    placement::RecoveryCohort.RecoveryPlacement,
    connected,
    baseline::RDParameters,
    settled::Vector{Float64},
    reference_diagnostics,
)
    edges = isolate_rectangle_edges(
        spec.regime.rows,
        spec.regime.cols,
        placement.top,
        placement.left,
        spec.regime.patch_rows,
        spec.regime.patch_cols,
    )
    isempty(edges) && error("development lesion must remove at least one edge")
    severed = graph_without_edges(connected, edges)
    length(graph_connected_components(severed)) > 1 ||
        error("development lesion must disconnect the graph")
    prepared = GraphRecovery._prepare_components(
        settled,
        severed,
        spec.protocol.active_fraction,
    )
    search = _search_surface(prepared, baseline, spec.protocol, spec.regime)
    case_id = recovery_development_case_id(spec, seed, placement)
    final_rows = _final_component_rows(prepared, search)
    all_steady = all(row.reached_steady for rows in final_rows for row in rows)
    unresolved = search.diagnostics.unresolved_boundary
    termination = search.diagnostics.termination
    final_bounds = search.diagnostics.final_bounds
    numerical_ready = all_steady && !unresolved
    surfaces = _surface_rows(
        spec,
        seed,
        placement,
        case_id,
        prepared,
        search;
        search_termination=termination,
        unresolved_boundary=unresolved,
        case_numerical_ready=numerical_ready,
    )
    if !all_steady
        failure = _development_failure(
            spec,
            seed,
            placement,
            :equilibrium,
            "NumericalReadinessFailure",
            "one or more final component/exponent rows did not reach steady_tol";
            reference_reached_steady=true,
            reference_terminal_residual_linf=
                reference_diagnostics.terminal_residual_linf,
            reference_settle_checkpoints=copy(reference_diagnostics.checkpoints),
            search_termination=termination,
            final_exponent_bounds=final_bounds,
            unresolved_boundary=unresolved,
            all_final_rows_reached_steady=false,
        )
        return surfaces, failure
    end
    if unresolved
        failure = _development_failure(
            spec,
            seed,
            placement,
            :exponent_search,
            "UnresolvedBoundary",
            "adaptive exponent search terminated with an unresolved count-constrained boundary";
            reference_reached_steady=true,
            reference_terminal_residual_linf=
                reference_diagnostics.terminal_residual_linf,
            reference_settle_checkpoints=copy(reference_diagnostics.checkpoints),
            search_termination=termination,
            final_exponent_bounds=final_bounds,
            unresolved_boundary=true,
            all_final_rows_reached_steady=true,
        )
        return surfaces, failure
    end

    coordinates = [
        _normalized_component_coordinates(component, spec.regime)
        for component in prepared
    ]
    observability = recovery_observability_report(
        [component.reference for component in prepared],
        final_rows,
        [coordinate[1] for coordinate in coordinates],
        [coordinate[2] for coordinate in coordinates];
        levels=spec.protocol.readout_levels,
        alias_resolutions=spec.protocol.alias_resolutions,
        max_selection_regret=spec.protocol.max_selection_regret,
    )
    record = RecoveryDevelopmentCase(
        case_id,
        spec.protocol.evidence_scope,
        spec.regime.regime_id,
        seed,
        placement.top,
        placement.left,
        spec.regime.patch_rows,
        spec.regime.patch_cols,
        RecoveryCohort._placement_stratum(spec.regime, placement),
        reference_diagnostics.termination,
        reference_diagnostics.elapsed_time,
        reference_diagnostics.chunk_count,
        reference_diagnostics.terminal_residual_linf,
        copy(reference_diagnostics.checkpoints),
        termination,
        search.diagnostics.initial_bounds,
        search.diagnostics.hard_bounds,
        final_bounds,
        false,
        length(search.cache),
        true,
        true,
        _search_stages(search),
        observability,
    )
    return surfaces, record
end

function _case_sort_key(record::RecoveryDevelopmentCaseRecord)
    return (record.seed, record.patch_top, record.patch_left)
end

function run_recovery_development(spec::RecoveryDevelopmentSpec)
    canonical = _canonical_spec(spec)
    surface_rows = RecoveryDevelopmentSurfaceRow[]
    cases = RecoveryDevelopmentCaseRecord[]
    reference_preparation_count = 0
    for seed in canonical.seeds
        reference_preparation_count += 1
        prepared_reference = try
            _prepare_reference(canonical, seed)
        catch exception
            exception isa InterruptException && rethrow()
            for placement in canonical.placements
                push!(
                    cases,
                    _development_failure(
                        canonical,
                        seed,
                        placement,
                        :reference,
                        string(typeof(exception)),
                        sprint(showerror, exception);
                        reference_reached_steady=false,
                    ),
                )
            end
            continue
        end
        connected, baseline, settled, reference_diagnostics = prepared_reference
        if !reference_diagnostics.reached_steady
            for placement in canonical.placements
                push!(
                    cases,
                    _development_failure(
                        canonical,
                        seed,
                        placement,
                        :reference,
                        "NumericalReadinessFailure",
                        "connected reference did not reach " *
                        "steady_tol=$(canonical.protocol.steady_tol) by " *
                        "max_time=$(canonical.protocol.settling.max_time); " *
                        "terminal_residual_linf=" *
                        string(reference_diagnostics.terminal_residual_linf);
                        reference_reached_steady=false,
                        reference_terminal_residual_linf=
                            reference_diagnostics.terminal_residual_linf,
                        reference_settle_checkpoints=
                            copy(reference_diagnostics.checkpoints),
                    ),
                )
            end
            continue
        end
        for placement in canonical.placements
            local_surfaces = RecoveryDevelopmentSurfaceRow[]
            record = try
                local_surfaces, completed = _run_case(
                    canonical,
                    seed,
                    placement,
                    connected,
                    baseline,
                    settled,
                    reference_diagnostics,
                )
                completed
            catch exception
                exception isa InterruptException && rethrow()
                _development_failure(
                    canonical,
                    seed,
                    placement,
                    :case,
                    string(typeof(exception)),
                    sprint(showerror, exception);
                    reference_reached_steady=true,
                    reference_terminal_residual_linf=
                        reference_diagnostics.terminal_residual_linf,
                    reference_settle_checkpoints=
                        copy(reference_diagnostics.checkpoints),
                )
            end
            append!(surface_rows, local_surfaces)
            push!(cases, record)
        end
    end
    sort!(surface_rows; by=row -> (
        row.seed,
        row.patch_top,
        row.patch_left,
        row.component_id,
        row.exponent,
    ))
    sort!(cases; by=_case_sort_key)
    provisional = RecoveryDevelopmentResult(
        DEVELOPMENT_RESULT_SCHEMA_VERSION,
        DEVELOPMENT_PROTOCOL_VERSION,
        canonical.development_id,
        canonical.regime,
        canonical.protocol,
        canonical.seeds,
        canonical.placements,
        reference_preparation_count,
        surface_rows,
        cases,
        RecoveryDevelopmentSummary(
            DEVELOPMENT_ARTIFACT_SCHEMA_VERSION,
            DEVELOPMENT_PROTOCOL_VERSION,
            canonical.development_id,
            canonical.protocol.evidence_scope,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0.0,
            0,
            RecoveryDevelopmentReadoutSummary[],
            nothing,
            String[],
        ),
    )
    summary = analyze_recovery_development(provisional)
    return RecoveryDevelopmentResult(
        provisional.schema_version,
        provisional.protocol_version,
        provisional.development_id,
        provisional.regime,
        provisional.protocol,
        provisional.seeds,
        provisional.placements,
        provisional.reference_preparation_count,
        provisional.response_surface_rows,
        provisional.observability_cases,
        summary,
    )
end

function _rate(numerator::Int, denominator::Int)
    denominator == 0 && return 0.0
    return numerator / denominator
end

function _aggregate_diagnostic(record::RecoveryDevelopmentCase, level::Symbol)
    return only([
        diagnostic for diagnostic in record.observability.aggregate
        if diagnostic.level == level
    ])
end

function _surface_metric_for_observability(row::RecoveryDevelopmentSurfaceRow)
    nodes = collect(1:row.component_size)
    observed_A = fill(row.observed_activator_mass / row.component_size, row.component_size)
    inhibitor_energy = 1.0
    inhibitor_squared_error = row.inhibitor_profile_relative_rmse ^ 2 * inhibitor_energy
    return GraphRecovery.ComponentRecoveryMetrics(
        row.component_id,
        nodes,
        row.exponent,
        row.D_a,
        row.D_i,
        string(row.settle_termination),
        row.settle_elapsed_time,
        row.terminal_residual_linf,
        row.reached_steady,
        row.target_domain_count,
        row.observed_domain_count,
        row.count_error,
        row.target_domain_count,
        row.observed_domain_count,
        row.profile_relative_rmse,
        row.profile_relative_rmse,
        row.profile_relative_rmse,
        row.inhibitor_profile_relative_rmse,
        row.inhibitor_profile_relative_rmse,
        row.inhibitor_profile_relative_rmse,
        row.shape_rmse,
        row.mask_hamming_fraction,
        row.profile_squared_error,
        row.reference_energy,
        inhibitor_squared_error,
        inhibitor_energy,
        observed_A,
        zeros(row.component_size),
    )
end

function _recompute_surface_observability(
    case_rows::AbstractVector{RecoveryDevelopmentSurfaceRow},
    protocol::RecoveryDevelopmentProtocol,
)
    isempty(case_rows) && error("cannot recompute observability from an empty surface")
    component_ids = sort(unique([row.component_id for row in case_rows]))
    resolutions = RecoveryObservability._validate_resolutions(protocol.alias_resolutions)
    selection_resolution = maximum(resolutions)
    component_reports = RecoveryObservability.ComponentObservabilityReport[]
    metrics_by_component = Vector{GraphRecovery.ComponentRecoveryMetrics}[]
    for component_id in component_ids
        rows = sort(
            [row for row in case_rows if row.component_id == component_id];
            by=row -> row.exponent,
        )
        first_row = first(rows)
        target_signature = (
            first_row.target_domain_count,
            first_row.target_activator_mass,
            first_row.target_centroid_x,
            first_row.target_centroid_y,
            first_row.component_size,
        )
        all(
            row -> (
                row.target_domain_count,
                row.target_activator_mass,
                row.target_centroid_x,
                row.target_centroid_y,
                row.component_size,
            ) == target_signature,
            rows,
        ) || error("development surface target readout must be constant per component")
        target = RecoveryObservability.RecoveryReadout(
            first_row.target_domain_count,
            first_row.target_activator_mass,
            first_row.target_centroid_x,
            first_row.target_centroid_y,
        )
        candidates = RecoveryObservability.RecoveryReadoutCandidate[
            RecoveryObservability.RecoveryReadoutCandidate(
                row.exponent,
                RecoveryObservability.RecoveryReadout(
                    row.observed_domain_count,
                    row.observed_activator_mass,
                    row.observed_centroid_x,
                    row.observed_centroid_y,
                ),
            ) for row in rows
        ]
        metrics = [_surface_metric_for_observability(row) for row in rows]
        diagnostics = [
            RecoveryObservability._component_diagnostic(
                target,
                candidates,
                metrics,
                level,
                resolutions,
                selection_resolution,
                protocol.max_selection_regret,
            ) for level in protocol.readout_levels
        ]
        push!(
            component_reports,
            RecoveryObservability.ComponentObservabilityReport(
                component_id,
                target,
                length(rows),
                diagnostics,
            ),
        )
        push!(metrics_by_component, metrics)
    end
    aggregate = [
        RecoveryObservability._aggregate_diagnostic(
            level,
            component_reports,
            metrics_by_component,
            protocol.max_selection_regret,
        ) for level in protocol.readout_levels
    ]
    return RecoveryObservability.RecoveryObservabilityReport(
        1,
        copy(protocol.readout_levels),
        resolutions,
        selection_resolution,
        protocol.max_selection_regret,
        component_reports,
        aggregate,
    )
end

function _recompute_final_stage_decision(
    case_rows::AbstractVector{RecoveryDevelopmentSurfaceRow},
    protocol::RecoveryDevelopmentProtocol,
    report::RecoveryObservability.RecoveryObservabilityReport,
)
    exponents = sort(unique([row.exponent for row in case_rows]))
    component_ids = sort(unique([row.component_id for row in case_rows]))
    values = _DevelopmentExponentEvaluation[]
    for exponent in exponents
        metrics = GraphRecovery.ComponentRecoveryMetrics[
            _surface_metric_for_observability(only([
                row for row in case_rows
                if row.component_id == component_id && row.exponent == exponent
            ])) for component_id in component_ids
        ]
        push!(
            values,
            _DevelopmentExponentEvaluation(
                metrics,
                RecoveryAdaptive.AdaptiveSettleDiagnostics[],
            ),
        )
    end
    bounds = (first(exponents), last(exponents))
    extra_sides = unique(vcat(
        RecoveryObservability.observability_boundary_sides(report, bounds),
        _certification_boundary_sides(bounds, protocol.exponents),
    ))
    return _adaptive_stage_decision(
        bounds,
        exponents,
        values;
        extra_requested_sides=extra_sides,
    )
end

function _validate_settle_trace(
    checkpoints::AbstractVector{AdaptiveSettleCheckpoint},
    termination::Symbol,
    elapsed_time::Float64,
    chunk_count::Int,
    terminal_residual_linf::Float64,
    reached_steady::Bool,
    protocol::RecoveryDevelopmentProtocol,
    label::String,
)
    isempty(checkpoints) && error("$label must retain at least one settling checkpoint")
    length(checkpoints) == chunk_count + 1 || error(
        "$label checkpoint count does not match its chunk count",
    )
    confirmation_count = 0
    expected_elapsed = 0.0
    for (offset, checkpoint) in enumerate(checkpoints)
        expected_index = offset - 1
        isfinite(checkpoint.residual_linf) && checkpoint.residual_linf >= 0 || error(
            "$label checkpoint residuals must be finite and nonnegative",
        )
        checkpoint.chunk_index == expected_index || error(
            "$label checkpoint indices must be contiguous from zero",
        )
        if iszero(expected_index)
            checkpoint.elapsed_time == 0.0 || error(
                "$label initial checkpoint must have zero elapsed time",
            )
            isnothing(checkpoint.solver_retcode) || error(
                "$label initial checkpoint must not have a solver retcode",
            )
        else
            expected_elapsed = min(
                expected_elapsed + protocol.settling.chunk_time,
                protocol.settling.max_time,
            )
            checkpoint.elapsed_time == expected_elapsed || error(
                "$label checkpoint elapsed times do not match the settling protocol",
            )
            checkpoint.solver_retcode == "Success" || error(
                "$label integrated checkpoints must have a successful solver retcode",
            )
        end
        confirmation_count = RecoveryAdaptive._updated_confirmation_count(
            confirmation_count,
            checkpoint.residual_linf,
            protocol.steady_tol,
        )
        checkpoint.consecutive_below_tolerance == confirmation_count || error(
            "$label confirmation streak does not match checkpoint residuals",
        )
        if offset < length(checkpoints) &&
           confirmation_count >= protocol.settling.confirmation_checks
            error("$label continues after the required confirmation streak was reached")
        end
    end
    terminal = last(checkpoints)
    terminal.chunk_index == chunk_count || error("$label chunk count does not match its trace")
    terminal.elapsed_time == elapsed_time || error("$label elapsed time does not match its trace")
    terminal.residual_linf == terminal_residual_linf || error(
        "$label terminal residual does not match its trace",
    )
    confirmed = terminal.consecutive_below_tolerance >=
        protocol.settling.confirmation_checks
    expected_termination = confirmed ?
        (iszero(chunk_count) ? :steady_initial : :steady) : :time_cap
    termination == expected_termination || error(
        "$label termination does not match its persistent confirmation trace",
    )
    reached_steady == confirmed || error(
        "$label equilibrium status does not match persistent confirmation checkpoints",
    )
    if !confirmed && elapsed_time != protocol.settling.max_time
        error("$label unconfirmed trace must run to the configured time cap")
    end
    return nothing
end

function _validate_failure_reference_trace(
    record::RecoveryDevelopmentFailure,
    protocol::RecoveryDevelopmentProtocol,
)
    checkpoints = record.reference_settle_checkpoints
    terminal_residual = record.reference_terminal_residual_linf
    isnothing(checkpoints) == isnothing(terminal_residual) || error(
        "development failure reference residual and checkpoints must be retained together",
    )
    isnothing(checkpoints) && return nothing
    if isempty(checkpoints)
        record.stage == :reference || error(
            "post-reference development failures must retain nonempty reference checkpoints",
        )
        return nothing
    end
    record.reference_reached_steady isa Bool || error(
        "development failure reference equilibrium status must be retained with its checkpoints",
    )
    terminal = last(checkpoints)
    termination = if record.reference_reached_steady
        iszero(terminal.chunk_index) ? :steady_initial : :steady
    else
        :time_cap
    end
    _validate_settle_trace(
        checkpoints,
        termination,
        terminal.elapsed_time,
        terminal.chunk_index,
        terminal_residual,
        record.reference_reached_steady,
        protocol,
        "development failure reference",
    )
    return nothing
end

function _validate_failure_record(
    record::RecoveryDevelopmentFailure,
    case_rows::AbstractVector{RecoveryDevelopmentSurfaceRow},
    canonical::RecoveryDevelopmentSpec,
)
    record.stage in (:reference, :case, :equilibrium, :exponent_search) || error(
        "development failure has an unsupported stage: $(record.stage)",
    )
    _validate_failure_reference_trace(record, canonical.protocol)

    if record.stage in (:reference, :case)
        isempty(case_rows) || error(
            "development $(record.stage) failures must not retain response-surface rows",
        )
        all(isnothing, (
            record.search_termination,
            record.final_exponent_bounds,
            record.unresolved_boundary,
            record.all_final_rows_reached_steady,
        )) || error(
            "development $(record.stage) failures must not claim exponent-search status",
        )
        expected_reference_status = record.stage == :reference ? false : true
        record.reference_reached_steady === expected_reference_status || error(
            "development $(record.stage) failure has an inconsistent reference equilibrium status",
        )
        return nothing
    end

    isempty(case_rows) && error(
        "development $(record.stage) failures must retain their response surface",
    )
    record.reference_reached_steady === true || error(
        "development $(record.stage) failures require a confirmed reference equilibrium",
    )
    record.search_termination isa Symbol || error(
        "development $(record.stage) failure must retain its search termination",
    )
    record.final_exponent_bounds isa Tuple{Int,Int} || error(
        "development $(record.stage) failure must retain its final exponent bounds",
    )
    record.unresolved_boundary isa Bool || error(
        "development $(record.stage) failure must retain its boundary status",
    )
    record.all_final_rows_reached_steady isa Bool || error(
        "development $(record.stage) failure must retain its final equilibrium status",
    )

    lower, upper = record.final_exponent_bounds
    canonical.protocol.exponents.hard_min <= lower <= upper <=
        canonical.protocol.exponents.hard_max || error(
        "development failure final exponent bounds lie outside the registered hard range",
    )
    all(
        row -> row.search_termination == record.search_termination &&
            row.unresolved_boundary == record.unresolved_boundary &&
            !row.case_numerical_ready,
        case_rows,
    ) || error(
        "development failure status does not match its response surface",
    )
    all(row.reached_steady for row in case_rows) ==
        record.all_final_rows_reached_steady || error(
        "development failure equilibrium status does not match its response surface",
    )
    expected_exponents = collect(lower:upper)
    component_ids = sort(unique([row.component_id for row in case_rows]))
    for component_id in component_ids
        rows = [row for row in case_rows if row.component_id == component_id]
        sort([row.exponent for row in rows]) == expected_exponents || error(
            "development failure response surface does not cover its final exponent bounds",
        )
    end

    if record.stage == :equilibrium
        record.all_final_rows_reached_steady === false || error(
            "development equilibrium failure must retain at least one unconfirmed final row",
        )
    else
        record.error_type == "UnresolvedBoundary" || error(
            "development exponent-search failure must use the UnresolvedBoundary error type",
        )
        record.all_final_rows_reached_steady === true || error(
            "development exponent-search failure requires all final rows at equilibrium",
        )
        record.unresolved_boundary === true || error(
            "development exponent-search failure must retain an unresolved boundary",
        )
        record.search_termination in (:plateau, :hard_bound) || error(
            "development exponent-search failure must terminate at a plateau or hard bound",
        )
    end
    return nothing
end

function _validate_result_identity(result::RecoveryDevelopmentResult)
    canonical = _canonical_spec(
        RecoveryDevelopmentSpec(
            result.development_id,
            result.regime,
            result.protocol,
            result.seeds,
            result.placements,
        ),
    )
    result.seeds == canonical.seeds || error(
        "development result seeds must be canonical and match the registered spec",
    )
    result.placements == canonical.placements || error(
        "development result placements must be canonical and match the registered spec",
    )
    RecoveryCohort._json_bytes(result.regime) ==
        RecoveryCohort._json_bytes(canonical.regime) || error(
        "development result regime does not match the registered spec",
    )
    RecoveryCohort._json_bytes(result.protocol) ==
        RecoveryCohort._json_bytes(canonical.protocol) || error(
        "development result protocol does not match the registered spec",
    )
    expected = Dict{
        String,
        NamedTuple{
            (:seed, :top, :left, :stratum),
            Tuple{Int,Int,Int,Symbol},
        },
    }()
    for seed in canonical.seeds, placement in canonical.placements
        case_id = recovery_development_case_id(canonical, seed, placement)
        expected[case_id] = (
            seed=seed,
            top=placement.top,
            left=placement.left,
            stratum=RecoveryCohort._placement_stratum(canonical.regime, placement),
        )
    end
    length(result.observability_cases) == length(expected) || error(
        "development result must contain exactly one record per registered case",
    )
    seen_cases = Set{String}()
    for record in result.observability_cases
        haskey(expected, record.case_id) || error(
            "development result contains an unregistered case id: $(record.case_id)",
        )
        record.case_id ∉ seen_cases || error(
            "development result contains a duplicate case id: $(record.case_id)",
        )
        push!(seen_cases, record.case_id)
        identity = expected[record.case_id]
        (record.seed, record.patch_top, record.patch_left) ==
            (identity.seed, identity.top, identity.left) || error(
            "development case identity fields do not match $(record.case_id)",
        )
        record.placement_stratum == identity.stratum || error(
            "development case placement stratum does not match $(record.case_id)",
        )
        record.regime_id == canonical.regime.regime_id || error(
            "development case regime does not match the registered spec",
        )
        record.evidence_scope == canonical.protocol.evidence_scope || error(
            "development case evidence scope does not match the registered spec",
        )
        (record.patch_rows, record.patch_cols) ==
            (canonical.regime.patch_rows, canonical.regime.patch_cols) || error(
            "development case patch dimensions do not match the registered spec",
        )
    end
    seen_cases == Set(keys(expected)) || error(
        "development result case coverage does not match the registered Cartesian set",
    )
    seen_rows = Set{Tuple{String,Int,Int}}()
    for row in result.response_surface_rows
        haskey(expected, row.case_id) || error(
            "development surface contains an unregistered case id: $(row.case_id)",
        )
        identity = expected[row.case_id]
        (row.seed, row.patch_top, row.patch_left) ==
            (identity.seed, identity.top, identity.left) || error(
            "development surface identity fields do not match $(row.case_id)",
        )
        row.regime_id == canonical.regime.regime_id || error(
            "development surface regime does not match the registered spec",
        )
        row.evidence_scope == canonical.protocol.evidence_scope || error(
            "development surface evidence scope does not match the registered spec",
        )
        (row.patch_rows, row.patch_cols) ==
            (canonical.regime.patch_rows, canonical.regime.patch_cols) || error(
            "development surface patch dimensions do not match the registered spec",
        )
        row.placement_stratum == identity.stratum || error(
            "development surface placement stratum does not match $(row.case_id)",
        )
        row.component_id >= 1 && row.component_size >= 1 || error(
            "development surface component identity and size must be positive",
        )
        canonical.protocol.exponents.hard_min <= row.exponent <=
            canonical.protocol.exponents.hard_max || error(
            "development surface exponent lies outside the registered hard bounds",
        )
        row.count_error == row.observed_domain_count - row.target_domain_count || error(
            "development surface count error does not match observed minus target",
        )
        _validate_settle_trace(
            row.settle_checkpoints,
            row.settle_termination,
            row.settle_elapsed_time,
            row.settle_chunk_count,
            row.terminal_residual_linf,
            row.reached_steady,
            canonical.protocol,
            "development surface row",
        )
        key = (row.case_id, row.component_id, row.exponent)
        key ∉ seen_rows || error(
            "development surface contains a duplicate case/component/exponent row",
        )
        push!(seen_rows, key)
    end
    rows_by_case = Dict(
        case_id => [row for row in result.response_surface_rows if row.case_id == case_id]
        for case_id in keys(expected)
    )
    for record in result.observability_cases
        if record isa RecoveryDevelopmentFailure
            _validate_failure_record(record, rows_by_case[record.case_id], canonical)
            continue
        end
        record.numerical_ready && record.all_final_rows_reached_steady &&
            !record.unresolved_boundary || error(
            "completed development cases must be numerically ready with resolved boundaries",
        )
        record.final_exponent_bounds ==
            (canonical.protocol.exponents.hard_min, canonical.protocol.exponents.hard_max) || error(
            "completed development cases must cover the registered hard exponent range",
        )
        record.initial_exponent_bounds ==
            (canonical.protocol.exponents.initial_min, canonical.protocol.exponents.initial_max) || error(
            "completed development case initial bounds do not match the protocol",
        )
        record.hard_exponent_bounds == record.final_exponent_bounds || error(
            "completed development case hard bounds do not match its final surface",
        )
        _validate_settle_trace(
            record.reference_settle_checkpoints,
            record.reference_settle_termination,
            record.reference_settle_elapsed_time,
            record.reference_settle_chunk_count,
            record.reference_terminal_residual_linf,
            true,
            canonical.protocol,
            "development reference",
        )
        report = record.observability
        report.levels == canonical.protocol.readout_levels || error(
            "development observability levels do not match the registered protocol",
        )
        report.alias_resolutions == canonical.protocol.alias_resolutions || error(
            "development observability resolutions do not match the registered protocol",
        )
        report.selection_resolution == maximum(canonical.protocol.alias_resolutions) || error(
            "development observability selection resolution is inconsistent",
        )
        report.max_selection_regret == canonical.protocol.max_selection_regret || error(
            "development observability regret threshold does not match the protocol",
        )
        case_rows = rows_by_case[record.case_id]
        isempty(case_rows) && error(
            "completed development cases must retain their response surface",
        )
        all(
            row -> row.search_termination == record.search_termination &&
                row.unresolved_boundary == record.unresolved_boundary &&
                row.case_numerical_ready == record.numerical_ready &&
                row.reached_steady,
            case_rows,
        ) || error(
            "completed development case status does not match its response surface",
        )
        component_ids = sort(unique([row.component_id for row in case_rows]))
        report_component_ids = sort([
            component.component_id for component in report.components
        ])
        component_ids == report_component_ids || error(
            "development observability components do not match the response surface",
        )
        expected_exponents = collect(record.final_exponent_bounds[1]:record.final_exponent_bounds[2])
        record.exponent_evaluation_count == length(expected_exponents) || error(
            "completed development exponent evaluation count does not match the hard range",
        )
        for component in report.components
            rows = [row for row in case_rows if row.component_id == component.component_id]
            sort([row.exponent for row in rows]) == expected_exponents || error(
                "development observability candidates do not cover the final exponent bounds",
            )
            component.candidate_count == length(expected_exponents) || error(
                "development observability candidate count does not match the response surface",
            )
            available = Set(expected_exponents)
            for diagnostic in component.diagnostics
                diagnostic.level in report.levels || error(
                    "development component observability level is not registered",
                )
                diagnostic_exponents = vcat(
                    diagnostic.selected_exponent,
                    diagnostic.score_tied_exponents,
                    diagnostic.resolution_compatible_exponents,
                    diagnostic.score_tied_best_exponent,
                    diagnostic.target_count_exponents,
                    diagnostic.worst_case_exponent,
                    isnothing(diagnostic.count_constrained_oracle_exponent) ?
                        Int[] : [diagnostic.count_constrained_oracle_exponent],
                )
                all(exponent -> exponent in available, diagnostic_exponents) || error(
                    "development observability exponent is absent from the response surface",
                )
            end
        end
        [diagnostic.level for diagnostic in report.aggregate] == report.levels || error(
            "development aggregate observability ladder is incomplete or out of order",
        )
        recomputed = _recompute_surface_observability(case_rows, canonical.protocol)
        RecoveryCohort._json_bytes(report) == RecoveryCohort._json_bytes(recomputed) || error(
            "development observability report does not match the retained response surface",
        )
        final_decision = _recompute_final_stage_decision(
            case_rows,
            canonical.protocol,
            recomputed,
        )
        isempty(final_decision.requested_sides) && !final_decision.unresolved_boundary || error(
            "completed development case has an unresolved final boundary decision",
        )
        record.search_termination == :interior || error(
            "completed development cases must terminate with a resolved interior decision",
        )
    end
    return canonical
end

function analyze_recovery_development(result::RecoveryDevelopmentResult)
    result.schema_version == DEVELOPMENT_RESULT_SCHEMA_VERSION ||
        error("recovery development result schema must be 1")
    _validate_result_identity(result)
    completed = RecoveryDevelopmentCase[
        record for record in result.observability_cases
        if record isa RecoveryDevelopmentCase
    ]
    failures = RecoveryDevelopmentFailure[
        record for record in result.observability_cases
        if record isa RecoveryDevelopmentFailure
    ]
    registered = length(result.seeds) * length(result.placements)
    length(result.observability_cases) == registered ||
        error("development result must contain one observability record per registered case")
    required_seed_count = ceil(
        Int,
        result.protocol.required_sufficient_seed_fraction * length(result.seeds),
    )
    readout_summaries = RecoveryDevelopmentReadoutSummary[]
    for level in result.protocol.readout_levels
        sufficient_records = [
            record for record in completed
            if _aggregate_diagnostic(record, level).sufficient === true
        ]
        seed_summaries = RecoveryDevelopmentSeedReadoutSummary[]
        for seed in result.seeds
            registered_for_seed = length(result.placements)
            completed_for_seed = [record for record in completed if record.seed == seed]
            sufficient_for_seed = count(
                record -> _aggregate_diagnostic(record, level).sufficient === true,
                completed_for_seed,
            )
            registered_rate = _rate(sufficient_for_seed, registered_for_seed)
            push!(
                seed_summaries,
                RecoveryDevelopmentSeedReadoutSummary(
                    level,
                    seed,
                    registered_for_seed,
                    length(completed_for_seed),
                    sufficient_for_seed,
                    _rate(sufficient_for_seed, length(completed_for_seed)),
                    registered_rate,
                    registered_rate >=
                        result.protocol.min_within_seed_sufficiency_rate,
                ),
            )
        end
        seeds_meeting = count(summary -> summary.meets_within_seed_threshold, seed_summaries)
        sufficient_count = length(sufficient_records)
        registered_rate = _rate(sufficient_count, registered)
        qualifies = length(completed) == registered &&
            registered_rate >= result.protocol.min_overall_sufficiency_rate &&
            seeds_meeting >= required_seed_count
        push!(
            readout_summaries,
            RecoveryDevelopmentReadoutSummary(
                level,
                registered,
                length(completed),
                sufficient_count,
                _rate(sufficient_count, length(completed)),
                registered_rate,
                seeds_meeting,
                required_seed_count,
                qualifies,
                seed_summaries,
            ),
        )
    end
    smallest = findfirst(summary -> summary.qualifies, readout_summaries)
    reference_failures = count(failure -> failure.stage == :reference, failures)
    equilibrium_failures = count(failure -> failure.stage == :equilibrium, failures)
    unresolved_failures = count(
        failure -> failure.unresolved_boundary === true,
        failures,
    )
    return RecoveryDevelopmentSummary(
        DEVELOPMENT_ARTIFACT_SCHEMA_VERSION,
        DEVELOPMENT_PROTOCOL_VERSION,
        result.development_id,
        result.protocol.evidence_scope,
        registered,
        length(completed),
        length(failures),
        reference_failures,
        equilibrium_failures,
        unresolved_failures,
        length(completed),
        _rate(length(completed), registered),
        length(result.response_surface_rows),
        readout_summaries,
        isnothing(smallest) ? nothing : readout_summaries[smallest].level,
        [
            "All sufficiency rates include both completed and registered denominators; registered-denominator rates conservatively treat failed cases as insufficient.",
            "Observability is computed only after the reference and every retained component/exponent row reach equilibrium and adaptive exponent boundaries are resolved.",
            "A qualifying case exhausts the registered hard exponent range, preventing disconnected response regions or profile-guided support construction from changing the compact selector candidate set.",
            "Plateau termination only shortens a censored search; an unresolved requested boundary remains a failure and cannot qualify.",
            "This is a development-only capacity workflow; it has no delayed-capacity or feedback-controller path.",
        ],
    )
end

function _protocol_manifest(canonical::RecoveryDevelopmentSpec)
    return Dict(
        "schema_version" => DEVELOPMENT_ARTIFACT_SCHEMA_VERSION,
        "protocol_version" => DEVELOPMENT_PROTOCOL_VERSION,
        "development_result_schema_version" => DEVELOPMENT_RESULT_SCHEMA_VERSION,
        "development_id" => canonical.development_id,
        "evidence_scope" => canonical.protocol.evidence_scope,
        "code_revision" => get(ENV, "POLY_MORPHOGENESIS_REVISION", "unrecorded"),
        "julia_version" => string(VERSION),
        "package_version" => string(
            something(Base.pkgversion(parentmodule(@__MODULE__)), v"0.0.0"),
        ),
        "regime" => RecoveryCohort._cohort_jsonable(canonical.regime),
        "protocol" => RecoveryCohort._cohort_jsonable(canonical.protocol),
        "seeds" => copy(canonical.seeds),
        "placements" => RecoveryCohort._cohort_jsonable(canonical.placements),
        "registered_case_count" => length(canonical.seeds) * length(canonical.placements),
        "reserved_seed_ranges" => ["100:111", "200:211"],
    )
end

function write_recovery_development_protocol(
    spec::RecoveryDevelopmentSpec,
    output_dir::String,
)
    _guard_output_dir(output_dir)
    canonical = _canonical_spec(spec)
    path = joinpath(output_dir, "development-protocol.json")
    _guard_artifact_leaf(path)
    bytes = RecoveryCohort._json_bytes(_protocol_manifest(canonical))
    if isfile(path)
        read(path) == bytes || error(
            "development-protocol.json is immutable and does not match the requested run",
        )
    else
        RecoveryCohort._atomic_bytes_write(path, bytes)
    end
    return RecoveryDevelopmentProtocolManifest(path, RecoveryCohort._sha256_file(path))
end

function write_recovery_development_artifacts(
    result::RecoveryDevelopmentResult,
    output_dir::String,
)
    _guard_output_dir(output_dir)
    result.schema_version == DEVELOPMENT_RESULT_SCHEMA_VERSION ||
        error("recovery development result schema must be 1")
    result.protocol_version == DEVELOPMENT_PROTOCOL_VERSION ||
        error("recovery development protocol version must be 2")
    _validate_result_identity(result)
    protocol_path = joinpath(output_dir, "development-protocol.json")
    _guard_artifact_leaf(protocol_path)
    isfile(protocol_path) || error(
        "development-protocol.json must be frozen before writing development outcomes",
    )
    result_spec = RecoveryDevelopmentSpec(
        result.development_id,
        result.regime,
        result.protocol,
        result.seeds,
        result.placements,
    )
    canonical = _canonical_spec(result_spec)
    expected_protocol = RecoveryCohort._json_bytes(_protocol_manifest(canonical))
    read(protocol_path) == expected_protocol || error(
        "development-protocol.json does not match the completed development run",
    )
    response_path = joinpath(output_dir, "response-surfaces.jsonl")
    cases_path = joinpath(output_dir, "observability-cases.jsonl")
    summary_path = joinpath(output_dir, "observability-summary.json")
    manifest_path = joinpath(output_dir, "development-manifest.json")
    outcome_paths = [response_path, cases_path, summary_path, manifest_path]
    _guard_artifact_leaf.(outcome_paths)
    existing_outcomes = [path for path in outcome_paths if isfile(path)]
    isempty(existing_outcomes) || length(existing_outcomes) == length(outcome_paths) || error(
        "refusing to complete a partial development artifact set; use a new output directory",
    )
    sorted_surfaces = sort(copy(result.response_surface_rows); by=row -> (
        row.seed,
        row.patch_top,
        row.patch_left,
        row.component_id,
        row.exponent,
    ))
    sorted_cases = sort(copy(result.observability_cases); by=_case_sort_key)
    analysis = analyze_recovery_development(result)
    response_bytes = RecoveryCohort._json_bytes(sorted_surfaces; jsonl=true)
    cases_bytes = RecoveryCohort._json_bytes(sorted_cases; jsonl=true)
    summary_bytes = RecoveryCohort._json_bytes(analysis)
    response_hash = bytes2hex(sha256(response_bytes))
    cases_hash = bytes2hex(sha256(cases_bytes))
    summary_hash = bytes2hex(sha256(summary_bytes))
    protocol_hash = RecoveryCohort._sha256_file(protocol_path)
    manifest = Dict(
        "schema_version" => DEVELOPMENT_ARTIFACT_SCHEMA_VERSION,
        "protocol_version" => DEVELOPMENT_PROTOCOL_VERSION,
        "development_id" => result.development_id,
        "evidence_scope" => result.protocol.evidence_scope,
        "code_revision" => get(ENV, "POLY_MORPHOGENESIS_REVISION", "unrecorded"),
        "julia_version" => string(VERSION),
        "package_version" => string(
            something(Base.pkgversion(parentmodule(@__MODULE__)), v"0.0.0"),
        ),
        "registered_case_count" => analysis.registered_case_count,
        "completed_case_count" => analysis.completed_case_count,
        "failed_case_count" => analysis.failed_case_count,
        "files" => Dict(
            "development-protocol.json" => Dict("sha256" => protocol_hash),
            "response-surfaces.jsonl" => Dict("sha256" => response_hash),
            "observability-cases.jsonl" => Dict("sha256" => cases_hash),
            "observability-summary.json" => Dict("sha256" => summary_hash),
        ),
    )
    manifest_bytes = RecoveryCohort._json_bytes(manifest)
    _guard_output_dir(output_dir)
    _guard_artifact_leaf.(outcome_paths)
    RecoveryCohort._freeze_artifact_set([
        (response_path, response_bytes),
        (cases_path, cases_bytes),
        (summary_path, summary_bytes),
        (manifest_path, manifest_bytes),
    ])
    return RecoveryDevelopmentArtifacts(
        response_path,
        cases_path,
        summary_path,
        manifest_path,
        response_hash,
        cases_hash,
        summary_hash,
        bytes2hex(sha256(manifest_bytes)),
    )
end

end
