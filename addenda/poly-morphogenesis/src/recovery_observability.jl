module RecoveryObservability

using ..GraphRecovery: GraphComponentReference, ComponentRecoveryMetrics

export RECOVERY_READOUT_LEVELS,
    RecoveryReadout,
    RecoveryReadoutCandidate,
    RecoveryReadoutSelection,
    RecoveryAliasGroup,
    ComponentReadoutDiagnostic,
    ComponentObservabilityReport,
    RecoveryReadoutAggregateDiagnostic,
    RecoveryObservabilityReport,
    recovery_readout,
    select_recovery_readout,
    component_observability_report,
    recovery_observability_report,
    observability_boundary_sides

const RECOVERY_READOUT_LEVELS = (
    :domain_count,
    :domain_count_mass,
    :domain_count_mass_centroid,
)

struct RecoveryReadout
    domain_count::Int
    activator_mass::Float64
    centroid_x::Float64
    centroid_y::Float64
end

struct RecoveryReadoutCandidate
    exponent::Int
    readout::RecoveryReadout
end

struct RecoveryReadoutSelection
    level::Symbol
    selection_resolution::Float64
    selected_exponent::Int
    count_error::Int
    sensor_rms::Float64
    score_tied_exponents::Vector{Int}
    resolution_compatible_exponents::Vector{Int}
end

struct RecoveryAliasGroup
    resolution::Float64
    signature::Vector{Int}
    exponents::Vector{Int}
    profile_loss_min::Float64
    profile_loss_max::Float64
    profile_loss_span::Float64
end

struct ComponentReadoutDiagnostic
    level::Symbol
    selection_resolution::Float64
    continuous_readout_dimension::Int
    compression_eligible::Bool
    selected_exponent::Int
    selected_count_error::Int
    selected_sensor_rms::Float64
    score_tied_exponents::Vector{Int}
    resolution_compatible_exponents::Vector{Int}
    score_tied_best_exponent::Int
    score_tied_best_loss::Float64
    target_count_exponents::Vector{Int}
    target_count_equivalence_class_size::Int
    target_count_loss_min::Union{Nothing,Float64}
    target_count_loss_max::Union{Nothing,Float64}
    target_count_loss_span::Union{Nothing,Float64}
    selected_loss::Float64
    worst_case_exponent::Int
    worst_case_loss::Float64
    count_constrained_oracle_exponent::Union{Nothing,Int}
    count_constrained_oracle_loss::Union{Nothing,Float64}
    fixed_loss::Float64
    selected_normalized_regret::Union{Nothing,Float64}
    worst_case_normalized_regret::Union{Nothing,Float64}
    sufficient::Union{Nothing,Bool}
    tie_break_excess_loss::Float64
    readout_excess_loss::Union{Nothing,Float64}
    tie_break_failure::Bool
    readout_mismatch::Union{Nothing,Bool}
    quantized_alias_groups::Vector{RecoveryAliasGroup}
end

struct ComponentObservabilityReport
    component_id::Int
    target::RecoveryReadout
    candidate_count::Int
    diagnostics::Vector{ComponentReadoutDiagnostic}
end

struct RecoveryReadoutAggregateDiagnostic
    level::Symbol
    continuous_readout_dimension::Int
    compression_eligible::Bool
    selected_exponents::Vector{Int}
    worst_case_exponents::Vector{Int}
    count_targets_met::Bool
    fixed_loss::Float64
    selected_loss::Float64
    worst_case_loss::Float64
    count_constrained_oracle_loss::Union{Nothing,Float64}
    selected_normalized_regret::Union{Nothing,Float64}
    worst_case_normalized_regret::Union{Nothing,Float64}
    sufficient::Union{Nothing,Bool}
end

struct RecoveryObservabilityReport
    schema_version::Int
    levels::Vector{Symbol}
    alias_resolutions::Vector{Float64}
    selection_resolution::Float64
    max_selection_regret::Float64
    components::Vector{ComponentObservabilityReport}
    aggregate::Vector{RecoveryReadoutAggregateDiagnostic}
end

function _validate_level(level::Symbol)
    level in RECOVERY_READOUT_LEVELS || error(
        "readout level must be one of $(join(string.(RECOVERY_READOUT_LEVELS), ", "))",
    )
    return level
end

