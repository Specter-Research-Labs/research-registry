module RecoveryAdaptive

using ..RD: RDParameters
using ..RDGraph: RDGraphConfig,
    graph_residual_linf,
    settle_rd_graph!

export AdaptiveSettlingProtocol,
    AdaptiveSettleCheckpoint,
    AdaptiveSettleDiagnostics,
    AdaptiveExponentProtocol,
    AdaptiveExponentStageDecision,
    AdaptiveExponentStageDiagnostics,
    AdaptiveExponentSearchDiagnostics,
    AdaptiveExponentSearchResult,
    settle_rd_graph_adaptive!,
    search_adaptive_exponent_bounds

Base.@kwdef struct AdaptiveSettlingProtocol
    chunk_time::Float64 = 300.0
    max_time::Float64 = 1200.0
    confirmation_checks::Int = 2
end

struct AdaptiveSettleCheckpoint
    chunk_index::Int
    elapsed_time::Float64
    residual_linf::Float64
    consecutive_below_tolerance::Int
    solver_retcode::Union{Nothing,String}
end

struct AdaptiveSettleDiagnostics
    termination::Symbol
    reached_steady::Bool
    elapsed_time::Float64
    chunk_count::Int
    required_confirmation_checks::Int
    achieved_confirmation_checks::Int
    terminal_residual_linf::Float64
    checkpoints::Vector{AdaptiveSettleCheckpoint}
end

function _validate_settling_protocol(protocol::AdaptiveSettlingProtocol)
    isfinite(protocol.chunk_time) && protocol.chunk_time > 0 ||
        error("adaptive settling chunk_time must be finite and > 0")
    isfinite(protocol.max_time) && protocol.max_time > 0 ||
        error("adaptive settling max_time must be finite and > 0")
    protocol.confirmation_checks >= 1 ||
        error("adaptive settling confirmation_checks must be >= 1")
    return protocol
end

function _checked_graph_residual(
    state::Vector{Float64},
    params::RDParameters,
    config::RDGraphConfig,
)
    residual = Float64(graph_residual_linf(state, params, config))
    isfinite(residual) || error("graph residual must remain finite during adaptive settling")
    return residual
end

function _settle_diagnostics(
    termination::Symbol,
    residual::Float64,
    protocol::AdaptiveSettlingProtocol,
    checkpoints::Vector{AdaptiveSettleCheckpoint},
)
    elapsed_time = last(checkpoints).elapsed_time
    return AdaptiveSettleDiagnostics(
        termination,
        termination in (:steady_initial, :steady),
        elapsed_time,
        length(checkpoints) - 1,
        protocol.confirmation_checks,
        last(checkpoints).consecutive_below_tolerance,
        residual,
        checkpoints,
    )
end

function _updated_confirmation_count(
    previous_count::Int,
    residual::Float64,
    steady_tol::Float64,
)
    previous_count >= 0 || error("confirmation count must be nonnegative")
    return residual <= steady_tol ? previous_count + 1 : 0
end

function settle_rd_graph_adaptive!(
    state::Vector{Float64},
    params::RDParameters,
    config::RDGraphConfig;
    protocol::AdaptiveSettlingProtocol=AdaptiveSettlingProtocol(),
)
    protocol = _validate_settling_protocol(protocol)
    initial_residual = _checked_graph_residual(state, params, config)
    confirmation_count = _updated_confirmation_count(
        0,
        initial_residual,
        config.steady_tol,
    )
    checkpoints = AdaptiveSettleCheckpoint[
        AdaptiveSettleCheckpoint(
            0,
            0.0,
            initial_residual,
            confirmation_count,
            nothing,
        ),
    ]
    confirmation_count >= protocol.confirmation_checks && return _settle_diagnostics(
        :steady_initial,
        initial_residual,
        protocol,
        checkpoints,
    )

    elapsed_time = 0.0
    chunk_index = 0
    time_origin = config.tspan[1]
    while elapsed_time < protocol.max_time
        chunk_index += 1
        next_elapsed_time = min(elapsed_time + protocol.chunk_time, protocol.max_time)
        solution = settle_rd_graph!(
            state,
            params,
            config;
            tspan=(time_origin + elapsed_time, time_origin + next_elapsed_time),
            steady_stop=false,
        )
        elapsed_time = next_elapsed_time
        residual = _checked_graph_residual(state, params, config)
        confirmation_count = _updated_confirmation_count(
            confirmation_count,
            residual,
            config.steady_tol,
        )
        push!(
            checkpoints,
            AdaptiveSettleCheckpoint(
                chunk_index,
                elapsed_time,
                residual,
                confirmation_count,
                string(solution.retcode),
            ),
        )
        confirmation_count >= protocol.confirmation_checks && return _settle_diagnostics(
            :steady,
            residual,
            protocol,
            checkpoints,
        )
    end
    return _settle_diagnostics(
        :time_cap,
        last(checkpoints).residual_linf,
        protocol,
        checkpoints,
    )
