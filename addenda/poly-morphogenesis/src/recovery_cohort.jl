module RecoveryCohort

using JSON3
using Random
using SHA
using Statistics

using ..RD: RDParameters
using ..RDGraph: graph_residual_linf,
    graph_without_edges,
    grid_graph_config,
    make_rd_graph_state,
    settle_rd_graph!
using ..GridLesions: isolate_rectangle_edges
import ..GraphRecovery

export RecoveryRegime,
    RecoveryGateCriteria,
    RecoveryProtocol,
    RecoveryPlacement,
    RecoveryCohortSpec,
    RecoveryCaseSummary,
    RecoveryCaseFailure,
    RecoveryCohortResult,
    RecoverySeedSummary,
    RecoveryCohortAnalysis,
    RecoveryCohortProtocolManifest,
    RecoveryCohortArtifacts,
    recovery_placements,
    recovery_case_id,
    summarize_recovery_case,
    run_recovery_cohort,
    analyze_recovery_cohort,
    write_recovery_cohort_protocol_manifest,
    write_recovery_cohort_artifacts

Base.@kwdef struct RecoveryRegime
    regime_id::String = "grid4x6-d1-i30"
    rows::Int = 4
    cols::Int = 6
    patch_rows::Int = 2
    patch_cols::Int = 2
    field_width::Float64 = 40.0
    field_height::Float64 = 40.0
    baseline::RDParameters = RDParameters(D_a=1.0, D_i=30.0)
end

Base.@kwdef struct RecoveryGateCriteria
    require_complete_cases::Bool = true
    require_all_evaluations_at_equilibrium::Bool = true
    min_factorized_count_feasible_rate::Float64 = 0.80
    required_material_seed_fraction::Float64 = 5 / 6
    min_within_seed_material_rate::Float64 = 0.50
    require_positive_seed_median_ci_lower::Bool = true
    require_advantage_in_each_represented_stratum::Bool = true
    require_no_count_constrained_boundary_censoring::Bool = true
    bootstrap_replicates::Int = 10_000
    bootstrap_seed::Int = 20_260_713
    bootstrap_confidence_level::Float64 = 0.95
    min_count_sufficiency_rate::Float64 = 0.80
    required_count_sufficient_seed_fraction::Float64 = 5 / 6
    min_within_seed_count_sufficiency_rate::Float64 = 0.80
end

Base.@kwdef struct RecoveryProtocol
    settle_time::Float64 = 300.0
    steady_tol::Float64 = 1.0e-6
    recovery::GraphRecovery.GraphRecoveryConfig = GraphRecovery.GraphRecoveryConfig(
        include_delayed_capacity=false,
        include_feedback=false,
    )
    gates::RecoveryGateCriteria = RecoveryGateCriteria()
    evidence_scope::String = "capacity_cohort"
end

struct RecoveryPlacement
    top::Int
    left::Int
end

struct RecoveryCohortSpec
    cohort_id::String
    regime::RecoveryRegime
    protocol::RecoveryProtocol
    seeds::Vector{Int}
    placements::Vector{RecoveryPlacement}
end

function RecoveryCohortSpec(;
    cohort_id::String,
    regime::RecoveryRegime=RecoveryRegime(),
    protocol::RecoveryProtocol=RecoveryProtocol(),
    seeds::AbstractVector{<:Integer},
    placements::Union{Nothing,AbstractVector{RecoveryPlacement}}=nothing,
)
    selected = isnothing(placements) ? recovery_placements(regime) : placements
    return RecoveryCohortSpec(
        cohort_id,
        regime,
        protocol,
        Int.(collect(seeds)),
        collect(selected),
    )
end