function _continuous_readout_dimension(level::Symbol)
    _validate_level(level)
    level == :domain_count && return 0
    level == :domain_count_mass && return 1
    return 3
end

function _validate_levels(levels::AbstractVector{Symbol})
    isempty(levels) && error("observability report requires at least one readout level")
    length(unique(levels)) == length(levels) || error("readout levels must be unique")
    return [_validate_level(level) for level in levels]
end

function _validate_resolutions(resolutions::AbstractVector{<:Real})
    values = Float64.(resolutions)
    isempty(values) && error("observability report requires at least one alias resolution")
    all(isfinite, values) || error("alias resolutions must be finite")
    all(>(0), values) || error("alias resolutions must be > 0")
    issorted(values) || error("alias resolutions must be sorted")
    length(unique(values)) == length(values) || error("alias resolutions must be unique")
    return values
end

function _validate_readout(readout::RecoveryReadout)
    readout.domain_count >= 0 || error("domain count must be nonnegative")
    isfinite(readout.activator_mass) && readout.activator_mass > 0 ||
        error("activator mass must be finite and > 0")
    isfinite(readout.centroid_x) && 0 <= readout.centroid_x <= 1 ||
        error("centroid_x must be finite and lie in [0, 1]")
    isfinite(readout.centroid_y) && 0 <= readout.centroid_y <= 1 ||
        error("centroid_y must be finite and lie in [0, 1]")
    return readout
end

function _readout(
    domain_count::Int,
    activator::AbstractVector{<:Real},
    normalized_x::AbstractVector{<:Real},
    normalized_y::AbstractVector{<:Real},
)
    length(activator) == length(normalized_x) == length(normalized_y) ||
        error("activator and normalized coordinate vectors must align")
    isempty(activator) && error("recovery readout requires at least one node")
    values = Float64.(activator)
    x = Float64.(normalized_x)
    y = Float64.(normalized_y)
    all(isfinite, values) || error("activator values must be finite")
    all(>=(0), values) || error("activator values must be nonnegative")
    all(value -> isfinite(value) && 0 <= value <= 1, x) ||
        error("normalized x coordinates must be finite and lie in [0, 1]")
    all(value -> isfinite(value) && 0 <= value <= 1, y) ||
        error("normalized y coordinates must be finite and lie in [0, 1]")
    mass = sum(values)
    mass > 0 || error("activator mass must be > 0")
    return RecoveryReadout(
        domain_count,
        mass,
        sum(values .* x) / mass,
        sum(values .* y) / mass,
    )
end

function recovery_readout(
    reference::GraphComponentReference,
    normalized_x::AbstractVector{<:Real},
    normalized_y::AbstractVector{<:Real},
)
    length(reference.nodes) == length(reference.reference_A) ||
        error("reference nodes and activator values must align")
    return _readout(
        reference.target_domain_count,
        reference.reference_A,
        normalized_x,
        normalized_y,
    )
end

function recovery_readout(
    metrics::ComponentRecoveryMetrics,
    normalized_x::AbstractVector{<:Real},
    normalized_y::AbstractVector{<:Real},
)
    length(metrics.nodes) == length(metrics.observed_A) ||
        error("metric nodes and activator values must align")
    return _readout(
        metrics.observed_domain_count,
        metrics.observed_A,
        normalized_x,
        normalized_y,
    )
end

function _sensor_errors(
    target::RecoveryReadout,
    observed::RecoveryReadout,
    level::Symbol,
)
    _validate_level(level)
    _validate_readout(target)
    _validate_readout(observed)
    level == :domain_count && return Float64[]
    mass_error = log(observed.activator_mass / target.activator_mass)
    level == :domain_count_mass && return [mass_error]
    return [
        mass_error,
        observed.centroid_x - target.centroid_x,
        observed.centroid_y - target.centroid_y,
    ]
end

function _validate_candidates(candidates::AbstractVector{RecoveryReadoutCandidate})
    isempty(candidates) && error("readout selection requires at least one candidate")
    exponents = [candidate.exponent for candidate in candidates]
    length(unique(exponents)) == length(exponents) || error("candidate exponents must be unique")
    all(candidate -> _validate_readout(candidate.readout) isa RecoveryReadout, candidates)
    return sort(collect(candidates); by=candidate -> candidate.exponent)
end

