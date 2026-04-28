module Wiring

using Random: AbstractRNG, MersenneTwister, shuffle

using ..RD: RDParameters,
    RDChainConfig,
    make_rd_state,
    preseed_lxh!,
    settle_rd_composed!,
    peak_count,
    shape_string

export cut_connectivity_loss,
    wiring_intervention_order,
    wiring_cut_sweep_demo,
    wiring_fragment_family_demo,
    wiring_severity_phase_scan_demo,
    wiring_intervention_k_demo,
    wiring_bistability_demo

const REFERENCE_ONE_HEAD_D_A_100 = 9.849732675807608

struct MorphologySnapshot
    cuts::Vector{Int}
    shape::String
    peak_count::Int
    A::Vector{Float64}
    I::Vector{Float64}
end

struct SegmentSnapshot
    interval::Tuple{Int,Int}
    segment_length::Int
    shape::String
    peak_count::Int
    A::Vector{Float64}
    I::Vector{Float64}
end

Base.@kwdef mutable struct CutEvaluation
    cuts::Vector{Int}
    cut_count::Int
    segment_lengths::Vector{Int}
    n_segments::Int
    cut_connectivity_loss::Int
    shape::String
    peak_count::Int
    A::Vector{Float64}
    I::Vector{Float64}
    segments::Vector{SegmentSnapshot}
    peak_delta::Int
    shape_changed::Bool
    profile_l1_mean::Float64
    shape_distance::Int
    peak_delta_abs::Int
    severity_score::Float64
    cut::Union{Nothing,Int}
    left_cells::Union{Nothing,Int}
    right_cells::Union{Nothing,Int}
end

struct SeverityCalibration
    max_peak_delta_abs::Int
    max_profile_l1_mean::Float64
    max_shape_distance::Int
end

struct ValidationCase
    cuts::Vector{Int}
    profile_linf_error::Float64
    peak_count_error::Int
    shape_match::Bool
end

struct FactorizationValidation
    cases::Vector{ValidationCase}
    max_profile_linf_error::Float64
    max_peak_count_error::Int
end

struct ValidationScope
    mode::String
    validated_cutset_count::Int
    all_candidates_validated::Bool
end

struct CutSweepResult
    n_cells::Int
    seed::Int
    D_a::Float64
    cut_count::Int
    candidate_count::Int
    connected::MorphologySnapshot
    cuts::Vector{CutEvaluation}
    ranking_connectivity::Vector{CutEvaluation}
    ranking_decomposition::Vector{CutEvaluation}
    severity_calibration::SeverityCalibration
    validation_scope::ValidationScope
    validation::Union{Nothing,FactorizationValidation}
end

struct FragmentPlacement
    cuts::Vector{Int}
    isolated_interval::Tuple{Int,Int}
    isolated_length::Int
end

struct FragmentFamilyResult
    sweep::CutSweepResult
    family::String
    fragment_size::Int
    left_cuts::Vector{Int}
    candidate_cutsets::Vector{Vector{Int}}
    placements::Vector{FragmentPlacement}
end

struct SeverityScanSlice
    D_a::Float64
    candidate_count::Int
    top_k::Int
    top_k_cutsets::Vector{Vector{Int}}
    top_k_margin::Union{Nothing,Float64}
    connected::MorphologySnapshot
    best_connectivity::CutEvaluation
    best_decomposition::CutEvaluation
    validation_scope::ValidationScope
end

struct RegimeChange
    from_D_a::Float64
    to_D_a::Float64
    from_top_k_cutsets::Vector{Vector{Int}}
    to_top_k_cutsets::Vector{Vector{Int}}
end

struct BestDecompositionPoint
    D_a::Float64
    cuts::Vector{Int}
    severity_score::Float64
    peak_count::Int
    shape::String
end

struct SeverityPhaseScanResult
    n_cells::Int
    seed::Int
    cut_count::Int
    top_k::Int
    D_a_values::Vector{Float64}
    candidate_family::String
    candidate_cutsets::Union{Nothing,Vector{Vector{Int}}}
    scan::Vector{SeverityScanSlice}
    best_decomposition_trace::Vector{BestDecompositionPoint}
    regime_changes::Vector{RegimeChange}
    notes::Vector{String}
end

struct PairedTrialSummary
    lower_bound_censored_at_H::Float64
    conditional_on_both_solved::Union{Nothing,Float64}
    agent_mean_censored::Float64
    blind_mean_censored::Float64
    agent_mean_both_solved::Union{Nothing,Float64}
    blind_mean_both_solved::Union{Nothing,Float64}
    agent_solve_rate::Float64
    blind_solve_rate::Float64
    both_solved_rate::Float64
    trials::Int
    agent_solved::Int
    blind_solved::Int
    both_solved::Int
    notes::Vector{String}
end

struct InterventionTrial
    seed::Int
    n_candidates::Int
    n_successes::Int
    target_peak_count::Int
    target_shape::Union{Nothing,String}
    target_top_k::Union{Nothing,Int}
    cost_connectivity::Float64
    cost_decomposition::Float64
    cost_blind::Float64
    first_success_connectivity::Vector{Int}
    first_success_decomposition::Vector{Int}
    first_success_blind::Vector{Int}
end

struct InterventionKResult
    schema_version::Int
    reference_addendum::String
    cut_count::Int
    trials::Int
    reference_sweep::CutSweepResult
    validation::Union{Nothing,FactorizationValidation}
    connectivity_loss_vs_blind::PairedTrialSummary
    decomposition_severity_vs_blind::PairedTrialSummary
    trial_results::Vector{InterventionTrial}
    target_peak_count::Int
    target_shape::Union{Nothing,String}
    target_top_k::Union{Nothing,Int}
    notes::Vector{String}
