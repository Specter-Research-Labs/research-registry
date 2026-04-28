module Wave

using ..Algebra: AbstractCellState,
    PhaseProgram,
    PhaseState,
    PolynomialObject,
    PortSchema,
    WiringEdge,
    WiringSpec,
    CompiledPhase,
    compile_phase,
    execute_phase,
    normalize_profile,
    normalize_profile!

export WaveConfig,
    WaveCellState,
    WaveExecutionState,
    WaveResult,
    WavePlan,
    CompiledWavePlan,
    normalize_profile,
    make_wave_state,
    set_wave_input!,
    seed_wave_source!,
    integrate_wave!,
    wave_result,
    wave_count,
    wave_count_from_normalized,
    wave_count_composed,
    wave_count_composed_from_normalized,
    wave_phase_outputs,
    wave_phase_program,
    compile_wave_plan

Base.@kwdef struct WaveConfig
    n_peaks_max::Int = 6
    grn_settle_time_small::Float64 = 500.0
    grn_settle_time_large::Float64 = 1500.0
    pre_decay::Float64 = 1.0
    amdr_decay::Float64 = 1.0
    sig_decay::Float64 = 1.0
    sig_diffusion::Float64 = 2.0
    sig_activation_km::Float64 = 0.5
    sig_activation_hill::Float64 = 2.0
    sig_activation_vmax::Float64 = 1.3
    pre_self_km::Float64 = 0.5
    pre_self_hill::Float64 = 3.0
    pre_sig_km::Float64 = 0.3
    pre_amdr_km::Float64 = 0.5
    schm0::Float64 = 0.1
    schm1::Float64 = 0.3
    on_threshold::Float64 = 0.6
    integration_dt::Float64 = 0.1
    steady_tol::Float64 = 1.0e-6
    normalize_input::Bool = false
    source_bug_prev_sig_for_pre0l::Bool = true
end

mutable struct WaveCellState <: AbstractCellState
    mode::Symbol
    pre::Vector{Float64}
    sig::Vector{Float64}
    amdr::Float64
    A_local::Float64
    done::Bool
end

Base.copy(state::WaveCellState) = WaveCellState(
    state.mode,
    copy(state.pre),
    copy(state.sig),
    state.amdr,
    state.A_local,
    state.done,
)

Base.haskey(state::WaveCellState, key::Symbol) = key in (:mode, :pre, :sig, :amdr, :A_local, :done)
Base.get(state::WaveCellState, key::Symbol, default) = haskey(state, key) ? state[key] : default

function Base.getindex(state::WaveCellState, key::Symbol)
    if key === :mode
        return state.mode
    elseif key === :pre
        return state.pre
    elseif key === :sig
        return state.sig
    elseif key === :amdr
        return state.amdr
    elseif key === :A_local
        return state.A_local
    elseif key === :done
        return state.done
    end
    error("WaveCellState has no key $(key)")
end

function Base.setindex!(state::WaveCellState, value, key::Symbol)
    if key === :mode
        state.mode = Symbol(value)
    elseif key === :pre
        state.pre = Float64.(value)
    elseif key === :sig
        state.sig = Float64.(value)
    elseif key === :amdr
        state.amdr = Float64(value)
    elseif key === :A_local
        state.A_local = Float64(value)
    elseif key === :done
        state.done = Bool(value)
    else
        error("WaveCellState has no key $(key)")
    end
    return value
end

struct WaveResult
    count::Float64
    emitted::Vector{Symbol}
    done::BitVector
    input_A::Vector{Float64}
    normalized_A::Vector{Float64}
    final_pre::Matrix{Float64}
    final_sig::Matrix{Float64}
    final_amdr::Vector{Float64}
end

mutable struct WaveExecutionState
    input_A::Vector{Float64}
    normalized_A::Vector{Float64}
    pre::Matrix{Float64}
    sig::Matrix{Float64}
    amdr::Vector{Float64}
    done::BitVector
end

Base.copy(state::WaveExecutionState) = WaveExecutionState(
    copy(state.input_A),
    copy(state.normalized_A),
    copy(state.pre),
    copy(state.sig),
    copy(state.amdr),
    copy(state.done),
)

struct WavePlan
    config::WaveConfig
    n_cells::Int
    n_species::Int
    routing::Tuple{Vector{Int},Vector{Int}}
    n_steps::Int
end