function select_recovery_readout(
    target::RecoveryReadout,
    candidates::AbstractVector{RecoveryReadoutCandidate},
    level::Symbol;
    selection_resolution::Real,
)
    _validate_level(level)
    _validate_readout(target)
    resolution = Float64(selection_resolution)
    isfinite(resolution) && resolution > 0 ||
        error("selection_resolution must be finite and > 0")
    canonical = _validate_candidates(candidates)
    signatures = [
        _quantized_signature(target, candidate, level, resolution)
        for candidate in canonical
    ]
    sensor_scores = [
        begin
            quantized_errors = signature[2:end]
            isempty(quantized_errors) ? 0.0 :
            resolution * sqrt(sum(abs2, quantized_errors) / length(quantized_errors))
        end for signature in signatures
    ]
    keys = [
        (
            abs(candidate.readout.domain_count - target.domain_count),
            sensor_scores[idx],
            abs(candidate.exponent),
            candidate.exponent,
        ) for (idx, candidate) in enumerate(canonical)
    ]
    selected_index = argmin(keys)
    selected = canonical[selected_index]
    selected_key = keys[selected_index]
    score_tied = sort([
        candidate.exponent for (candidate, key) in zip(canonical, keys)
        if key[1] == selected_key[1] && key[2] == selected_key[2]
    ])
    selected_signature = signatures[selected_index]
    resolution_compatible = sort([
        candidate.exponent for (candidate, signature) in zip(canonical, signatures)
        if signature == selected_signature
    ])
    return RecoveryReadoutSelection(
        level,
        resolution,
        selected.exponent,
        selected_key[1],
        selected_key[2],
        score_tied,
        resolution_compatible,
    )
end

function _metric_sort_key(metrics::ComponentRecoveryMetrics)
    return (
        metrics.profile_squared_error,
        abs(metrics.count_error),
        abs(metrics.exponent),
        metrics.exponent,
    )
end

function _minimum_metric(rows::AbstractVector{ComponentRecoveryMetrics})
    isempty(rows) && error("cannot select a metric from an empty collection")
    return rows[argmin(_metric_sort_key.(rows))]
end

function _maximum_loss_metric(rows::AbstractVector{ComponentRecoveryMetrics})
    isempty(rows) && error("cannot select a metric from an empty collection")
    keys = [(-row.profile_squared_error, abs(row.exponent), row.exponent) for row in rows]
    return rows[argmin(keys)]
end

function _loss_tolerance(losses::Real...)
    return 100 * eps(Float64) * max(1.0, Float64.(losses)...)
end

function _normalized_selection_regret(
    fixed_loss::Float64,
    candidate_loss::Float64,
    oracle_loss::Float64,
)
    tolerance = _loss_tolerance(fixed_loss, candidate_loss, oracle_loss)
    candidate_loss + tolerance >= oracle_loss || error(
        "readout-compatible loss cannot beat the count-constrained oracle",
    )
    available = fixed_loss - oracle_loss
    available > tolerance || return nothing
    return max(0.0, candidate_loss - oracle_loss) / available
end

function _quantized_signature(
    target::RecoveryReadout,
    candidate::RecoveryReadoutCandidate,
    level::Symbol,
    resolution::Float64,
)
    errors = _sensor_errors(target, candidate.readout, level)
    return vcat(
        candidate.readout.domain_count,
        [round(Int, error / resolution) for error in errors],
    )
end

function _alias_groups(
    target::RecoveryReadout,
    candidates::Vector{RecoveryReadoutCandidate},
    metrics_by_exponent::Dict{Int,ComponentRecoveryMetrics},
    level::Symbol,
    resolutions::Vector{Float64},
)
    min_count_error = minimum(
        abs(candidate.readout.domain_count - target.domain_count) for candidate in candidates
    )
    primary = [
        candidate for candidate in candidates
        if abs(candidate.readout.domain_count - target.domain_count) == min_count_error
    ]
    groups = RecoveryAliasGroup[]
    for resolution in resolutions
        by_signature = Dict{Tuple,Vector{Int}}()
        for candidate in primary
            signature = Tuple(_quantized_signature(target, candidate, level, resolution))
            push!(get!(by_signature, signature, Int[]), candidate.exponent)
        end
        for signature in sort(collect(keys(by_signature)))
            exponents = sort(by_signature[signature])
            length(exponents) >= 2 || continue
            losses = [metrics_by_exponent[exponent].profile_relative_rmse for exponent in exponents]
            low = minimum(losses)
            high = maximum(losses)
            push!(
                groups,
                RecoveryAliasGroup(
                    resolution,
                    collect(signature),
                    exponents,
                    low,
                    high,
                    high - low,
                ),
            )
        end
    end
    return groups