struct RecoveryCaseSummary
    case_id::String
    evidence_scope::String
    regime_id::String
    seed::Int
    patch_top::Int
    patch_left::Int
    patch_rows::Int
    patch_cols::Int
    placement_stratum::Symbol
    component_sizes::Vector{Int}
    all_evaluations_at_equilibrium::Bool
    immediate_capacity_at_equilibrium::Bool
    delayed_capacity_at_equilibrium::Union{Nothing,Bool}
    feedback_at_equilibrium::Union{Nothing,Bool}
    preferred_exponent_span::Int
    outcome_class::Symbol
    meaningful_improvement::Float64
    material_factorized_advantage::Bool
    global_best_on_boundary::Bool
    factorized_best_on_boundary::Bool
    global_count_constrained_on_boundary::Union{Nothing,Bool}
    factorized_count_constrained_on_boundary::Union{Nothing,Bool}
    fixed_profile_loss::Float64
    global_profile_oracle_exponents::Vector{Int}
    global_profile_oracle_loss::Float64
    global_profile_oracle_count_targets_met::Bool
    factorized_profile_oracle_exponents::Vector{Int}
    factorized_profile_oracle_loss::Float64
    factorized_profile_oracle_count_targets_met::Bool
    global_count_feasible::Bool
    factorized_count_feasible::Bool
    global_count_constrained_exponents::Union{Nothing,Vector{Int}}
    global_count_constrained_loss::Union{Nothing,Float64}
    factorized_count_constrained_exponents::Union{Nothing,Vector{Int}}
    factorized_count_constrained_loss::Union{Nothing,Float64}
    global_count_constrained_shape_rmse::Union{Nothing,Float64}
    factorized_count_constrained_shape_rmse::Union{Nothing,Float64}
    global_count_constrained_mask_hamming::Union{Nothing,Float64}
    factorized_count_constrained_mask_hamming::Union{Nothing,Float64}
    global_count_constrained_inhibitor_loss::Union{Nothing,Float64}
    factorized_count_constrained_inhibitor_loss::Union{Nothing,Float64}
    global_count_selected_exponents::Vector{Int}
    global_count_selected_loss::Float64
    factorized_count_selected_exponents::Union{Nothing,Vector{Int}}
    factorized_count_selected_loss::Union{Nothing,Float64}
    factorized_count_selection_regret::Union{Nothing,Float64}
    count_selection_sufficient::Union{Nothing,Bool}
    profile_oracle_loss_reduction::Float64
    profile_oracle_relative_loss_reduction::Float64
    count_constrained_loss_reduction::Union{Nothing,Float64}
    count_constrained_relative_loss_reduction::Union{Nothing,Float64}
    factorized_count_feasibility_rescue::Bool
    delayed_outcome_class::Union{Nothing,Symbol}
    delayed_count_constrained_relative_loss_reduction::Union{Nothing,Float64}
    delayed_count_selection_regret::Union{Nothing,Float64}
    global_feedback_final_exponents::Union{Nothing,Vector{Int}}
    global_feedback_final_loss::Union{Nothing,Float64}
    global_feedback_count_targets_met::Union{Nothing,Bool}
    componentwise_feedback_final_exponents::Union{Nothing,Vector{Int}}
    componentwise_feedback_final_loss::Union{Nothing,Float64}
    componentwise_feedback_count_targets_met::Union{Nothing,Bool}
    feedback_loss_reduction::Union{Nothing,Float64}
    feedback_relative_loss_reduction::Union{Nothing,Float64}
    componentwise_feedback_count_rescue::Union{Nothing,Bool}
end

struct RecoveryCaseFailure
    case_id::String
    evidence_scope::String
    regime_id::String
    seed::Int
    patch_top::Int
    patch_left::Int
    stage::Symbol
    error_type::String
    message::String
end

const RecoveryCaseRecord = Union{RecoveryCaseSummary,RecoveryCaseFailure}

struct RecoveryCohortResult
    schema_version::Int
    cohort_id::String
    regime::RecoveryRegime
    protocol::RecoveryProtocol
    seeds::Vector{Int}
    placements::Vector{RecoveryPlacement}
    reference_preparation_count::Int
    cases::Vector{RecoveryCaseRecord}
end

struct RecoverySeedSummary
    seed::Int
    case_count::Int
    equilibrium_case_count::Int
    count_constrained_boundary_case_count::Int
    count_constrained_boundary_case_rate::Float64
    factorized_count_feasible_rate::Float64
    material_advantage_rate::Float64
    median_count_constrained_relative_loss_reduction::Union{Nothing,Float64}
    count_selection_sufficient_rate::Float64
end

struct RecoveryCohortAnalysis
    schema_version::Int
    cohort_id::String
    gate_criteria::RecoveryGateCriteria
    expected_case_count::Int
    completed_case_count::Int
    failed_case_count::Int
    equilibrium_case_count::Int
    count_constrained_boundary_case_count::Int
    count_constrained_boundary_case_rate::Float64
    factorized_count_feasible_rate::Float64
    material_advantage_rate::Float64
    count_selection_sufficient_rate::Float64
    outcome_class_counts::Dict{String,Int}
    placement_stratum_counts::Dict{String,Int}
    seed_summaries::Vector{RecoverySeedSummary}
    seed_median_gain_bootstrap_replicates::Int
    seed_median_gain_bootstrap_seed::Int
    seed_median_gain_confidence_level::Float64
    seed_median_gain_ci::Union{Nothing,Tuple{Float64,Float64}}
    seeds_meeting_material_gain::Int
    required_seeds_meeting_material_gain::Int
    required_count_sufficient_seeds::Int
    capacity_gate_pass::Bool
    count_sufficiency_gate_pass::Bool
    notes::Vector{String}
end

struct RecoveryCohortArtifacts
    cases_path::String
    summary_path::String
    manifest_path::String
    cases_sha256::String
    summary_sha256::String
    manifest_sha256::String
end