struct CompiledWavePlan
    plan::WavePlan
    program::PhaseProgram
    compiled::CompiledPhase
    nodes::Vector{Symbol}
end

WavePlan(config::WaveConfig, n_cells::Int) = wave_plan(config, n_cells)
CompiledWavePlan(config::WaveConfig, n_cells::Int) = compile_wave_plan(config, n_cells)

function _prepare_wave_input(A::AbstractVector{<:Real}, config::WaveConfig)
    input_A = Float64.(A)
    normalized_A = normalize_profile(input_A)
    wave_A = config.normalize_input ? normalized_A : input_A
    return wave_A, normalized_A
end

function make_wave_state(plan::WavePlan, A::AbstractVector{<:Real}; source_pre::Float64=0.0)
    length(A) == plan.n_cells || error("A length must match plan.n_cells")
    input_A, normalized_A = _prepare_wave_input(A, plan.config)
    state = WaveExecutionState(
        input_A,
        normalized_A,
        zeros(plan.n_species, plan.n_cells),
        zeros(plan.n_species, plan.n_cells),
        zeros(plan.n_cells),
        falses(plan.n_cells),
    )
    source_pre != 0.0 && seed_wave_source!(state; source_pre=source_pre)
    return state
end

function make_wave_state(
    normalized_A::AbstractVector{<:Real},
    config::WaveConfig=WaveConfig();
    source_pre::Float64=0.0,
)
    plan = wave_plan(config, length(normalized_A))
    state = WaveExecutionState(
        Float64.(normalized_A),
        Float64.(normalized_A),
        zeros(plan.n_species, plan.n_cells),
        zeros(plan.n_species, plan.n_cells),
        zeros(plan.n_cells),
        falses(plan.n_cells),
    )
    source_pre != 0.0 && seed_wave_source!(state; source_pre=source_pre)
    return state
end

function set_wave_input!(state::WaveExecutionState, A::AbstractVector{<:Real}, config::WaveConfig=WaveConfig())
    length(A) == length(state.input_A) || error("A length must match existing wave state")
    normalize_profile!(state.normalized_A, A)
    if config.normalize_input
        state.input_A .= state.normalized_A
    else
        state.input_A .= Float64.(A)
    end
    return state
end

function seed_wave_source!(state::WaveExecutionState; source_pre::Float64=1.0)
    source_pre >= 0 || error("source_pre must be >= 0")
    state.pre[1, 1] = source_pre
    return state
end

function _hill_on(x, km, hill)
    ratio = (x / km) ^ hill
    return ratio / (1 + ratio)
end

function _hill_off(x, km, hill)
    ratio = (x / km) ^ hill
    return 1 / (1 + ratio)
end

function _k_vmax_for_stable_one(km, hill)
    ratio = (1 / km) ^ hill
    return (1 + ratio) / ratio
end

function _species_name(idx::Int)
    phase = div(idx - 1, 2)
    suffix = isodd(idx) ? 'L' : 'H'
    return Symbol("S$(phase)$(suffix)")
end

_species_output_port(idx::Int) = Symbol("$(String(_species_name(idx)))_out")
_species_left_port(idx::Int) = Symbol("$(String(_species_name(idx)))_left")
_species_right_port(idx::Int) = Symbol("$(String(_species_name(idx)))_right")

function _validate_wave_config(config::WaveConfig)
    config.n_peaks_max >= 1 || error("n_peaks_max must be >= 1")
    config.integration_dt > 0 || error("integration_dt must be > 0")
    config.steady_tol > 0 || error("steady_tol must be > 0")
    config.grn_settle_time_small >= 0 || error("grn_settle_time_small must be >= 0")
    config.grn_settle_time_large >= 0 || error("grn_settle_time_large must be >= 0")
    return config
end

function _chain_neighbor_indices(n_cells::Int)
    left = zeros(Int, n_cells)
    right = zeros(Int, n_cells)
    for idx in 1:n_cells
        idx > 1 && (left[idx] = idx - 1)
        idx < n_cells && (right[idx] = idx + 1)
    end
    return left, right
end

function _wave_step_count(config::WaveConfig, n_cells::Int)
    settle_time = n_cells < 201 ? config.grn_settle_time_small : config.grn_settle_time_large
    return max(1, ceil(Int, settle_time / config.integration_dt))
end