end

function _component_diagnostic(
    target::RecoveryReadout,
    candidates::Vector{RecoveryReadoutCandidate},
    rows::Vector{ComponentRecoveryMetrics},
    level::Symbol,
    resolutions::Vector{Float64},
    selection_resolution::Float64,
    max_selection_regret::Float64,
)
    selection = select_recovery_readout(
        target,
        candidates,
        level;
        selection_resolution,
    )
    metrics_by_exponent = Dict(row.exponent => row for row in rows)
    selected = metrics_by_exponent[selection.selected_exponent]
    compatible_rows = [
        metrics_by_exponent[exponent]
        for exponent in selection.resolution_compatible_exponents
    ]
    worst_case = _maximum_loss_metric(compatible_rows)
    continuous_dimension = _continuous_readout_dimension(level)
    compression_eligible = continuous_dimension < length(first(rows).nodes)
    fixed_rows = [row for row in rows if iszero(row.exponent)]
    length(fixed_rows) == 1 || error("component surface must contain exactly one exponent-0 row")
    fixed = only(fixed_rows)
    target_rows = [row for row in rows if row.observed_domain_count == target.domain_count]
    target_exponents = sort([row.exponent for row in target_rows])
    target_losses = [row.profile_relative_rmse for row in target_rows]
    count_oracle = isempty(target_rows) ? nothing : _minimum_metric(target_rows)
    score_tied_rows = [metrics_by_exponent[exponent] for exponent in selection.score_tied_exponents]
    score_tied_best = _minimum_metric(score_tied_rows)
    tie_tolerance = _loss_tolerance(
        selected.profile_relative_rmse,
        score_tied_best.profile_relative_rmse,
    )
    tie_break_excess = max(
        0.0,
        selected.profile_relative_rmse - score_tied_best.profile_relative_rmse,
    )
    tie_break_failure = tie_break_excess > tie_tolerance
    readout_excess = if isnothing(count_oracle)
        nothing
    else
        max(
            0.0,
            score_tied_best.profile_relative_rmse - count_oracle.profile_relative_rmse,
        )
    end
    readout_mismatch = if isnothing(readout_excess)
        nothing
    else
        readout_excess > _loss_tolerance(
            score_tied_best.profile_relative_rmse,
            count_oracle.profile_relative_rmse,
        )
    end
    selected_normalized_regret = if isnothing(count_oracle)
        nothing
    else
        _normalized_selection_regret(
            fixed.profile_relative_rmse,
            selected.profile_relative_rmse,
            count_oracle.profile_relative_rmse,
        )
    end
    worst_case_normalized_regret = if isnothing(count_oracle)
        nothing
    else
        _normalized_selection_regret(
            fixed.profile_relative_rmse,
            worst_case.profile_relative_rmse,
            count_oracle.profile_relative_rmse,
        )
    end
    sufficient = if isnothing(worst_case_normalized_regret)
        nothing
    else
        compression_eligible &&
            selected.observed_domain_count == target.domain_count &&
            worst_case_normalized_regret <= max_selection_regret
    end
    return ComponentReadoutDiagnostic(
        level,
        selection_resolution,
        continuous_dimension,
        compression_eligible,
        selected.exponent,
        selection.count_error,
        selection.sensor_rms,
        copy(selection.score_tied_exponents),
        copy(selection.resolution_compatible_exponents),
        score_tied_best.exponent,
        score_tied_best.profile_relative_rmse,
        target_exponents,
        length(target_rows),
        isempty(target_losses) ? nothing : minimum(target_losses),
        isempty(target_losses) ? nothing : maximum(target_losses),
        isempty(target_losses) ? nothing : maximum(target_losses) - minimum(target_losses),
        selected.profile_relative_rmse,
        worst_case.exponent,
        worst_case.profile_relative_rmse,
        isnothing(count_oracle) ? nothing : count_oracle.exponent,
        isnothing(count_oracle) ? nothing : count_oracle.profile_relative_rmse,
        fixed.profile_relative_rmse,
        selected_normalized_regret,
        worst_case_normalized_regret,
        sufficient,
        tie_break_excess,
        readout_excess,
        tie_break_failure,
        readout_mismatch,
        _alias_groups(
            target,
            candidates,
            metrics_by_exponent,
            level,
            resolutions,
        ),
    )