end

Base.@kwdef struct AdaptiveExponentProtocol
    initial_min::Int = -11
    initial_max::Int = 11
    hard_min::Int = -15
    hard_max::Int = 15
    expansion_step::Int = 2
    plateau_relative_tolerance::Float64 = 1.0e-3
    plateau_patience::Int = 2
end

struct AdaptiveExponentStageDecision{T}
    value::T
    requested_sides::Vector{Symbol}
    objective::Union{Nothing,Float64}
    unresolved_boundary::Bool
end

function AdaptiveExponentStageDecision(
    value;
    requested_sides::AbstractVector{Symbol}=Symbol[],
    objective::Union{Nothing,Real}=nothing,
    unresolved_boundary::Union{Nothing,Bool}=nothing,
)
    sides = Symbol[]
    for side in (:lower, :upper)
        side in requested_sides && push!(sides, side)
    end
    all(side in (:lower, :upper) for side in requested_sides) ||
        error("adaptive exponent requested_sides may contain only :lower and :upper")
    length(unique(requested_sides)) == length(requested_sides) ||
        error("adaptive exponent requested_sides must be unique")
    objective_value = if isnothing(objective)
        nothing
    else
        converted = Float64(objective)
        isfinite(converted) || error("adaptive exponent stage objective must be finite")
        converted
    end
    unresolved = something(unresolved_boundary, !isempty(sides))
    !isempty(sides) && !unresolved && error(
        "an adaptive exponent stage requesting expansion must mark its boundary unresolved",
    )
    return AdaptiveExponentStageDecision(value, sides, objective_value, unresolved)
end

struct AdaptiveExponentStageDiagnostics{T}
    bounds::Tuple{Int,Int}
    newly_evaluated_exponents::Vector{Int}
    requested_sides::Vector{Symbol}
    objective::Union{Nothing,Float64}
    unresolved_boundary::Bool
    materially_unchanged::Bool
    plateau_streak::Int
    value::T
end

struct AdaptiveExponentSearchDiagnostics{T}
    termination::Symbol
    initial_bounds::Tuple{Int,Int}
    hard_bounds::Tuple{Int,Int}
    final_bounds::Tuple{Int,Int}
    unresolved_boundary::Bool
    stages::Vector{AdaptiveExponentStageDiagnostics{T}}
end

struct AdaptiveExponentSearchResult{T,V}
    diagnostics::AdaptiveExponentSearchDiagnostics{T}
    cache::Dict{Int,V}
    final_value::T
end

function _validate_exponent_protocol(protocol::AdaptiveExponentProtocol)
    protocol.hard_min <= protocol.initial_min <= 0 <= protocol.initial_max <=
        protocol.hard_max || error(
        "adaptive exponent bounds must satisfy hard_min <= initial_min <= 0 <= initial_max <= hard_max",
    )
    protocol.expansion_step >= 1 ||
        error("adaptive exponent expansion_step must be >= 1")
    isfinite(protocol.plateau_relative_tolerance) &&
        protocol.plateau_relative_tolerance >= 0 || error(
        "adaptive exponent plateau_relative_tolerance must be finite and >= 0",
    )
    protocol.plateau_patience >= 1 ||
        error("adaptive exponent plateau_patience must be >= 1")
    return protocol
end

function _relative_objective_change(previous::Float64, current::Float64)
    scale = max(abs(previous), abs(current), eps(Float64))
    return abs(current - previous) / scale
end

function _populate_exponent_cache!(
    cache::Dict{Int,V},
    bounds::Tuple{Int,Int},
    evaluate_exponent::F,
) where {V,F}
    newly_evaluated = Int[]
    for exponent in bounds[1]:bounds[2]
        haskey(cache, exponent) && continue
        cache[exponent] = evaluate_exponent(exponent)
        push!(newly_evaluated, exponent)
    end
    return newly_evaluated
end