function wave_plan(config::WaveConfig, n_cells::Int)
    _validate_wave_config(config)
    n_cells >= 1 || error("n_cells must be >= 1")
    return WavePlan(
        config,
        n_cells,
        2 * config.n_peaks_max,
        _chain_neighbor_indices(n_cells),
        _wave_step_count(config, n_cells),
    )
end

function compile_wave_plan(config::WaveConfig, n_cells::Int)
    plan = wave_plan(config, n_cells)
    program = wave_phase_program(config, n_cells)
    compiled = compile_phase(program)
    return CompiledWavePlan(plan, program, compiled, program.wiring.nodes)
end

function _wave_cell_object(config::WaveConfig, node::Symbol)
    n_species = 2 * config.n_peaks_max
    inputs = Symbol[]
    outputs = Symbol[]
    for species in 1:n_species
        push!(inputs, _species_left_port(species))
        push!(inputs, _species_right_port(species))
        push!(outputs, _species_output_port(species))
    end
    schema = PortSchema(inputs, outputs)
    dt = config.integration_dt
    k_vmax = _k_vmax_for_stable_one(config.pre_self_km, config.pre_self_hill)
    return PolynomialObject(
        node,
        [:wave],
        Dict(:wave => schema),
        () -> WaveCellState(
            :wave,
            zeros(n_species),
            zeros(n_species),
            0.0,
            0.0,
            false,
        ),
        (state) -> begin
            haskey(state, :mode) || error("wave cell state must include :mode")
            mode = state[:mode]
            mode == :wave || error("unsupported wave cell mode $(mode)")
            return Dict{Symbol,Any}(
                _species_output_port(species) => state[:sig][species]
                for species in 1:n_species
            )
        end,
        (state, incoming) -> begin
            haskey(state, :mode) || error("wave cell state must include :mode")
            mode = state[:mode]
            mode == :wave || error("unsupported wave cell mode $(mode)")
            pre = state[:pre]
            sig = state[:sig]
            amdr = state[:amdr]
            A_local = state[:A_local]

            sum_pre = sum(pre)
            du_amdr =
                k_vmax * _hill_on(sum_pre, config.pre_amdr_km, config.pre_self_hill) -
                amdr * config.amdr_decay

            new_pre = Vector{Float64}(undef, n_species)
            new_sig = Vector{Float64}(undef, n_species)
            for species in 1:n_species
                iam_high = iseven(species)
                conc = pre[species]
                value = k_vmax * _hill_on(conc, config.pre_self_km, config.pre_self_hill)
                if species > 1
                    prev_sig = sig[species - 1]
                    prev_term = _hill_on(prev_sig, config.pre_sig_km, config.pre_self_hill)
                    morph_term =
                        iam_high ?
                        _hill_on(A_local, config.schm1, config.pre_self_hill) :
                        _hill_off(A_local, config.schm0, config.pre_self_hill)
                    value +=
                        prev_term *
                        morph_term *
                        _hill_off(amdr, config.pre_amdr_km, config.pre_self_hill)
                elseif config.source_bug_prev_sig_for_pre0l
                    prev_pre = pre[n_species]
                    prev_term = _hill_on(prev_pre, config.pre_sig_km, config.pre_self_hill)
                    value +=
                        prev_term *
                        _hill_off(A_local, config.schm0, config.pre_self_hill) *
                        _hill_off(amdr, config.pre_amdr_km, config.pre_self_hill)
                end

                my_sig = sig[species]
                morph_term =
                    iam_high ?
                    _hill_on(A_local, config.schm0, config.pre_self_hill) :
                    _hill_off(A_local, config.schm1, config.pre_self_hill)
                value +=
                    _hill_on(my_sig, config.pre_sig_km, config.pre_self_hill) *
                    morph_term *
                    _hill_off(amdr, config.pre_amdr_km, config.pre_self_hill)
                du_pre = value - config.pre_decay * conc

                left_sig = get(incoming, _species_left_port(species), my_sig)
                right_sig = get(incoming, _species_right_port(species), my_sig)
                lap = left_sig + right_sig - 2 * my_sig
                du_sig =
                    config.sig_activation_vmax *
                    _hill_on(conc, config.sig_activation_km, config.sig_activation_hill) -
                    config.sig_decay * my_sig +
                    config.sig_diffusion * lap

                new_pre[species] = max(0.0, conc + dt * du_pre)
                new_sig[species] = max(0.0, my_sig + dt * du_sig)
            end

            return WaveCellState(
                mode,
                new_pre,
                new_sig,
                max(0.0, amdr + dt * du_amdr),
                A_local,
                state[:done],
            )
        end,
    )