end

function component_observability_report(
    reference::GraphComponentReference,
    rows::AbstractVector{ComponentRecoveryMetrics},
    normalized_x::AbstractVector{<:Real},
    normalized_y::AbstractVector{<:Real};
    levels::AbstractVector{Symbol}=collect(RECOVERY_READOUT_LEVELS),
    alias_resolutions::AbstractVector{<:Real},
    max_selection_regret::Float64=0.10,
)
    canonical_levels = _validate_levels(levels)
    resolutions = _validate_resolutions(alias_resolutions)
    selection_resolution = maximum(resolutions)
    0 <= max_selection_regret <= 1 || error("max_selection_regret must lie in [0, 1]")
    isempty(rows) && error("component observability requires at least one surface row")
    canonical_rows = sort(collect(rows); by=row -> row.exponent)
    all(row -> row.component_id == reference.component_id, canonical_rows) ||
        error("surface rows must match the reference component id")
    all(row -> row.nodes == reference.nodes, canonical_rows) ||
        error("surface row nodes must match the reference nodes")
    all(row -> row.target_domain_count == reference.target_domain_count, canonical_rows) ||
        error("surface row count targets must match the reference target")
    all(
        row -> row.count_error == row.observed_domain_count - reference.target_domain_count,
        canonical_rows,
    ) || error("surface row count errors must match observed minus target count")
    all(
        row -> isfinite(row.reference_energy) && row.reference_energy > 0,
        canonical_rows,
    ) || error("surface reference energies must be finite and > 0")
    all(row -> row.reference_energy == first(canonical_rows).reference_energy, canonical_rows) ||
        error("surface reference energy must be constant across exponents")
    all(
        row -> isfinite(row.profile_squared_error) && row.profile_squared_error >= 0 &&
            isfinite(row.profile_relative_rmse) && row.profile_relative_rmse >= 0,
        canonical_rows,
    ) || error("surface profile losses must be finite and nonnegative")
    exponents = [row.exponent for row in canonical_rows]
    length(unique(exponents)) == length(exponents) || error("surface exponents must be unique")
    target = recovery_readout(reference, normalized_x, normalized_y)
    candidates = [
        RecoveryReadoutCandidate(
            row.exponent,
            recovery_readout(row, normalized_x, normalized_y),
        ) for row in canonical_rows
    ]
    diagnostics = [
        _component_diagnostic(
            target,
            candidates,
            canonical_rows,
            level,
            resolutions,
            selection_resolution,
            max_selection_regret,
        ) for level in canonical_levels
    ]
    return ComponentObservabilityReport(
        reference.component_id,
        target,
        length(canonical_rows),
        diagnostics,
    )
end

function _aggregate_profile_loss(rows::AbstractVector{ComponentRecoveryMetrics})
    isempty(rows) && error("aggregate profile loss requires at least one component")
    total_energy = sum(row.reference_energy for row in rows)
    total_energy > 0 || error("aggregate reference energy must be > 0")
    return sqrt(sum(row.profile_squared_error for row in rows) / total_energy)
end