end

struct BistabilityResult
    n_cells::Int
    seed::Int
    cut::Int
    D_a::Float64
    connected::MorphologySnapshot
    severed::MorphologySnapshot
end

_wiring_fieldnames(::Type{T}) where {T} = fieldnames(T)

for T in (
    MorphologySnapshot,
    SegmentSnapshot,
    SeverityCalibration,
    ValidationCase,
    FactorizationValidation,
    ValidationScope,
    CutSweepResult,
    SeverityScanSlice,
    RegimeChange,
    BestDecompositionPoint,
    SeverityPhaseScanResult,
    FragmentPlacement,
    PairedTrialSummary,
    InterventionTrial,
    BistabilityResult,
)
    @eval begin
        Base.haskey(value::$T, key::Symbol) = key in _wiring_fieldnames($T)
        function Base.getindex(value::$T, key::Symbol)
            haskey(value, key) || error("$(string($T)) has no key $(key)")
            return getfield(value, key)
        end
    end
end

function Base.haskey(value::CutEvaluation, key::Symbol)
    key in _wiring_fieldnames(CutEvaluation) || return false
    if key in (:cut, :left_cells, :right_cells)
        return !isnothing(getfield(value, key))
    end
    return true
end

function Base.getindex(value::CutEvaluation, key::Symbol)
    haskey(value, key) || error("CutEvaluation has no key $(key)")
    return getfield(value, key)
end

function Base.haskey(value::FragmentFamilyResult, key::Symbol)
    key in (:family, :fragment_size, :left_cuts, :candidate_cutsets, :placements) && return true
    return haskey(value.sweep, key)
end

function Base.getindex(value::FragmentFamilyResult, key::Symbol)
    if key === :family
        return value.family
    elseif key === :fragment_size
        return value.fragment_size
    elseif key === :left_cuts
        return value.left_cuts
    elseif key === :candidate_cutsets
        return value.candidate_cutsets
    elseif key === :placements
        return value.placements
    end
    return value.sweep[key]
end

function Base.haskey(value::InterventionKResult, key::Symbol)
    key in (
        :schema_version,
        :reference_addendum,
        :problem_space,
        :policies,
        :connected,
        :severity_calibration,
        :validation_scope,
        :ranking_connectivity,
        :ranking_decomposition,
        :validation,
        :comparison,
        :trials,
        :derived,
        :notes,
    )
end

function Base.getindex(value::InterventionKResult, key::Symbol)
    if key === :schema_version
        return value.schema_version
    elseif key === :reference_addendum
        return value.reference_addendum
    elseif key === :problem_space
        return _intervention_problem_space(value)
    elseif key === :policies
        return _intervention_policies(value)
    elseif key === :connected
        return value.reference_sweep.connected
    elseif key === :severity_calibration
        return value.reference_sweep.severity_calibration
    elseif key === :validation_scope
        return value.reference_sweep.validation_scope
    elseif key === :ranking_connectivity
        return value.reference_sweep.ranking_connectivity
    elseif key === :ranking_decomposition
        return value.reference_sweep.ranking_decomposition
    elseif key === :validation
        return value.validation
    elseif key === :comparison
        return _intervention_comparison(value)
    elseif key === :trials
        return value.trial_results
    elseif key === :derived
        return _intervention_derived(value)
    elseif key === :notes
        return value.notes
    end
    error("InterventionKResult has no key $(key)")
end

function _intervention_problem_space(result::InterventionKResult)
    target_peak_count = result.target_peak_count
    return Dict(
        :S => "$(result.cut_count)-cut interventions in a $(result.reference_sweep.n_cells)-cell RD chain",
        :O => ["test_candidate_intervention(cuts)"],
        :C => [
            "fixed cut_count == $(result.cut_count)",
            "one intervention tested per evaluation",
            "same seed-indexed initial state distribution for all policies",
        ],
        :E =>
            !isnothing(result.target_top_k) ?
            "find one of the top-$(result.target_top_k) most severe interventions under decomposition-ranked phenotype shift" :
            isnothing(result.target_shape) ?
            "find an intervention whose settled attractor has peak_count == $(target_peak_count)" :
            "find an intervention whose settled attractor has peak_count == $(target_peak_count) and shape == $(result.target_shape)",
        :H => result.reference_sweep.candidate_count,
        :H_unit => "cut_test",
        :S_init => "connected attractor search over admissible $(result.cut_count)-cut interventions",
        :S_goal =>
            !isnothing(result.target_top_k) ?
            "any intervention in the top-$(result.target_top_k) decomposition-severity set" :
            isnothing(result.target_shape) ?
            "any intervention with target peak_count" :
            "any intervention with target peak_count and target shape",
    )
end

function _intervention_policies(result::InterventionKResult)
    return Dict(
        :agent_connectivity => "descending_cutset_connectivity_loss",
        :agent_decomposition => "descending_decomposition_severity",
        :blind => "uniform_random_cut_order",
        :cut_count => result.cut_count,
        :trials => result.trials,
    )
end

function _intervention_comparison(result::InterventionKResult)
    return Dict(
        :connectivity_loss_vs_blind => result.connectivity_loss_vs_blind,
        :decomposition_severity_vs_blind => result.decomposition_severity_vs_blind,
    )
end

function _intervention_derived(result::InterventionKResult)
    return Dict(
        :target_peak_count => result.target_peak_count,
        :target_shape => result.target_shape,
        :target_top_k => result.target_top_k,
        :candidate_count => result.reference_sweep.candidate_count,
    )