end

function wave_phase_program(config::WaveConfig, n_cells::Int)
    _validate_wave_config(config)
    n_cells >= 1 || error("n_cells must be >= 1")
    nodes = [Symbol("cell_$(idx)") for idx in 1:n_cells]
    objects = Dict(node => _wave_cell_object(config, node) for node in nodes)
    edges = WiringEdge[]
    n_species = 2 * config.n_peaks_max
    for idx in eachindex(nodes)
        node = nodes[idx]
        if idx > 1
            for species in 1:n_species
                push!(
                    edges,
                    WiringEdge(
                        nodes[idx - 1],
                        _species_output_port(species),
                        node,
                        _species_left_port(species),
                    ),
                )
            end
        end
        if idx < length(nodes)
            for species in 1:n_species
                push!(
                    edges,
                    WiringEdge(
                        nodes[idx + 1],
                        _species_output_port(species),
                        node,
                        _species_right_port(species),
                    ),
                )
            end
        end
    end
    return PhaseProgram(:wave_tissue, :wave, objects, WiringSpec(nodes, edges))
end

function _wave_neighbor_indices(program::PhaseProgram)
    node_to_idx = Dict(node => idx for (idx, node) in enumerate(program.wiring.nodes))
    left = zeros(Int, length(program.wiring.nodes))
    right = zeros(Int, length(program.wiring.nodes))
    for edge in program.wiring.edges
        dst_idx = node_to_idx[edge.dst_node]
        src_idx = node_to_idx[edge.src_node]
        if endswith(String(edge.dst_port), "_left")
            left[dst_idx] = src_idx
        elseif endswith(String(edge.dst_port), "_right")
            right[dst_idx] = src_idx
        end
    end
    return left, right
end

function _wave_state_delta(
    prev_amdr::AbstractVector{Float64},
    prev_pre::AbstractMatrix{Float64},
    prev_sig::AbstractMatrix{Float64},
    amdr::AbstractVector{Float64},
    pre::AbstractMatrix{Float64},
    sig::AbstractMatrix{Float64},
)
    n_cells = length(amdr)
    cell_delta = zeros(Float64, n_cells)
    for cell in 1:n_cells
        cell_delta[cell] = abs(amdr[cell] - prev_amdr[cell])
    end
    for species in axes(pre, 1), cell in axes(pre, 2)
        cell_delta[cell] = max(
            cell_delta[cell],
            abs(pre[species, cell] - prev_pre[species, cell]),
            abs(sig[species, cell] - prev_sig[species, cell]),
        )
    end
    return cell_delta
end

function _wave_state_delta(prev_state, next_state)
    delta = abs(next_state[:amdr] - prev_state[:amdr])
    for idx in eachindex(prev_state[:pre])
        delta = max(
            delta,
            abs(next_state[:pre][idx] - prev_state[:pre][idx]),
            abs(next_state[:sig][idx] - prev_state[:sig][idx]),
        )
    end
    return delta
end

function _emitted_labels(pre::AbstractMatrix, sig::AbstractMatrix, threshold::Float64)
    n_species, n_cells = size(sig)
    labels = Vector{Symbol}(undef, n_cells)
    for cell in 1:n_cells
        label = Symbol("S0L")
        best_value = -Inf
        for species in 1:n_species
            value = max(pre[species, cell], sig[species, cell])
            if value > threshold && value >= best_value
                best_value = value
                label = _species_name(species)
            end
        end
        labels[cell] = label
    end
    return labels
end