struct RecoveryCohortProtocolManifest
    path::String
    sha256::String
end

function _validate_identifier(value::String, label::String)
    isempty(value) && error("$label must not be empty")
    occursin(r"^[A-Za-z0-9._-]+$", value) ||
        error("$label may contain only letters, digits, '.', '_', and '-'")
    return value
end

function _validate_regime(regime::RecoveryRegime)
    _validate_identifier(regime.regime_id, "regime_id")
    regime.rows >= 1 || error("rows must be >= 1")
    regime.cols >= 1 || error("cols must be >= 1")
    1 <= regime.patch_rows <= regime.rows || error("patch_rows must lie in 1:rows")
    1 <= regime.patch_cols <= regime.cols || error("patch_cols must lie in 1:cols")
    regime.field_width > 0 || error("field_width must be > 0")
    regime.field_height > 0 || error("field_height must be > 0")
    regime.baseline.D_a > 0 || error("baseline D_a must be > 0")
    regime.baseline.D_i > 0 || error("baseline D_i must be > 0")
    return regime
end

function _validate_protocol(protocol::RecoveryProtocol)
    protocol.settle_time > 0 || error("settle_time must be > 0")
    protocol.steady_tol > 0 || error("steady_tol must be > 0")
    isempty(protocol.evidence_scope) && error("evidence_scope must not be empty")
    GraphRecovery._validate_recovery_config(protocol.recovery)
    _validate_gate_criteria(protocol.gates)
    return protocol
end

function _validate_rate(value::Float64, label::String)
    0 <= value <= 1 || error("$label must lie in [0, 1]")
    return value
end

function _validate_gate_criteria(criteria::RecoveryGateCriteria)
    _validate_rate(
        criteria.min_factorized_count_feasible_rate,
        "min_factorized_count_feasible_rate",
    )
    _validate_rate(
        criteria.required_material_seed_fraction,
        "required_material_seed_fraction",
    )
    _validate_rate(
        criteria.min_within_seed_material_rate,
        "min_within_seed_material_rate",
    )
    _validate_rate(criteria.min_count_sufficiency_rate, "min_count_sufficiency_rate")
    _validate_rate(
        criteria.required_count_sufficient_seed_fraction,
        "required_count_sufficient_seed_fraction",
    )
    _validate_rate(
        criteria.min_within_seed_count_sufficiency_rate,
        "min_within_seed_count_sufficiency_rate",
    )
    criteria.bootstrap_replicates >= 100 || error("bootstrap_replicates must be >= 100")
    criteria.bootstrap_seed >= 0 || error("bootstrap_seed must be nonnegative")
    0 < criteria.bootstrap_confidence_level < 1 ||
        error("bootstrap_confidence_level must lie in (0, 1)")
    return criteria
end

function recovery_placements(regime::RecoveryRegime)
    _validate_regime(regime)
    return [
        RecoveryPlacement(top, left)
        for top in 1:(regime.rows - regime.patch_rows + 1)
        for left in 1:(regime.cols - regime.patch_cols + 1)
    ]
end

function _placement_stratum(regime::RecoveryRegime, placement::RecoveryPlacement)
    touches_horizontal = placement.top == 1 ||
        placement.top + regime.patch_rows - 1 == regime.rows
    touches_vertical = placement.left == 1 ||
        placement.left + regime.patch_cols - 1 == regime.cols
    touches_horizontal && touches_vertical && return :corner
    (touches_horizontal || touches_vertical) && return :edge
    return :interior
end

function _canonical_placements(regime::RecoveryRegime, placements::Vector{RecoveryPlacement})
    isempty(placements) && error("cohort requires at least one placement")
    canonical = sort(copy(placements); by=placement -> (placement.top, placement.left))
    coordinates = [(placement.top, placement.left) for placement in canonical]
    length(unique(coordinates)) == length(coordinates) ||
        error("cohort placements must be unique")
    max_top = regime.rows - regime.patch_rows + 1
    max_left = regime.cols - regime.patch_cols + 1
    all(1 <= placement.top <= max_top for placement in canonical) ||
        error("placement top lies outside the rectangular placement range")
    all(1 <= placement.left <= max_left for placement in canonical) ||
        error("placement left lies outside the rectangular placement range")
    return canonical
end

function _canonical_spec(spec::RecoveryCohortSpec)
    _validate_identifier(spec.cohort_id, "cohort_id")
    _validate_regime(spec.regime)
    _validate_protocol(spec.protocol)
    isempty(spec.seeds) && error("cohort requires at least one seed")
    all(seed >= 0 for seed in spec.seeds) || error("cohort seeds must be nonnegative")
    length(unique(spec.seeds)) == length(spec.seeds) || error("cohort seeds must be unique")
    canonical_regime = deepcopy(spec.regime)
    return RecoveryCohortSpec(
        spec.cohort_id,
        canonical_regime,
        spec.protocol,
        sort(copy(spec.seeds)),
        _canonical_placements(canonical_regime, spec.placements),
    )