end

function _snapshot_from_state(state::Vector{Float64})
    n = length(state) ÷ 2
    A = collect(@view state[1:n])
    I = collect(@view state[n + 1:end])
    return MorphologySnapshot(Int[], shape_string(A), peak_count(A), A, I)
end

function _prepared_rd_state(config::RDChainConfig; rng_seed::Int=config.seed)
    state = make_rd_state(config; rng_seed=rng_seed)
    preseed_lxh!(state)
    return state
end

function _settled_pattern_snapshot(
    state::Vector{Float64},
    params::RDParameters,
    config::RDChainConfig;
    cuts::Vector{Int}=config.cuts,
    steady_stop::Bool=true,
)
    local_config = RDChainConfig(
        n_cells=config.n_cells,
        field_length=config.field_length,
        tspan=config.tspan,
        seed=config.seed,
        steady_tol=config.steady_tol,
        cuts=sort(unique(cuts)),
    )
    working = copy(state)
    settle_rd_composed!(working, params, local_config; steady_stop=steady_stop)
    snapshot = _snapshot_from_state(working)
    return MorphologySnapshot(collect(local_config.cuts), snapshot.shape, snapshot.peak_count, snapshot.A, snapshot.I)
end

function _settled_pattern_snapshot(; n_cells::Int, seed::Int, D_a::Float64, cuts::Vector{Int}, steady_stop::Bool=true)
    config = RDChainConfig(n_cells=n_cells, seed=seed, cuts=cuts)
    params = RDParameters(D_a=D_a, D_i=30 * D_a)
    state = _prepared_rd_state(config; rng_seed=seed)
    return _settled_pattern_snapshot(state, params, config; cuts=cuts, steady_stop=steady_stop)
end

function _cutset_key(cuts::Vector{Int})
    return Tuple(sort(unique(cuts)))
end

function _segment_ranges(n_cells::Int, cuts::Vector{Int})
    ranges = UnitRange{Int}[]
    start_idx = 1
    for cut in sort(unique(cuts))
        1 <= cut < n_cells || error("each cut must satisfy 1 <= cut < n_cells")
        push!(ranges, start_idx:cut)
        start_idx = cut + 1
    end
    push!(ranges, start_idx:n_cells)
    return ranges
end

function _segment_lengths(n_cells::Int, cuts::Vector{Int})
    return [length(range) for range in _segment_ranges(n_cells, cuts)]
end

function cutset_connectivity_loss(n_cells::Int, cuts::Vector{Int})
    n_cells >= 2 || error("n_cells must be >= 2")
    total_pairs = n_cells * (n_cells - 1) ÷ 2
    within_pairs = sum(length(range) * (length(range) - 1) ÷ 2 for range in _segment_ranges(n_cells, cuts))
    return total_pairs - within_pairs
end

function cut_connectivity_loss(n_cells::Int, cut::Int)
    n_cells >= 2 || error("n_cells must be >= 2")
    1 <= cut < n_cells || error("cut must satisfy 1 <= cut < n_cells")
    return cutset_connectivity_loss(n_cells, [cut])
end

function wiring_intervention_order(n_cells::Int)
    cuts = collect(1:(n_cells - 1))
    sort!(
        cuts;
        by=cut -> (-cut_connectivity_loss(n_cells, cut), abs(n_cells - 2 * cut), cut),
    )
    return cuts
end

function _mean_value(values::Vector{Float64})
    isempty(values) && error("cannot take mean over empty values")
    return sum(values) / length(values)
end

function _levenshtein_distance(left::AbstractString, right::AbstractString)
    left_chars = collect(left)
    right_chars = collect(right)
    rows = length(left_chars) + 1
    cols = length(right_chars) + 1
    dist = Matrix{Int}(undef, rows, cols)
    for i in 1:rows
        dist[i, 1] = i - 1
    end
    for j in 1:cols
        dist[1, j] = j - 1
    end
    for i in 2:rows
        for j in 2:cols
            substitution = left_chars[i - 1] == right_chars[j - 1] ? 0 : 1
            dist[i, j] = min(
                dist[i - 1, j] + 1,
                dist[i, j - 1] + 1,
                dist[i - 1, j - 1] + substitution,
            )
        end
    end
    return dist[end, end]
end

function _profile_l1_mean(left::Vector{Float64}, right::Vector{Float64})
    length(left) == length(right) || error("profiles must have the same length")
    return _mean_value(abs.(left .- right))
end

function _segment_balance(lengths::Vector{Int})
    isempty(lengths) && error("segment lengths must be non-empty")
    return maximum(lengths) - minimum(lengths)
end

function _reflection_invariant_partition_key(lengths::Vector{Int})
    isempty(lengths) && error("segment lengths must be non-empty")
    forward = join(string.(lengths), ",")
    backward = join(string.(reverse(lengths)), ",")
    return min(forward, backward)
end

Base.@kwdef struct IntervalBlueprint
    state::Vector{Float64}
    config::RDChainConfig
end

Base.@kwdef struct CutSweepBlueprint
    config::RDChainConfig
    cutsets::Vector{Vector{Int}}
    initial_state::Vector{Float64}
    intervals::Dict{Tuple{Int,Int},IntervalBlueprint}
end

Base.@kwdef mutable struct CutSweepContext
    blueprint::CutSweepBlueprint
    params::RDParameters
    connected::MorphologySnapshot
    interval_cache::Dict{Tuple{Int,Int},SegmentSnapshot} = Dict{Tuple{Int,Int},SegmentSnapshot}()
end