function _wave_derivative!(
    du_amdr::AbstractVector{Float64},
    du_pre::AbstractMatrix{Float64},
    du_sig::AbstractMatrix{Float64},
    amdr::AbstractVector{Float64},
    pre::AbstractMatrix{Float64},
    sig::AbstractMatrix{Float64},
    A::AbstractVector{Float64},
    config::WaveConfig,
    routing,
)
    left, right = routing
    n_cells = length(A)
    n_species = 2 * config.n_peaks_max

    k_vmax = _k_vmax_for_stable_one(config.pre_self_km, config.pre_self_hill)
    for cell in 1:n_cells
        sum_pre = 0.0
        for species in 1:n_species
            sum_pre += pre[species, cell]
        end
        du_amdr[cell] =
            k_vmax * _hill_on(sum_pre, config.pre_amdr_km, config.pre_self_hill) -
            amdr[cell] * config.amdr_decay
    end

    for species in 1:n_species
        iam_high = iseven(species)
        for cell in 1:n_cells
            conc = pre[species, cell]
            value = k_vmax * _hill_on(conc, config.pre_self_km, config.pre_self_hill)
            if species > 1
                prev_sig = sig[species - 1, cell]
                prev_term = _hill_on(prev_sig, config.pre_sig_km, config.pre_self_hill)
                morph_term =
                    iam_high ?
                    _hill_on(A[cell], config.schm1, config.pre_self_hill) :
                    _hill_off(A[cell], config.schm0, config.pre_self_hill)
                value +=
                    prev_term *
                    morph_term *
                    _hill_off(amdr[cell], config.pre_amdr_km, config.pre_self_hill)
            elseif config.source_bug_prev_sig_for_pre0l
                prev_pre = pre[n_species, cell]
                prev_term = _hill_on(prev_pre, config.pre_sig_km, config.pre_self_hill)
                value +=
                    prev_term *
                    _hill_off(A[cell], config.schm0, config.pre_self_hill) *
                    _hill_off(amdr[cell], config.pre_amdr_km, config.pre_self_hill)
            end

            my_sig = sig[species, cell]
            morph_term =
                iam_high ?
                _hill_on(A[cell], config.schm0, config.pre_self_hill) :
                _hill_off(A[cell], config.schm1, config.pre_self_hill)
            value +=
                _hill_on(my_sig, config.pre_sig_km, config.pre_self_hill) *
                morph_term *
                _hill_off(amdr[cell], config.pre_amdr_km, config.pre_self_hill)
            du_pre[species, cell] = value - config.pre_decay * conc

            left_idx = left[cell] == 0 ? cell : left[cell]
            right_idx = right[cell] == 0 ? cell : right[cell]
            lap = sig[species, left_idx] + sig[species, right_idx] - 2 * my_sig
            du_sig[species, cell] =
                config.sig_activation_vmax *
                _hill_on(conc, config.sig_activation_km, config.sig_activation_hill) -
                config.sig_decay * my_sig +
                config.sig_diffusion * lap
        end
    end

    return nothing
end

function _integrate_wave!(
    amdr::Vector{Float64},
    pre::Matrix{Float64},
    sig::Matrix{Float64},
    A::Vector{Float64},
    plan::WavePlan,
    steady_stop::Bool=true,
)
    du_amdr = zeros(size(amdr))
    du_pre = zeros(size(pre))
    du_sig = zeros(size(sig))
    prev_amdr = similar(amdr)
    prev_pre = similar(pre)
    prev_sig = similar(sig)
    dt = plan.config.integration_dt
    done = falses(length(amdr))

    for _ in 1:plan.n_steps
        copyto!(prev_amdr, amdr)
        copyto!(prev_pre, pre)
        copyto!(prev_sig, sig)
        _wave_derivative!(du_amdr, du_pre, du_sig, amdr, pre, sig, A, plan.config, plan.routing)
        for cell in eachindex(amdr)
            amdr[cell] = max(0.0, amdr[cell] + dt * du_amdr[cell])
        end
        for species in axes(pre, 1), cell in axes(pre, 2)
            pre[species, cell] = max(0.0, pre[species, cell] + dt * du_pre[species, cell])
            sig[species, cell] = max(0.0, sig[species, cell] + dt * du_sig[species, cell])
        end
        done .= _wave_state_delta(prev_amdr, prev_pre, prev_sig, amdr, pre, sig) .<= plan.config.steady_tol
        steady_stop && all(done) && break
    end

    return copy(done)
end

function _wave_result(
    input_A::Vector{Float64},
    normalized::Vector{Float64},
    pre::Matrix{Float64},
    sig::Matrix{Float64},
    amdr::Vector{Float64},
    done::BitVector,
    threshold::Float64,
)
    head_pre = @view pre[:, end]
    on_indices = findall(>(threshold), head_pre)
    count = isempty(on_indices) ? 0.0 : last(on_indices) / 2
    emitted = _emitted_labels(pre, sig, threshold)
    return WaveResult(
        count,
        emitted,
        done,
        input_A,
        normalized,
        pre,
        sig,
        amdr,
    )
end