end

function recovery_case_id(
    spec::RecoveryCohortSpec,
    seed::Int,
    placement::RecoveryPlacement,
)
    seed >= 0 || error("seed must be nonnegative")
    return string(
        spec.cohort_id,
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

function _relative_reduction(reference::Float64, candidate::Float64)
    reference <= eps(Float64) && return 0.0
    return (reference - candidate) / reference
end

function summarize_recovery_case(
    case_id::String,
    regime::RecoveryRegime,
    seed::Int,
    placement::RecoveryPlacement,
    experiment::GraphRecovery.GraphRecoveryExperiment,
)
    feasibility = experiment.immediate_feasibility
    global_oracle = feasibility.global_best
    factorized_oracle = feasibility.factorized_best
    global_count_oracle = feasibility.global_count_constrained_best
    factorized_count_oracle = feasibility.factorized_count_constrained_best
    factorized_count_selected = feasibility.factorized_count_selected
    delayed = experiment.delayed_feasibility
    global_feedback_run = experiment.global_feedback
    componentwise_feedback_run = experiment.componentwise_feedback
    global_feedback = isnothing(global_feedback_run) ?
        nothing : global_feedback_run.final_evaluation
    componentwise_feedback = isnothing(componentwise_feedback_run) ?
        nothing : componentwise_feedback_run.final_evaluation
    material_advantage = feasibility.outcome_class in (
        :factorized_feasibility_rescue,
        :factorized_quality_rescue,
    )
    return RecoveryCaseSummary(
        case_id,
        experiment.evidence_scope,
        regime.regime_id,
        seed,
        placement.top,
        placement.left,
        regime.patch_rows,
        regime.patch_cols,
        _placement_stratum(regime, placement),
        copy(experiment.component_sizes),
        experiment.all_evaluations_at_equilibrium,
        experiment.immediate_capacity_at_equilibrium,
        experiment.delayed_capacity_at_equilibrium,
        experiment.feedback_at_equilibrium,
        feasibility.preferred_exponent_span,
        feasibility.outcome_class,
        feasibility.meaningful_improvement,
        material_advantage,
        feasibility.global_best_on_boundary,
        feasibility.factorized_best_on_boundary,
        feasibility.global_count_constrained_on_boundary,
        feasibility.factorized_count_constrained_on_boundary,
        experiment.fixed.final_evaluation.profile_relative_rmse,
        copy(global_oracle.exponents),
        global_oracle.profile_relative_rmse,
        global_oracle.component_count_targets_met,
        copy(factorized_oracle.exponents),
        factorized_oracle.profile_relative_rmse,
        factorized_oracle.component_count_targets_met,
        !isempty(feasibility.global_count_feasible_exponents),
        feasibility.factorized_count_feasible,
        isnothing(global_count_oracle) ? nothing : copy(global_count_oracle.exponents),
        isnothing(global_count_oracle) ? nothing : global_count_oracle.profile_relative_rmse,
        isnothing(factorized_count_oracle) ?
            nothing : copy(factorized_count_oracle.exponents),
        isnothing(factorized_count_oracle) ?
            nothing : factorized_count_oracle.profile_relative_rmse,
        isnothing(global_count_oracle) ? nothing : global_count_oracle.shape_rmse,
        isnothing(factorized_count_oracle) ? nothing : factorized_count_oracle.shape_rmse,
        isnothing(global_count_oracle) ? nothing : global_count_oracle.mask_hamming_fraction,
        isnothing(factorized_count_oracle) ?
            nothing : factorized_count_oracle.mask_hamming_fraction,
        isnothing(global_count_oracle) ?
            nothing : global_count_oracle.inhibitor_profile_relative_rmse,
        isnothing(factorized_count_oracle) ?
            nothing : factorized_count_oracle.inhibitor_profile_relative_rmse,
        copy(feasibility.global_count_selected.exponents),
        feasibility.global_count_selected.profile_relative_rmse,
        isnothing(factorized_count_selected) ?
            nothing : copy(factorized_count_selected.exponents),
        isnothing(factorized_count_selected) ?
            nothing : factorized_count_selected.profile_relative_rmse,
        feasibility.factorized_count_selection_regret,
        feasibility.count_selection_sufficient,
        global_oracle.profile_relative_rmse - factorized_oracle.profile_relative_rmse,
        _relative_reduction(
            global_oracle.profile_relative_rmse,
            factorized_oracle.profile_relative_rmse,
        ),
        feasibility.count_constrained_absolute_loss_reduction,
        feasibility.count_constrained_relative_loss_reduction,
        isempty(feasibility.global_count_feasible_exponents) &&
            feasibility.factorized_count_feasible,
        isnothing(delayed) ? nothing : delayed.outcome_class,
        isnothing(delayed) ? nothing : delayed.count_constrained_relative_loss_reduction,
        isnothing(delayed) ? nothing : delayed.factorized_count_selection_regret,
        isnothing(global_feedback_run) ? nothing : copy(global_feedback_run.final_exponents),
        isnothing(global_feedback) ? nothing : global_feedback.profile_relative_rmse,
        isnothing(global_feedback) ? nothing : global_feedback.component_count_targets_met,
        isnothing(componentwise_feedback_run) ?
            nothing : copy(componentwise_feedback_run.final_exponents),
        isnothing(componentwise_feedback) ?
            nothing : componentwise_feedback.profile_relative_rmse,
        isnothing(componentwise_feedback) ?
            nothing : componentwise_feedback.component_count_targets_met,
        if isnothing(global_feedback) || isnothing(componentwise_feedback)
            nothing
        else
            global_feedback.profile_relative_rmse - componentwise_feedback.profile_relative_rmse
        end,
        if isnothing(global_feedback) || isnothing(componentwise_feedback)
            nothing
        else
            _relative_reduction(
                global_feedback.profile_relative_rmse,
                componentwise_feedback.profile_relative_rmse,
            )
        end,
        if isnothing(global_feedback) || isnothing(componentwise_feedback)
            nothing
        else
            !global_feedback.component_count_targets_met &&
                componentwise_feedback.component_count_targets_met
        end,
    )
end

function _case_failure(
    case_id::String,
    spec::RecoveryCohortSpec,
    seed::Int,
    placement::RecoveryPlacement,
    stage::Symbol,
    exception,
)
    return RecoveryCaseFailure(
        case_id,
        spec.protocol.evidence_scope,
        spec.regime.regime_id,
        seed,
        placement.top,
        placement.left,
        stage,
        string(typeof(exception)),
        sprint(showerror, exception),
    )
end

function _prepare_reference(spec::RecoveryCohortSpec, seed::Int)
    regime = spec.regime
    protocol = spec.protocol
    connected = grid_graph_config(
        regime.rows,
        regime.cols;
        field_width=regime.field_width,
        field_height=regime.field_height,
        tspan=(0.0, protocol.settle_time),
        seed=seed,
        steady_tol=protocol.steady_tol,
    )
    baseline = _copy_parameters(regime.baseline)
    settled = make_rd_graph_state(connected; rng_seed=seed)
    solution = settle_rd_graph!(
        settled,
        baseline,
        connected;
        steady_stop=protocol.recovery.steady_stop,
    )
    residual = graph_residual_linf(settled, baseline, connected)
    protocol.recovery.steady_stop && residual > protocol.steady_tol && error(
        "connected reference did not reach steady_tol=$(protocol.steady_tol); " *
        "increase settle_time or set steady_stop=false for a finite-horizon cohort",
    )
    return connected, baseline, settled, solution
end

function _run_recovery_case(
    spec::RecoveryCohortSpec,
    seed::Int,
    placement::RecoveryPlacement,
    connected,
    baseline::RDParameters,
    settled::Vector{Float64},
    reference_solution,
)
    regime = spec.regime
    severed_edges = isolate_rectangle_edges(
        regime.rows,
        regime.cols,
        placement.top,
        placement.left,
        regime.patch_rows,
        regime.patch_cols,
    )
    severed = graph_without_edges(connected, severed_edges)
    experiment = GraphRecovery.graph_recovery_experiment(
        copy(settled),
        connected,
        severed,
        baseline;
        severed_edges=severed_edges,
        recovery_config=spec.protocol.recovery,
        reference_solver_retcode=string(reference_solution.retcode),
        reference_integration_end_time=Float64(reference_solution.t[end]),
        evidence_scope=spec.protocol.evidence_scope,
    )
    id = recovery_case_id(spec, seed, placement)
    return summarize_recovery_case(id, regime, seed, placement, experiment)
end

function run_recovery_cohort(spec::RecoveryCohortSpec)
    canonical = _canonical_spec(spec)
    cases = RecoveryCaseRecord[]
    reference_preparation_count = 0
    for seed in canonical.seeds
        reference_preparation_count += 1
        prepared = try
            _prepare_reference(canonical, seed)
        catch exception
            exception isa InterruptException && rethrow()
            for placement in canonical.placements
                id = recovery_case_id(canonical, seed, placement)
                push!(
                    cases,
                    _case_failure(
                        id,
                        canonical,
                        seed,
                        placement,
                        :reference,
                        exception,
                    ),
                )
            end
            continue
        end
        connected, baseline, settled, reference_solution = prepared
        for placement in canonical.placements
            id = recovery_case_id(canonical, seed, placement)
            record = try
                _run_recovery_case(
                    canonical,
                    seed,
                    placement,
                    connected,
                    baseline,
                    settled,
                    reference_solution,
                )
            catch exception
                exception isa InterruptException && rethrow()
                _case_failure(id, canonical, seed, placement, :case, exception)
            end
            push!(cases, record)
        end
    end
    return RecoveryCohortResult(
        2,
        canonical.cohort_id,
        canonical.regime,
        canonical.protocol,
        canonical.seeds,
        canonical.placements,
        reference_preparation_count,
        cases,
    )
end

function _rate(values::AbstractVector{Bool})
    isempty(values) && return 0.0
    return count(identity, values) / length(values)
end

function _maybe_median(values::AbstractVector{<:Real})
    isempty(values) && return nothing
    return Float64(median(values))
end

function _seed_summary(seed::Int, cases::Vector{RecoveryCaseSummary})
    reductions = Float64[
        case.count_constrained_relative_loss_reduction
        for case in cases
        if case.count_constrained_relative_loss_reduction isa Float64
    ]
    count_sufficiency = [case.count_selection_sufficient === true for case in cases]
    boundary_count = count(_count_constrained_boundary_censored, cases)
    boundary_rate = isempty(cases) ? 0.0 : boundary_count / length(cases)
    return RecoverySeedSummary(
        seed,
        length(cases),
        count(case -> case.all_evaluations_at_equilibrium, cases),
        boundary_count,
        boundary_rate,
        _rate([case.factorized_count_feasible for case in cases]),
        _rate([case.material_factorized_advantage for case in cases]),
        _maybe_median(reductions),
        _rate(count_sufficiency),
    )
end

function _count_constrained_boundary_censored(case::RecoveryCaseSummary)
    return something(case.global_count_constrained_on_boundary, false) ||
        something(case.factorized_count_constrained_on_boundary, false)
end

function _bootstrap_seed_median_ci(
    seed_medians::Vector{Float64};
    replicates::Int,
    rng_seed::Int,
    confidence_level::Float64,
)
    length(seed_medians) >= 2 || return nothing
    replicates >= 100 || error("bootstrap replicates must be >= 100")
    0 < confidence_level < 1 || error("confidence_level must lie in (0, 1)")
    rng = MersenneTwister(rng_seed)
    n = length(seed_medians)
    distribution = Vector{Float64}(undef, replicates)
    for replicate in 1:replicates
        sample = [seed_medians[rand(rng, 1:n)] for _ in 1:n]
        distribution[replicate] = median(sample)
    end
    tail_probability = (1 - confidence_level) / 2
    return (
        Float64(quantile(distribution, tail_probability)),
        Float64(quantile(distribution, 1 - tail_probability)),
    )
end

function analyze_recovery_cohort(result::RecoveryCohortResult)
    criteria = _validate_gate_criteria(result.protocol.gates)
    expected = length(result.seeds) * length(result.placements)
    completed = RecoveryCaseSummary[
        case for case in result.cases if case isa RecoveryCaseSummary
    ]
    failures = RecoveryCaseFailure[
        case for case in result.cases if case isa RecoveryCaseFailure
    ]
    classes = Dict(
        string(class) => count(case -> case.outcome_class == class, completed)
        for class in (
            :neither_count_feasible,
            :factorized_feasibility_rescue,
            :factorized_quality_rescue,
            :no_material_factorized_advantage,
        )
    )
    strata = Dict(
        string(stratum) => count(case -> case.placement_stratum == stratum, completed)
        for stratum in (:corner, :edge, :interior)
    )
    seed_summaries = [
        _seed_summary(seed, [case for case in completed if case.seed == seed])
        for seed in result.seeds
    ]
    seed_medians = Float64[
        summary.median_count_constrained_relative_loss_reduction
        for summary in seed_summaries
        if summary.median_count_constrained_relative_loss_reduction isa Float64
    ]
    ci = _bootstrap_seed_median_ci(
        seed_medians;
        replicates=criteria.bootstrap_replicates,
        rng_seed=criteria.bootstrap_seed,
        confidence_level=criteria.bootstrap_confidence_level,
    )
    meaningful = result.protocol.recovery.meaningful_improvement
    seeds_meeting = count(seed_summaries) do summary
        quality_gate = isnothing(summary.median_count_constrained_relative_loss_reduction) ||
            summary.median_count_constrained_relative_loss_reduction >= meaningful
        summary.material_advantage_rate >= criteria.min_within_seed_material_rate &&
            quality_gate
    end
    required_seeds = ceil(
        Int,
        criteria.required_material_seed_fraction * length(result.seeds),
    )
    required_count_seeds = ceil(
        Int,
        criteria.required_count_sufficient_seed_fraction * length(result.seeds),
    )
    factorized_feasibility_rate = _rate([
        case.factorized_count_feasible for case in completed
    ])
    boundary_case_count = count(_count_constrained_boundary_censored, completed)
    boundary_case_rate = isempty(completed) ? 0.0 : boundary_case_count / length(completed)
    material_rate = _rate([case.material_factorized_advantage for case in completed])
    count_sufficiency_values = [
        case.count_selection_sufficient === true for case in completed
    ]
    count_sufficiency_rate = _rate(count_sufficiency_values)
    represented_strata = [
        stratum for stratum in (:corner, :edge, :interior)
        if get(strata, string(stratum), 0) > 0
    ]
    advantage_in_each_stratum = all(
        any(
            case.placement_stratum == stratum && case.material_factorized_advantage
            for case in completed
        ) for stratum in represented_strata
    )
    completeness_gate = !criteria.require_complete_cases ||
        (length(completed) == expected && isempty(failures))
    equilibrium_gate = !criteria.require_all_evaluations_at_equilibrium ||
        all(case.all_evaluations_at_equilibrium for case in completed)
    interval_gate = !criteria.require_positive_seed_median_ci_lower ||
        (ci isa Tuple{Float64,Float64} && first(ci) > 0)
    stratum_gate = !criteria.require_advantage_in_each_represented_stratum ||
        advantage_in_each_stratum
    boundary_gate = !criteria.require_no_count_constrained_boundary_censoring ||
        iszero(boundary_case_count)
    capacity_gate = completeness_gate && equilibrium_gate &&
        factorized_feasibility_rate >= criteria.min_factorized_count_feasible_rate &&
        seeds_meeting >= required_seeds &&
        interval_gate && stratum_gate && boundary_gate
    seeds_passing = count(
        summary -> summary.count_selection_sufficient_rate >=
            criteria.min_within_seed_count_sufficiency_rate,
        seed_summaries,
    )
    count_gate = completeness_gate && equilibrium_gate && boundary_gate &&
        count_sufficiency_rate >= criteria.min_count_sufficiency_rate &&
        seeds_passing >= required_count_seeds
    return RecoveryCohortAnalysis(
        1,
        result.cohort_id,
        deepcopy(criteria),
        expected,
        length(completed),
        length(failures),
        count(case -> case.all_evaluations_at_equilibrium, completed),
        boundary_case_count,
        boundary_case_rate,
        factorized_feasibility_rate,
        material_rate,
        count_sufficiency_rate,
        classes,
        strata,
        seed_summaries,
        criteria.bootstrap_replicates,
        criteria.bootstrap_seed,
        criteria.bootstrap_confidence_level,
        ci,
        seeds_meeting,
        required_seeds,
        required_count_seeds,
        capacity_gate,
        count_gate,
        [
            "Placements are a finite census nested within seeds; seed summaries are the uncertainty units.",
            "The capacity gate is evaluated only from the criteria frozen in protocol.gates.",
            "The count-sufficiency gate evaluates nearest-baseline count-only selection against the count-constrained profile oracle without running feedback trajectories.",
            "A failed gate is a scientific result and does not make artifact generation fail.",
        ],
    )
end

_cohort_jsonable(value::Nothing) = nothing
_cohort_jsonable(value::Bool) = value
_cohort_jsonable(value::Number) = value
_cohort_jsonable(value::AbstractString) = value
_cohort_jsonable(value::Symbol) = String(value)
_cohort_jsonable(value::AbstractVector) = [_cohort_jsonable(entry) for entry in value]
_cohort_jsonable(value::Tuple) = [_cohort_jsonable(entry) for entry in value]
function _cohort_jsonable(value::AbstractDict)
    keys_in_order = sort!(collect(keys(value)); by=string)
    names = Tuple(Symbol(string(key)) for key in keys_in_order)
    length(unique(names)) == length(names) ||
        error("dictionary keys must remain unique after string conversion")
    values = Tuple(_cohort_jsonable(value[key]) for key in keys_in_order)
    return NamedTuple{names}(values)
end

function _cohort_jsonable(value)
    names = fieldnames(typeof(value))
    values = Tuple(_cohort_jsonable(getfield(value, name)) for name in names)
    return NamedTuple{names}(values)
end

function _json_bytes(value; jsonl::Bool=false)
    io = IOBuffer()
    if jsonl
        for entry in value
            JSON3.write(io, _cohort_jsonable(entry))
            write(io, '\n')
        end
    else
        JSON3.pretty(io, _cohort_jsonable(value))
        write(io, '\n')
    end
    return take!(io)
end

function _atomic_bytes_write(path::String, bytes::Vector{UInt8})
    mkpath(dirname(path))
    temporary, io = mktemp(dirname(path))
    moved = false
    try
        write(io, bytes)
        close(io)
        mv(temporary, path; force=true)
        moved = true
    finally
        isopen(io) && close(io)
        !moved && rm(temporary; force=true)
    end
    return path
end

function _freeze_artifact_set(artifacts::Vector{Tuple{String,Vector{UInt8}}})
    for (path, bytes) in artifacts
        if isfile(path)
            read(path) == bytes || error(
                "$(basename(path)) is immutable and does not match the requested cohort",
            )
        end
    end
    for (path, bytes) in artifacts
        isfile(path) || _atomic_bytes_write(path, bytes)
    end
    return nothing
end

_sha256_file(path::String) = bytes2hex(sha256(read(path)))

function _protocol_manifest(canonical::RecoveryCohortSpec)
    return Dict(
        "schema_version" => 1,
        "cohort_result_schema_version" => 2,
        "cohort_id" => canonical.cohort_id,
        "code_revision" => get(ENV, "POLY_MORPHOGENESIS_REVISION", "unrecorded"),
        "julia_version" => string(VERSION),
        "package_version" => string(
            something(Base.pkgversion(parentmodule(@__MODULE__)), v"0.0.0"),
        ),
        "regime" => _cohort_jsonable(canonical.regime),
        "protocol" => _cohort_jsonable(canonical.protocol),
        "seeds" => copy(canonical.seeds),
        "placements" => _cohort_jsonable(canonical.placements),
        "expected_case_count" => length(canonical.seeds) * length(canonical.placements),
    )
end

function write_recovery_cohort_protocol_manifest(
    spec::RecoveryCohortSpec,
    output_dir::String,
)
    canonical = _canonical_spec(spec)
    path = joinpath(output_dir, "recovery-protocol.json")
    frozen_bytes = _json_bytes(_protocol_manifest(canonical))
    if isfile(path)
        read(path) == frozen_bytes || error(
            "recovery-protocol.json is immutable and does not match the requested cohort",
        )
    else
        _atomic_bytes_write(path, frozen_bytes)
    end
    return RecoveryCohortProtocolManifest(path, _sha256_file(path))
end

function write_recovery_cohort_artifacts(
    result::RecoveryCohortResult,
    output_dir::String,
)
    result.schema_version == 2 || error("recovery cohort result schema must be 2")
    frozen_protocol_path = joinpath(output_dir, "recovery-protocol.json")
    isfile(frozen_protocol_path) || error(
        "recovery-protocol.json must be frozen before writing outcome artifacts",
    )
    result_spec = RecoveryCohortSpec(
        result.cohort_id,
        result.regime,
        result.protocol,
        result.seeds,
        result.placements,
    )
    expected_protocol = _json_bytes(_protocol_manifest(_canonical_spec(result_spec)))
    read(frozen_protocol_path) == expected_protocol || error(
        "recovery-protocol.json does not match the completed cohort specification",
    )
    frozen_protocol_hash = _sha256_file(frozen_protocol_path)
    analysis = analyze_recovery_cohort(result)
    cases_path = joinpath(output_dir, "recovery-cases.jsonl")
    summary_path = joinpath(output_dir, "recovery-summary.json")
    manifest_path = joinpath(output_dir, "recovery-manifest.json")
    cases_bytes = _json_bytes(result.cases; jsonl=true)
    summary_bytes = _json_bytes(analysis)
    cases_hash = bytes2hex(sha256(cases_bytes))
    summary_hash = bytes2hex(sha256(summary_bytes))
    manifest = Dict(
        "schema_version" => 1,
        "cohort_id" => result.cohort_id,
        "code_revision" => get(ENV, "POLY_MORPHOGENESIS_REVISION", "unrecorded"),
        "julia_version" => string(VERSION),
        "package_version" => string(
            something(Base.pkgversion(parentmodule(@__MODULE__)), v"0.0.0"),
        ),
        "regime" => _cohort_jsonable(result.regime),
        "protocol" => _cohort_jsonable(result.protocol),
        "seeds" => copy(result.seeds),
        "placements" => _cohort_jsonable(result.placements),
        "expected_case_count" => analysis.expected_case_count,
        "completed_case_count" => analysis.completed_case_count,
        "failed_case_count" => analysis.failed_case_count,
        "files" => Dict(
            "recovery-protocol.json" => Dict("sha256" => frozen_protocol_hash),
            "recovery-cases.jsonl" => Dict("sha256" => cases_hash),
            "recovery-summary.json" => Dict("sha256" => summary_hash),
        ),
    )
    manifest_bytes = _json_bytes(manifest)
    _freeze_artifact_set([
        (cases_path, cases_bytes),
        (summary_path, summary_bytes),
        (manifest_path, manifest_bytes),
    ])
    return RecoveryCohortArtifacts(
        cases_path,
        summary_path,
        manifest_path,
        cases_hash,
        summary_hash,
        bytes2hex(sha256(manifest_bytes)),
    )
end

end