function _segment_initial_state(initial_state::Vector{Float64}, n_cells::Int, range::UnitRange{Int})
    left = collect(@view initial_state[range])
    right = collect(@view initial_state[(n_cells + first(range)):(n_cells + last(range))])
    return vcat(left, right)
end

function _segment_config(config::RDChainConfig, n_cells::Int, seed::Int, range::UnitRange{Int})
    seg_length = length(range)
    return RDChainConfig(
        n_cells=seg_length,
        field_length=config.field_length * seg_length / n_cells,
        tspan=config.tspan,
        seed=seed,
        steady_tol=config.steady_tol,
        cuts=Int[],
    )
end

function _resolve_cutsets(n_cells::Int, cut_count::Int, candidate_cutsets::Union{Nothing,Vector{Vector{Int}}})
    raw_cutsets = isnothing(candidate_cutsets) ? _candidate_cutsets(n_cells, cut_count) : candidate_cutsets
    return _normalize_cutsets(n_cells, cut_count, raw_cutsets; label="candidate_cutsets")
end

function _interval_keys(n_cells::Int, cutsets::Vector{Vector{Int}})
    keys = Set{Tuple{Int,Int}}()
    for cuts in cutsets
        for range in _segment_ranges(n_cells, cuts)
            push!(keys, (first(range), last(range)))
        end
    end
    return sort(collect(keys); by=key -> (key[1], key[2]))
end

function _build_cut_sweep_blueprint(;
    n_cells::Int,
    seed::Int,
    cut_count::Int,
    candidate_cutsets::Union{Nothing,Vector{Vector{Int}}}=nothing,
    field_length::Float64=40.0,
    tspan::Tuple{Float64,Float64}=(0.0, 300.0),
    steady_tol::Float64=1.0e-5,
)
    config = RDChainConfig(
        n_cells=n_cells,
        field_length=field_length,
        tspan=tspan,
        seed=seed,
        steady_tol=steady_tol,
        cuts=Int[],
    )
    initial_state = _prepared_rd_state(config; rng_seed=seed)
    cutsets = _resolve_cutsets(n_cells, cut_count, candidate_cutsets)
    intervals = Dict{Tuple{Int,Int},IntervalBlueprint}()
    for key in _interval_keys(n_cells, cutsets)
        range = key[1]:key[2]
        intervals[key] = IntervalBlueprint(
            state=_segment_initial_state(initial_state, n_cells, range),
            config=_segment_config(config, n_cells, seed, range),
        )
    end
    return CutSweepBlueprint(
        config=config,
        cutsets=cutsets,
        initial_state=initial_state,
        intervals=intervals,
    )
end

function _make_cut_sweep_context(blueprint::CutSweepBlueprint, D_a::Float64)
    params = RDParameters(D_a=D_a, D_i=30 * D_a)
    connected = _settled_pattern_snapshot(blueprint.initial_state, params, blueprint.config; cuts=Int[])
    return CutSweepContext(
        blueprint=blueprint,
        params=params,
        connected=connected,
    )
end

function _segment_snapshot!(context::CutSweepContext, range::UnitRange{Int}; steady_stop::Bool=true)
    key = (first(range), last(range))
    if steady_stop && haskey(context.interval_cache, key)
        return context.interval_cache[key]
    end
    interval = context.blueprint.intervals[key]
    snapshot = _settled_pattern_snapshot(interval.state, context.params, interval.config; cuts=Int[], steady_stop=steady_stop)
    segment = SegmentSnapshot(
        key,
        length(range),
        snapshot.shape,
        snapshot.peak_count,
        snapshot.A,
        snapshot.I,
    )
    steady_stop && (context.interval_cache[key] = segment)
    return segment
end

function _decomposed_cutset_snapshot!(context::CutSweepContext, cuts::Vector{Int}; steady_stop::Bool=true)
    A = Float64[]
    I = Float64[]
    segments = SegmentSnapshot[]
    for range in _segment_ranges(context.blueprint.config.n_cells, cuts)
        segment = _segment_snapshot!(context, range; steady_stop=steady_stop)
        append!(A, segment.A)
        append!(I, segment.I)
        push!(segments, segment)
    end
    return (
        snapshot=MorphologySnapshot(
            collect(sort(unique(cuts))),
            shape_string(A),
            peak_count(A),
            A,
            I,
        ),
        segments=segments,
    )
end

function _actual_cutset_snapshot(context::CutSweepContext, cuts::Vector{Int}; steady_stop::Bool=true)
    return _settled_pattern_snapshot(
        context.blueprint.initial_state,
        context.params,
        context.blueprint.config;
        cuts=cuts,
        steady_stop=steady_stop,
    )
end

function _cutset_summary(context::CutSweepContext, cuts::Vector{Int})
    sorted_cuts = collect(sort(unique(cuts)))
    decomposition = _decomposed_cutset_snapshot!(context, sorted_cuts)
    snapshot = decomposition.snapshot
    n_cells = context.blueprint.config.n_cells
    cut = length(sorted_cuts) == 1 ? only(sorted_cuts) : nothing
    return CutEvaluation(
        cuts=sorted_cuts,
        cut_count=length(sorted_cuts),
        segment_lengths=_segment_lengths(n_cells, sorted_cuts),
        n_segments=length(decomposition.segments),
        cut_connectivity_loss=cutset_connectivity_loss(n_cells, sorted_cuts),
        shape=snapshot.shape,
        peak_count=snapshot.peak_count,
        A=snapshot.A,
        I=snapshot.I,
        segments=decomposition.segments,
        peak_delta=snapshot.peak_count - context.connected.peak_count,
        shape_changed=snapshot.shape != context.connected.shape,
        profile_l1_mean=_profile_l1_mean(snapshot.A, context.connected.A),
        shape_distance=_levenshtein_distance(snapshot.shape, context.connected.shape),
        peak_delta_abs=0,
        severity_score=0.0,
        cut=cut,
        left_cells=cut,
        right_cells=isnothing(cut) ? nothing : n_cells - cut,
    )