function _aggregate_diagnostic(
    level::Symbol,
    component_reports::Vector{ComponentObservabilityReport},
    rows_by_component::Vector{Vector{ComponentRecoveryMetrics}},
    max_selection_regret::Float64,
)
    diagnostic_by_component = [
        only([diagnostic for diagnostic in report.diagnostics if diagnostic.level == level])
        for report in component_reports
    ]
    selected_rows = ComponentRecoveryMetrics[]
    worst_case_rows = ComponentRecoveryMetrics[]
    fixed_rows = ComponentRecoveryMetrics[]
    oracle_rows = ComponentRecoveryMetrics[]
    all_oracles_available = true
    for (rows, diagnostic) in zip(rows_by_component, diagnostic_by_component)
        push!(selected_rows, only([row for row in rows if row.exponent == diagnostic.selected_exponent]))
        push!(
            worst_case_rows,
            only([row for row in rows if row.exponent == diagnostic.worst_case_exponent]),
        )
        push!(fixed_rows, only([row for row in rows if iszero(row.exponent)]))
        if isnothing(diagnostic.count_constrained_oracle_exponent)
            all_oracles_available = false
        else
            push!(
                oracle_rows,
                only([
                    row for row in rows
                    if row.exponent == diagnostic.count_constrained_oracle_exponent
                ]),
            )
        end
    end
    fixed_loss = _aggregate_profile_loss(fixed_rows)
    selected_loss = _aggregate_profile_loss(selected_rows)
    worst_case_loss = _aggregate_profile_loss(worst_case_rows)
    oracle_loss = all_oracles_available ? _aggregate_profile_loss(oracle_rows) : nothing
    selected_normalized_regret = if isnothing(oracle_loss)
        nothing
    else
        _normalized_selection_regret(fixed_loss, selected_loss, oracle_loss)
    end
    worst_case_normalized_regret = if isnothing(oracle_loss)
        nothing
    else
        _normalized_selection_regret(fixed_loss, worst_case_loss, oracle_loss)
    end
    targets_met = all(
        diagnostic.selected_count_error == 0 for diagnostic in diagnostic_by_component
    )
    continuous_dimension = _continuous_readout_dimension(level)
    compression_eligible = all(
        diagnostic.compression_eligible for diagnostic in diagnostic_by_component
    )
    sufficient = if isnothing(worst_case_normalized_regret)
        nothing
    else
        compression_eligible && targets_met &&
            worst_case_normalized_regret <= max_selection_regret
    end
    return RecoveryReadoutAggregateDiagnostic(
        level,
        continuous_dimension,
        compression_eligible,
        [row.exponent for row in selected_rows],
        [row.exponent for row in worst_case_rows],
        targets_met,
        fixed_loss,
        selected_loss,
        worst_case_loss,
        oracle_loss,
        selected_normalized_regret,
        worst_case_normalized_regret,
        sufficient,
    )
end

function recovery_observability_report(
    references::AbstractVector{GraphComponentReference},
    component_rows::AbstractVector{<:AbstractVector{ComponentRecoveryMetrics}},
    normalized_x::AbstractVector{<:AbstractVector{<:Real}},
    normalized_y::AbstractVector{<:AbstractVector{<:Real}};
    levels::AbstractVector{Symbol}=collect(RECOVERY_READOUT_LEVELS),
    alias_resolutions::AbstractVector{<:Real},
    max_selection_regret::Float64=0.10,
)
    component_count = length(references)
    component_count >= 1 || error("observability report requires at least one component")
    length(component_rows) == component_count || error("component rows must align with references")
    length(normalized_x) == component_count || error("normalized x coordinates must align with references")
    length(normalized_y) == component_count || error("normalized y coordinates must align with references")
    canonical_levels = _validate_levels(levels)
    resolutions = _validate_resolutions(alias_resolutions)
    selection_resolution = maximum(resolutions)
    rows = [sort(collect(entries); by=row -> row.exponent) for entries in component_rows]
    reports = [
        component_observability_report(
            references[idx],
            rows[idx],
            normalized_x[idx],
            normalized_y[idx];
            levels=canonical_levels,
            alias_resolutions=resolutions,
            max_selection_regret=max_selection_regret,
        ) for idx in eachindex(references)
    ]
    aggregate = [
        _aggregate_diagnostic(level, reports, rows, max_selection_regret)
        for level in canonical_levels
    ]
    return RecoveryObservabilityReport(
        1,
        canonical_levels,
        resolutions,
        selection_resolution,
        max_selection_regret,
        reports,
        aggregate,
    )
end

function observability_boundary_sides(
    report::RecoveryObservabilityReport,
    bounds::Tuple{Int,Int},
)
    lower, upper = bounds
    lower <= upper || error("observability bounds must be ordered")
    requested = Symbol[]
    for component in report.components
        for diagnostic in component.diagnostics
            exponents = unique(vcat(
                diagnostic.selected_exponent,
                diagnostic.score_tied_exponents,
                diagnostic.target_count_exponents,
                diagnostic.resolution_compatible_exponents,
            ))
            all(lower <= exponent <= upper for exponent in exponents) || error(
                "observability diagnostic exponents must lie within the supplied bounds",
            )
            lower in exponents && :lower ∉ requested && push!(requested, :lower)
            upper in exponents && :upper ∉ requested && push!(requested, :upper)
        end
    end
    return [side for side in (:lower, :upper) if side in requested]
end

end