function _initial_exponent_cache(
    protocol::AdaptiveExponentProtocol,
    evaluate_exponent::F,
) where {F}
    first_exponent = protocol.initial_min
    first_value = evaluate_exponent(first_exponent)
    cache = Dict{Int,typeof(first_value)}(first_exponent => first_value)
    newly_evaluated = [first_exponent]
    for exponent in (first_exponent + 1):protocol.initial_max
        cache[exponent] = evaluate_exponent(exponent)
        push!(newly_evaluated, exponent)
    end
    return cache, newly_evaluated
end

function _evaluate_exponent_stage(
    cache::Dict{Int,V},
    bounds::Tuple{Int,Int},
    newly_evaluated::Vector{Int},
    evaluate_stage::F,
    previous_objective::Union{Nothing,Float64},
    previous_plateau_streak::Int,
    tolerance::Float64,
) where {V,F}
    exponents = collect(bounds[1]:bounds[2])
    values = [cache[exponent] for exponent in exponents]
    decision = evaluate_stage(bounds, exponents, values)
    decision isa AdaptiveExponentStageDecision || error(
        "adaptive exponent stage evaluator must return AdaptiveExponentStageDecision",
    )
    materially_unchanged = decision.objective isa Float64 &&
        previous_objective isa Float64 &&
        _relative_objective_change(previous_objective, decision.objective) <= tolerance
    plateau_streak = materially_unchanged ? previous_plateau_streak + 1 : 0
    stage = AdaptiveExponentStageDiagnostics(
        bounds,
        copy(newly_evaluated),
        copy(decision.requested_sides),
        decision.objective,
        decision.unresolved_boundary,
        materially_unchanged,
        plateau_streak,
        decision.value,
    )
    return decision, stage
end

function _expanded_bounds(
    bounds::Tuple{Int,Int},
    requested_sides::Vector{Symbol},
    protocol::AdaptiveExponentProtocol,
)
    lower, upper = bounds
    if :lower in requested_sides
        lower = max(protocol.hard_min, lower - protocol.expansion_step)
    end
    if :upper in requested_sides
        upper = min(protocol.hard_max, upper + protocol.expansion_step)
    end
    return (lower, upper)
end

function _search_result(
    termination::Symbol,
    protocol::AdaptiveExponentProtocol,
    cache::Dict{Int,V},
    stages::Vector{AdaptiveExponentStageDiagnostics{T}},
) where {T,V}
    final_stage = last(stages)
    diagnostics = AdaptiveExponentSearchDiagnostics(
        termination,
        (protocol.initial_min, protocol.initial_max),
        (protocol.hard_min, protocol.hard_max),
        final_stage.bounds,
        final_stage.unresolved_boundary,
        stages,
    )
    return AdaptiveExponentSearchResult(diagnostics, cache, final_stage.value)
end

function search_adaptive_exponent_bounds(
    evaluate_exponent::F,
    evaluate_stage::G;
    protocol::AdaptiveExponentProtocol=AdaptiveExponentProtocol(),
) where {F,G}
    protocol = _validate_exponent_protocol(protocol)
    bounds = (protocol.initial_min, protocol.initial_max)
    cache, newly_evaluated = _initial_exponent_cache(protocol, evaluate_exponent)
    decision, first_stage = _evaluate_exponent_stage(
        cache,
        bounds,
        newly_evaluated,
        evaluate_stage,
        nothing,
        0,
        protocol.plateau_relative_tolerance,
    )
    stages = [first_stage]

    while true
        if isempty(decision.requested_sides)
            termination = decision.unresolved_boundary ? :plateau : :interior
            return _search_result(termination, protocol, cache, stages)
        end
        next_bounds = _expanded_bounds(bounds, decision.requested_sides, protocol)
        next_bounds == bounds && return _search_result(:hard_bound, protocol, cache, stages)
        if last(stages).plateau_streak >= protocol.plateau_patience
            return _search_result(:plateau, protocol, cache, stages)
        end

        newly_evaluated = _populate_exponent_cache!(
            cache,
            next_bounds,
            evaluate_exponent,
        )
        previous_stage = last(stages)
        decision, stage = _evaluate_exponent_stage(
            cache,
            next_bounds,
            newly_evaluated,
            evaluate_stage,
            previous_stage.objective,
            previous_stage.plateau_streak,
            protocol.plateau_relative_tolerance,
        )
        push!(stages, stage)
        bounds = next_bounds
    end
end

end