end

function _annotate_severity!(entries::Vector{CutEvaluation})
    isempty(entries) && error("entries must be non-empty")
    max_peak_delta = maximum(abs(entry.peak_delta) for entry in entries)
    max_profile_l1 = maximum(entry.profile_l1_mean for entry in entries)
    max_shape_distance = maximum(entry.shape_distance for entry in entries)
    for entry in entries
        peak_norm = max_peak_delta == 0 ? 0.0 : abs(entry.peak_delta) / max_peak_delta
        profile_norm = max_profile_l1 == 0 ? 0.0 : entry.profile_l1_mean / max_profile_l1
        shape_norm = max_shape_distance == 0 ? 0.0 : entry.shape_distance / max_shape_distance
        entry.peak_delta_abs = abs(entry.peak_delta)
        entry.severity_score = (peak_norm + profile_norm + shape_norm) / 3
    end
    return SeverityCalibration(max_peak_delta, max_profile_l1, max_shape_distance)
end

function _shuffle_tied_entries!(
    ordered::Vector{CutEvaluation},
    signature::Function,
    rng::AbstractRNG,
)
    start_idx = 1
    while start_idx <= length(ordered)
        stop_idx = start_idx
        while stop_idx < length(ordered) && signature(ordered[stop_idx + 1]) == signature(ordered[start_idx])
            stop_idx += 1
        end
        if stop_idx > start_idx
            ordered[start_idx:stop_idx] = shuffle(rng, ordered[start_idx:stop_idx])
        end
        start_idx = stop_idx + 1
    end
    return ordered
end

function _connectivity_signature(entry::CutEvaluation)
    return (
        entry.cut_connectivity_loss,
        _segment_balance(entry.segment_lengths),
        _reflection_invariant_partition_key(entry.segment_lengths),
    )
end

function _connectivity_order(entries::Vector{CutEvaluation}; rng::Union{Nothing,AbstractRNG}=nothing, randomize_ties::Bool=false)
    ordered = collect(entries)
    sort!(
        ordered;
        by=entry -> (
            -entry.cut_connectivity_loss,
            _segment_balance(entry.segment_lengths),
            _reflection_invariant_partition_key(entry.segment_lengths),
            join(string.(entry.cuts), ","),
        ),
    )
    if randomize_ties
        isnothing(rng) && error("randomize_ties=true requires an rng")
        _shuffle_tied_entries!(ordered, _connectivity_signature, rng)
    end
    return ordered
end

function _severity_signature(entry::CutEvaluation)
    return (
        entry.severity_score,
        entry.cut_connectivity_loss,
    )
end

function _severity_order(entries::Vector{CutEvaluation}; rng::Union{Nothing,AbstractRNG}=nothing, randomize_ties::Bool=false)
    ordered = collect(entries)
    sort!(
        ordered;
        by=entry -> (
            -entry.severity_score,
            -entry.cut_connectivity_loss,
            join(string.(entry.cuts), ","),
        ),
    )
    if randomize_ties
        isnothing(rng) && error("randomize_ties=true requires an rng")
        _shuffle_tied_entries!(ordered, _severity_signature, rng)
    end
    return ordered
end

function _severity_target_set(entries::Vector{CutEvaluation}, target_top_k::Int)
    1 <= target_top_k <= length(entries) || error("target_top_k must satisfy 1 <= target_top_k <= candidate count")
    return Set(_cutset_key(entry.cuts) for entry in _severity_order(entries)[1:target_top_k])
end

function _candidate_cutsets(n_cells::Int, cut_count::Int)
    n_cells >= 2 || error("n_cells must be >= 2")
    1 <= cut_count < n_cells || error("cut_count must satisfy 1 <= cut_count < n_cells")
    cuts = collect(1:(n_cells - 1))
    results = Vector{Vector{Int}}()
    current = Int[]
    function rec(start_idx::Int, remaining::Int)
        if remaining == 0
            push!(results, copy(current))
            return
        end
        last_start = length(cuts) - remaining + 1
        for idx in start_idx:last_start
            push!(current, cuts[idx])
            rec(idx + 1, remaining - 1)
            pop!(current)
        end
    end
    rec(1, cut_count)
    return results
end

function _fragment_isolation_cutsets(n_cells::Int, fragment_size::Int; left_cuts::Union{Nothing,Vector{Int}}=nothing)
    1 <= fragment_size <= n_cells - 2 || error("fragment_size must satisfy 1 <= fragment_size <= n_cells - 2")
    raw_left_cuts = isnothing(left_cuts) ? collect(1:(n_cells - fragment_size - 1)) : collect(sort(unique(left_cuts)))
    all(1 <= left_cut < left_cut + fragment_size < n_cells for left_cut in raw_left_cuts) || error("left_cuts must satisfy 1 <= left_cut < left_cut + fragment_size < n_cells")
    return [Int[left_cut, left_cut + fragment_size] for left_cut in raw_left_cuts]
end