function integrate_wave!(state::WaveExecutionState, plan::WavePlan; steady_stop::Bool=true)
    length(state.input_A) == plan.n_cells || error("wave state input length must match plan.n_cells")
    size(state.pre) == (plan.n_species, plan.n_cells) || error("wave state pre matrix must match plan dimensions")
    size(state.sig) == (plan.n_species, plan.n_cells) || error("wave state sig matrix must match plan dimensions")
    length(state.amdr) == plan.n_cells || error("wave state amdr length must match plan.n_cells")
    state.done .= _integrate_wave!(state.amdr, state.pre, state.sig, state.input_A, plan, steady_stop)
    return state
end

function wave_result(state::WaveExecutionState, config::WaveConfig=WaveConfig())
    return _wave_result(
        copy(state.input_A),
        copy(state.normalized_A),
        copy(state.pre),
        copy(state.sig),
        copy(state.amdr),
        copy(state.done),
        config.on_threshold,
    )
end

function wave_count_from_normalized(
    plan::WavePlan,
    normalized_A::AbstractVector{<:Real};
    source_pre::Float64=1.0,
)
    length(normalized_A) == plan.n_cells || error("normalized_A length must match plan.n_cells")
    state = WaveExecutionState(
        Float64.(normalized_A),
        Float64.(normalized_A),
        zeros(plan.n_species, plan.n_cells),
        zeros(plan.n_species, plan.n_cells),
        zeros(plan.n_cells),
        falses(plan.n_cells),
    )
    source_pre != 0.0 && seed_wave_source!(state; source_pre=source_pre)
    integrate_wave!(state, plan)
    return wave_result(state, plan.config)
end

function wave_count_from_normalized(
    normalized_A::AbstractVector{<:Real},
    config::WaveConfig=WaveConfig();
    source_pre::Float64=1.0,
)
    plan = wave_plan(config, length(normalized_A))
    return wave_count_from_normalized(plan, normalized_A; source_pre=source_pre)
end

function wave_count(A::AbstractVector{<:Real}, config::WaveConfig=WaveConfig())
    plan = wave_plan(config, length(A))
    state = make_wave_state(plan, A; source_pre=1.0)
    integrate_wave!(state, plan)
    result = wave_result(state, config)
    return WaveResult(
        result.count,
        result.emitted,
        result.done,
        Float64.(A),
        normalize_profile(Float64.(A)),
        result.final_pre,
        result.final_sig,
        result.final_amdr,
    )
end

function wave_count_composed_from_normalized(
    compiled_plan::CompiledWavePlan,
    normalized_A::AbstractVector{<:Real};
    source_pre::Float64=1.0,
)
    length(normalized_A) == compiled_plan.plan.n_cells || error("normalized_A length must match plan.n_cells")
    state = WaveExecutionState(
        Float64.(normalized_A),
        Float64.(normalized_A),
        zeros(compiled_plan.plan.n_species, compiled_plan.plan.n_cells),
        zeros(compiled_plan.plan.n_species, compiled_plan.plan.n_cells),
        zeros(compiled_plan.plan.n_cells),
        falses(compiled_plan.plan.n_cells),
    )
    source_pre != 0.0 && seed_wave_source!(state; source_pre=source_pre)
    integrate_wave!(state, compiled_plan.plan)
    return wave_result(state, compiled_plan.plan.config)
end

function wave_count_composed_from_normalized(
    normalized_A::AbstractVector{<:Real},
    config::WaveConfig=WaveConfig();
    source_pre::Float64=1.0,
)
    compiled_plan = compile_wave_plan(config, length(normalized_A))
    return wave_count_composed_from_normalized(compiled_plan, normalized_A; source_pre=source_pre)
end

function wave_count_composed(A::AbstractVector{<:Real}, config::WaveConfig=WaveConfig())
    plan = compile_wave_plan(config, length(A))
    state = make_wave_state(plan.plan, A; source_pre=1.0)
    integrate_wave!(state, plan.plan)
    result = wave_result(state, config)
    return WaveResult(
        result.count,
        result.emitted,
        result.done,
        Float64.(A),
        normalize_profile(Float64.(A)),
        result.final_pre,
        result.final_sig,
        result.final_amdr,
    )
end

function wave_phase_outputs(result::WaveResult)
    return Dict(
        :peak_count => result.count,
        :emitted => copy(result.emitted),
        :done => copy(result.done),
    )
end

end