function _normalize_cutsets(
    n_cells::Int,
    cut_count::Int,
    cutsets::Vector{Vector{Int}};
    allow_empty::Bool=false,
    label::String="cutsets",
)
    normalized = Vector{Vector{Int}}()
    seen = Set{Tuple{Vararg{Int}}}()
    for raw_cuts in cutsets
        cuts = collect(sort(unique(raw_cuts)))
        length(cuts) == cut_count || error("$label entries must each contain exactly $cut_count distinct cuts")
        all(1 <= cut < n_cells for cut in cuts) || error("$label entries must satisfy 1 <= cut < n_cells")
        key = Tuple(cuts)
        if !(key in seen)
            push!(seen, key)
            push!(normalized, cuts)
        end
    end
    isempty(normalized) && !allow_empty && error("$label must be non-empty")
    return normalized
end

function _resolve_validation_cutsets(cutsets::Vector{Vector{Int}}, validate_cutsets::Vector{Vector{Int}}, validation_mode::Symbol)
    validation_mode in (:none, :auto, :all) || error("validation_mode must be one of :none, :auto, :all")
    if !isempty(validate_cutsets)
        return validate_cutsets
    end
    if validation_mode == :all
        return cutsets
    elseif validation_mode == :auto && length(cutsets) <= 32
        return cutsets
    end
    return Vector{Vector{Int}}()
end

function _top_k_margin(entries::Vector{CutEvaluation}, top_k::Int)
    1 <= top_k <= length(entries) || error("top_k must satisfy 1 <= top_k <= candidate count")
    top_k == length(entries) && return nothing
    return entries[top_k].severity_score - entries[top_k + 1].severity_score
end

function _first_success(order::Vector{CutEvaluation}, success_map::Dict{Tuple,Bool}, H::Int)
    for (idx, entry) in enumerate(order)
        if get(success_map, _cutset_key(entry.cuts), false)
            return Float64(idx), true, entry.cuts
        end
    end
    return Float64(H), false, Int[]
end

function _paired_trial_summary(agent_costs::Vector{Float64}, agent_solved::Vector{Bool}, blind_costs::Vector{Float64}, blind_solved::Vector{Bool}, H::Int)
    length(agent_costs) == length(agent_solved) == length(blind_costs) == length(blind_solved) || error("trial vectors must have the same length")
    n_trials = length(agent_costs)
    n_trials >= 1 || error("trial vectors must be non-empty")

    agent_censored = [agent_solved[idx] ? agent_costs[idx] : Float64(H) for idx in 1:n_trials]
    blind_censored = [blind_solved[idx] ? blind_costs[idx] : Float64(H) for idx in 1:n_trials]
    tau_agent = _mean_value(agent_censored)
    tau_blind = _mean_value(blind_censored)
    k_lower = log10(tau_blind / tau_agent)

    both_agent = Float64[]
    both_blind = Float64[]
    for idx in 1:n_trials
        if agent_solved[idx] && blind_solved[idx]
            push!(both_agent, agent_costs[idx])
            push!(both_blind, blind_costs[idx])
        end
    end
    k_both = nothing
    tau_agent_both = nothing
    tau_blind_both = nothing
    if !isempty(both_agent)
        tau_agent_both = _mean_value(both_agent)
        tau_blind_both = _mean_value(both_blind)
        k_both = log10(tau_blind_both / tau_agent_both)
    end

    both_solved = count(identity, agent_solved .& blind_solved)
    return PairedTrialSummary(
        k_lower,
        k_both,
        tau_agent,
        tau_blind,
        tau_agent_both,
        tau_blind_both,
        count(identity, agent_solved) / n_trials,
        count(identity, blind_solved) / n_trials,
        both_solved / n_trials,
        n_trials,
        count(identity, agent_solved),
        count(identity, blind_solved),
        both_solved,
        [
            "lower_bound_censored_at_H replaces unsolved trials with cost=H; this makes K conservative when blind fails.",
        ],
    )
end

function _validate_factorization(context::CutSweepContext, cutsets::Vector{Vector{Int}})
    validations = ValidationCase[]
    max_profile_error = 0.0
    max_peak_count_error = 0
    for cuts in cutsets
        actual = _actual_cutset_snapshot(context, cuts; steady_stop=false)
        predicted = _decomposed_cutset_snapshot!(context, cuts; steady_stop=false).snapshot
        profile_error = maximum(abs.(actual.A .- predicted.A))
        peak_error = abs(actual.peak_count - predicted.peak_count)
        shape_match = actual.shape == predicted.shape
        push!(validations, ValidationCase(collect(sort(unique(cuts))), profile_error, peak_error, shape_match))
        max_profile_error = max(max_profile_error, profile_error)
        max_peak_count_error = max(max_peak_count_error, peak_error)
    end
    return FactorizationValidation(validations, max_profile_error, max_peak_count_error)
end

function _evaluate_cut_sweep_blueprint(
    blueprint::CutSweepBlueprint,
    D_a::Float64;
    validate_cutsets::Vector{Vector{Int}}=Vector{Vector{Int}}(),
    validation_mode::Symbol=:auto,
)
    resolved_validation_cutsets = _resolve_validation_cutsets(
        blueprint.cutsets,
        _normalize_cutsets(
            blueprint.config.n_cells,
            length(first(blueprint.cutsets)),
            validate_cutsets;
            allow_empty=true,
            label="validate_cutsets",
        ),
        validation_mode,
    )
    context = _make_cut_sweep_context(blueprint, D_a)
    entries = [_cutset_summary(context, cuts) for cuts in blueprint.cutsets]
    calibration = _annotate_severity!(entries)
    validation = isempty(resolved_validation_cutsets) ? nothing : _validate_factorization(context, resolved_validation_cutsets)
    return CutSweepResult(
        blueprint.config.n_cells,
        blueprint.config.seed,
        D_a,
        length(first(blueprint.cutsets)),
        length(blueprint.cutsets),
        context.connected,
        entries,
        _connectivity_order(entries),
        _severity_order(entries),
        calibration,
        ValidationScope(
            String(validation_mode),
            length(resolved_validation_cutsets),
            length(resolved_validation_cutsets) == length(blueprint.cutsets),
        ),
        validation,
    )
end

function wiring_cut_sweep_demo(;
    n_cells::Int=100,
    seed::Int=0,
    D_a::Float64=REFERENCE_ONE_HEAD_D_A_100,
    cut_count::Int=1,
    candidate_cutsets::Union{Nothing,Vector{Vector{Int}}}=nothing,
    validate_cutsets::Vector{Vector{Int}}=Vector{Vector{Int}}(),
    validation_mode::Symbol=:auto,
)
    blueprint = _build_cut_sweep_blueprint(
        n_cells=n_cells,
        seed=seed,
        cut_count=cut_count,
        candidate_cutsets=candidate_cutsets,
    )
    return _evaluate_cut_sweep_blueprint(
        blueprint,
        D_a;
        validate_cutsets=validate_cutsets,
        validation_mode=validation_mode,
    )
end

function wiring_fragment_family_demo(;
    n_cells::Int=100,
    seed::Int=0,
    D_a::Float64=REFERENCE_ONE_HEAD_D_A_100,
    fragment_size::Int=max(1, n_cells ÷ 4),
    left_cuts::Union{Nothing,Vector{Int}}=nothing,
    validation_mode::Symbol=:auto,
)
    cutsets = _fragment_isolation_cutsets(n_cells, fragment_size; left_cuts=left_cuts)
    sweep = wiring_cut_sweep_demo(
        n_cells=n_cells,
        seed=seed,
        D_a=D_a,
        cut_count=2,
        candidate_cutsets=cutsets,
        validation_mode=validation_mode,
    )
    placements = [
        FragmentPlacement(cuts, (cuts[1] + 1, cuts[2]), fragment_size) for cuts in cutsets
    ]
    return FragmentFamilyResult(
        sweep,
        "isolate_contiguous_fragment",
        fragment_size,
        isnothing(left_cuts) ? [cuts[1] for cuts in cutsets] : collect(sort(unique(left_cuts))),
        cutsets,
        placements,
    )
end

function wiring_severity_phase_scan_demo(;
    n_cells::Int=100,
    seed::Int=0,
    D_a_values::Vector{Float64}=[REFERENCE_ONE_HEAD_D_A_100],
    cut_count::Int=1,
    top_k::Int=1,
    candidate_cutsets::Union{Nothing,Vector{Vector{Int}}}=nothing,
    validation_mode::Symbol=:none,
)
    isempty(D_a_values) && error("D_a_values must be non-empty")
    top_k >= 1 || error("top_k must be >= 1")
    blueprint = _build_cut_sweep_blueprint(
        n_cells=n_cells,
        seed=seed,
        cut_count=cut_count,
        candidate_cutsets=candidate_cutsets,
    )

    scan = Vector{SeverityScanSlice}(undef, length(D_a_values))
    regime_changes = RegimeChange[]
    Base.Threads.@threads for idx in eachindex(D_a_values)
        D_a = D_a_values[idx]
        sweep = _evaluate_cut_sweep_blueprint(blueprint, D_a; validation_mode=validation_mode)
        connectivity_ranking = sweep.ranking_connectivity
        decomposition_ranking = sweep.ranking_decomposition
        k = min(top_k, length(decomposition_ranking))
        top_entries = decomposition_ranking[1:k]
        top_k_cutsets = [entry.cuts for entry in top_entries]
        best_connectivity = first(connectivity_ranking)
        best_decomposition = first(top_entries)
        scan[idx] = SeverityScanSlice(
            D_a,
            sweep.candidate_count,
            k,
            top_k_cutsets,
            _top_k_margin(decomposition_ranking, k),
            sweep.connected,
            best_connectivity,
            best_decomposition,
            sweep.validation_scope,
        )
    end

    previous_top_k_cutsets::Union{Nothing,Vector{Vector{Int}}} = nothing
    previous_D_a::Union{Nothing,Float64} = nothing
    for slice in scan
        top_k_cutsets = slice.top_k_cutsets
        D_a = slice.D_a
        if !isnothing(previous_top_k_cutsets) && previous_top_k_cutsets != top_k_cutsets
            push!(regime_changes, RegimeChange(previous_D_a, D_a, previous_top_k_cutsets, top_k_cutsets))
        end
        previous_top_k_cutsets = top_k_cutsets
        previous_D_a = D_a
    end

    best_decomposition_trace = [
        BestDecompositionPoint(
            slice.D_a,
            slice.best_decomposition.cuts,
            slice.best_decomposition.severity_score,
            slice.best_decomposition.peak_count,
            slice.best_decomposition.shape,
        ) for slice in scan
    ]

    return SeverityPhaseScanResult(
        n_cells,
        seed,
        cut_count,
        top_k,
        collect(D_a_values),
        isnothing(candidate_cutsets) ? "all_$(cut_count)_cutsets" : "custom_candidate_cutsets",
        isnothing(candidate_cutsets) ? nothing : blueprint.cutsets,
        scan,
        best_decomposition_trace,
        regime_changes,
        [
            "Each slice recomputes the decomposition-ranked severity landscape at fixed D_a.",
            "regime_changes records where the identity of the top-k cutset family changes across the supplied D_a grid.",
        ],
    )
end

function wiring_intervention_k_demo(;
    n_cells::Int=100,
    seed::Int=0,
    D_a::Float64=REFERENCE_ONE_HEAD_D_A_100,
    trials::Int=1,
    cut_count::Int=1,
    target_peak_count::Union{Nothing,Int}=nothing,
    target_shape::Union{Nothing,String}=nothing,
    target_top_k::Union{Nothing,Int}=nothing,
    require_shape_change::Bool=true,
    candidate_cutsets::Union{Nothing,Vector{Vector{Int}}}=nothing,
    validate_cutsets::Vector{Vector{Int}}=Vector{Vector{Int}}(),
    validation_mode::Symbol=:auto,
)
    trials >= 1 || error("trials must be >= 1")
    agent_costs_connectivity = Float64[]
    agent_solved_connectivity = Bool[]
    agent_costs_decomposition = Float64[]
    agent_solved_decomposition = Bool[]
    blind_costs = Float64[]
    blind_solved = Bool[]
    trial_results = InterventionTrial[]
    reference_sweep::Union{Nothing,CutSweepResult} = nothing
    first_validation::Union{Nothing,FactorizationValidation} = nothing
    H = 0

    for trial_idx in 0:(trials - 1)
        trial_seed = seed + trial_idx
        sweep = wiring_cut_sweep_demo(
            n_cells=n_cells,
            seed=trial_seed,
            D_a=D_a,
            cut_count=cut_count,
            candidate_cutsets=candidate_cutsets,
            validate_cutsets=trial_idx == 0 ? validate_cutsets : Vector{Vector{Int}}(),
            validation_mode=validation_mode,
        )
        trial_idx == 0 && (reference_sweep = sweep)
        trial_idx == 0 && (first_validation = sweep.validation)
        connected = sweep.connected
        entries = sweep.cuts
        H = length(entries)
        success_target = isnothing(target_peak_count) ? connected.peak_count + cut_count : Int(target_peak_count)
        severity_targets = isnothing(target_top_k) ? nothing : _severity_target_set(entries, Int(target_top_k))
        success_map = Dict{Tuple,Bool}()
        n_successes = 0
        for entry in entries
            is_success = if isnothing(severity_targets)
                peak_success = entry.peak_count == success_target
                shape_target_success = isnothing(target_shape) ? true : entry.shape == target_shape
                shape_change_success = require_shape_change ? entry.shape_changed : true
                peak_success && shape_target_success && shape_change_success
            else
                _cutset_key(entry.cuts) in severity_targets
            end
            success_map[_cutset_key(entry.cuts)] = is_success
            n_successes += is_success ? 1 : 0
        end

        connectivity_order = _connectivity_order(entries; rng=MersenneTwister(trial_seed), randomize_ties=true)
        decomposition_order = _severity_order(entries; rng=MersenneTwister(trial_seed + 10_000), randomize_ties=true)
        blind_order = shuffle(MersenneTwister(trial_seed), collect(entries))

        connectivity_cost, connectivity_success, connectivity_first = _first_success(connectivity_order, success_map, H)
        decomposition_cost, decomposition_success, decomposition_first = _first_success(decomposition_order, success_map, H)
        blind_cost, blind_success, blind_first = _first_success(blind_order, success_map, H)

        push!(agent_costs_connectivity, connectivity_cost)
        push!(agent_solved_connectivity, connectivity_success)
        push!(agent_costs_decomposition, decomposition_cost)
        push!(agent_solved_decomposition, decomposition_success)
        push!(blind_costs, blind_cost)
        push!(blind_solved, blind_success)
        push!(
            trial_results,
            InterventionTrial(
                trial_seed,
                H,
                n_successes,
                success_target,
                target_shape,
                target_top_k,
                connectivity_cost,
                decomposition_cost,
                blind_cost,
                connectivity_first,
                decomposition_first,
                blind_first,
            ),
        )
    end

    reference_sweep isa CutSweepResult || error("missing reference sweep")

    return InterventionKResult(
        1,
        "addenda/k-semantics-reference",
        cut_count,
        trials,
        reference_sweep,
        first_validation,
        _paired_trial_summary(
            agent_costs_connectivity,
            agent_solved_connectivity,
            blind_costs,
            blind_solved,
            H,
        ),
        _paired_trial_summary(
            agent_costs_decomposition,
            agent_solved_decomposition,
            blind_costs,
            blind_solved,
            H,
        ),
        trial_results,
        isnothing(target_peak_count) ? reference_sweep.connected.peak_count + cut_count : target_peak_count,
        target_shape,
        target_top_k,
        [
            "This is an intervention-search K over admissible cut interventions, not an intrinsic tissue K after cutting.",
            "The decomposition-ranked policy uses exact factorization of severed chain dynamics into independently settled contiguous segments.",
            "The connectivity-ranked policy keeps the earlier wiring-only heuristic based on lost cross-segment coupling.",
            "When target_top_k is set, success means identifying one of the most severe cuts under the exact decomposition-ranked phenotype shift, rather than merely any cut with the requested peak count.",
        ],
    )
end

function wiring_bistability_demo(; n_cells::Int=100, seed::Int=0, cut::Int=n_cells ÷ 2, D_a::Float64=REFERENCE_ONE_HEAD_D_A_100)
    connected = _settled_pattern_snapshot(n_cells=n_cells, seed=seed, D_a=D_a, cuts=Int[])
    severed = _settled_pattern_snapshot(n_cells=n_cells, seed=seed, D_a=D_a, cuts=[cut])
    return BistabilityResult(n_cells, seed, cut, D_a, connected, severed)
end

end
