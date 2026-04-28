module Controller

using OrdinaryDiffEq: Rosenbrock23, solve
using SciMLBase: ODEProblem
using ..Algebra: AbstractCellState,
    CompiledPhase,
    DependentLens,
    PhaseState,
    PolynomialObject,
    PortSchema,
    compile_phase,
    execute_phase,
    normalize_profile!,
    rd_to_wave_lens,
    wave_to_ctrl_lens
using ..RD: RDCellState,
    RDParameters,
    RDChainConfig,
    _rd_derivative!,
    _rd_cell_object,
    make_rd_state,
    spread_pattern!,
    linear_spread!,
    preseed_lxh!,
    settle_rd_composed!,
    peak_count,
    rd_phase_program,
    shape_string
using ..Wave: WaveCellState,
    WaveConfig,
    CompiledWavePlan,
    WaveExecutionState,
    WaveResult,
    _wave_cell_object,
    compile_wave_plan,
    make_wave_state,
    _wave_derivative!,
    seed_wave_source!,
    wave_count,
    wave_result,
    wave_phase_outputs

export ClosedLoopConfig,
    CompiledClosedLoopMachine,
    ClosedLoopMachineState,
    ClosedLoopRun,
    ControllerTraceEntry,
    compile_closed_loop_machine,
    run_closed_loop_machine,
    closed_loop,
    closed_loop_composed,
    hybrid_cell_object,
    rd_pattern_demo,
    wave_count_demo,
    closed_loop_demo

mutable struct HybridCellState <: AbstractCellState
    mode::Symbol
    rd::RDCellState
    wave::WaveCellState
    peak_count::Float64
end

Base.copy(state::HybridCellState) = HybridCellState(
    state.mode,
    copy(state.rd),
    copy(state.wave),
    state.peak_count,
)

Base.haskey(state::HybridCellState, key::Symbol) = key in (
    :mode,
    :A,
    :I,
    :pre,
    :sig,
    :amdr,
    :A_local,
    :done,
    :peak_count,
)
Base.get(state::HybridCellState, key::Symbol, default) = haskey(state, key) ? state[key] : default

function Base.getindex(state::HybridCellState, key::Symbol)
    if key === :mode
        return state.mode
    elseif key === :A || key === :I
        return state.rd[key]
    elseif key in (:pre, :sig, :amdr, :A_local, :done)
        return state.wave[key]
    elseif key === :peak_count
        return state.peak_count
    end
    error("HybridCellState has no key $(key)")
end

function Base.setindex!(state::HybridCellState, value, key::Symbol)
    if key === :mode
        state.mode = Symbol(value)
    elseif key === :A || key === :I
        state.rd[key] = value
    elseif key in (:pre, :sig, :amdr, :A_local, :done)
        state.wave[key] = value
    elseif key === :peak_count
        state.peak_count = Float64(value)
    else
        error("HybridCellState has no key $(key)")
    end
    return value
end

function _merge_state(base::HybridCellState, patch::RDCellState)
    next_state = copy(base)
    next_state.rd = patch
    return next_state
end

function _merge_state(base::AbstractDict, patch::RDCellState)
    next_state = Dict{Symbol,Any}(base)
    next_state[:A] = patch.A
    next_state[:I] = patch.I
    return next_state
end

function _merge_state(base::HybridCellState, patch::WaveCellState)
    next_state = copy(base)
    next_state.wave = patch
    return next_state
end

function _merge_state(base::AbstractDict, patch::WaveCellState)
    next_state = Dict{Symbol,Any}(base)
    next_state[:pre] = copy(patch.pre)
    next_state[:sig] = copy(patch.sig)
    next_state[:amdr] = patch.amdr
    next_state[:A_local] = patch.A_local
    next_state[:done] = patch.done
    return next_state
end

function hybrid_cell_object(
    name::Symbol;
    rd_params::RDParameters=RDParameters(),
    rd_config::RDChainConfig=RDChainConfig(n_cells=1),
    wave_config::WaveConfig=WaveConfig(),
)
    rd_cell = _rd_cell_object(rd_params, rd_config, name)
    wave_cell = _wave_cell_object(wave_config, name)
    schemas = Dict(
        :rd => rd_cell.port_schemas[:rd],
        :wave => wave_cell.port_schemas[:wave],
        :done => PortSchema(Symbol[], [:peak_count]),
    )
    return PolynomialObject(
        name,
        [:rd, :wave, :done],
        schemas,
        () -> begin
            rd_state = rd_cell.initial_state()
            wave_state = wave_cell.initial_state()
            return HybridCellState(:rd, rd_state, wave_state, 0.0)
        end,
        (state) -> begin
            haskey(state, :mode) || error("hybrid cell state must include :mode")
            mode = state[:mode]
            if mode == :rd
                return rd_cell.readout(state)
            elseif mode == :wave
                return wave_cell.readout(state)
            elseif mode == :done
                return Dict(:peak_count => Float64(get(state, :peak_count, 0.0)))
            end
            error("unsupported mode $(mode)")
        end,
        (state, incoming) -> begin
            haskey(state, :mode) || error("hybrid cell state must include :mode")
            mode = state[:mode]
            if mode == :rd
                return _merge_state(state, rd_cell.update(state, incoming))
            elseif mode == :wave
                return _merge_state(state, wave_cell.update(state, incoming))
            elseif mode == :done
                next_state = copy(state)
                next_state[:peak_count] = Float64(get(incoming, :peak_count, get(state, :peak_count, 0.0)))
                return next_state
            end
            error("unsupported mode $(mode)")
        end,
    )
end

const SOURCE_CELL_RADIUS = 5.0e-6
const SOURCE_GJ_LENGTH = 15.0e-9

_source_field_length(n_cells::Int) = 40.0 * n_cells / 200.0

function _source_gap_diffusion_unit(config::RDChainConfig)
    dx = config.field_length / config.n_cells
    return SOURCE_CELL_RADIUS * SOURCE_GJ_LENGTH / (3 * dx * dx)
end

function _source_gap_diffusions(params::RDParameters, config::RDChainConfig)
    unit = _source_gap_diffusion_unit(config)
    return (params.D_a * unit, params.D_i * unit)
end

Base.@kwdef mutable struct ClosedLoopConfig
    n_cells::Int = 100
    target_peaks::Int = 3
    min_iterations::Int = 9
    max_iterations::Int = 16
    seed::Int = 0
    source_bootstrap::Bool = true
    rd::RDParameters = RDParameters()
    rd_chain::RDChainConfig = RDChainConfig(n_cells=n_cells, field_length=_source_field_length(n_cells), seed=seed)
    wave::WaveConfig = WaveConfig()
end

struct CompiledClosedLoopMachine
    config::ClosedLoopConfig
    rd_program::CompiledPhase
    wave_clear_plan::CompiledWavePlan
    wave_grn_plan::CompiledWavePlan
    rd_routing::Tuple{Vector{Int},Vector{Int}}
    rd_wave_lens::DependentLens
    wave_ctrl_lens::DependentLens
end

struct HybridPhaseReport
    end_time::Float64
    steps::Int
    done::BitVector
end

struct ControllerTraceEntry
    iteration::Int
    loop_index::Int
    previous_peak_count::Float64
    wave_count::Float64
    n_peaks::Float64
    local_peak_count::Int
    D_a::Float64
    D_i::Float64
    source_D_a::Float64
    source_D_i::Float64
    shape::String
    controller_action::Symbol
    linear_spread_applied::Bool
    rd_pre_decay::Float64
    grn_pre_decay::Float64
    rd_duration::Float64
    grn_duration::Float64
    rd_A_profile::Vector{Float64}
    rd_I_profile::Vector{Float64}
    head_pre::Vector{Float64}
    active_pre_indices::Vector{Int}
    highest_pre_on::Union{Nothing,Int}
    seed_pre0l::Float64
    source_should_continue::Bool
    outputs
    incoming
    lens_wave_input::Union{Nothing,Dict{Symbol,Any}}
    lens_ctrl_input::Union{Nothing,Dict{Symbol,Any}}
    done::BitVector
    ctrl_peak_count::Float64
end

mutable struct ClosedLoopMachineState
    rd_state::Vector{Float64}
    wave_state::WaveExecutionState
    params::RDParameters
    history::Vector{ControllerTraceEntry}
    controller_action::Symbol
    last_wave::Union{Nothing,WaveResult}
end

struct ClosedLoopRun
    converged::Bool
    state::Vector{Float64}
    wave_state::WaveExecutionState
    history::Vector{ControllerTraceEntry}
    wave::Union{Nothing,WaveResult}
    params::RDParameters
end

struct RDPatternDemoResult
    n_cells::Int
    init_shape::String
    peak_count::Int
    shape::String
    A::Vector{Float64}
    I::Vector{Float64}
end

struct WaveCountDemoResult
    expected::Int
    count::Float64
    emitted::Vector{String}
end

_controller_fieldnames(::Type{T}) where {T} = fieldnames(T)

for T in (ControllerTraceEntry, ClosedLoopRun, RDPatternDemoResult, WaveCountDemoResult)
    @eval begin
        Base.haskey(value::$T, key::Symbol) = begin
            key in _controller_fieldnames($T) || return false
            if key === :lens_wave_input || key === :lens_ctrl_input
                return !isnothing(getfield(value, key))
            end
            return true
        end

        function Base.getindex(value::$T, key::Symbol)
            haskey(value, key) || error("$(string($T)) has no key $(key)")
            return getfield(value, key)
        end
    end
end

function _validate_closed_loop_config(config::ClosedLoopConfig)
    config.n_cells >= 1 || error("n_cells must be >= 1")
    config.target_peaks >= 0 || error("target_peaks must be >= 0")
    config.min_iterations >= 1 || error("min_iterations must be >= 1")
    config.max_iterations >= config.min_iterations || error("max_iterations must be >= min_iterations")
    config.rd_chain.n_cells == config.n_cells || error("ClosedLoopConfig n_cells must match rd_chain.n_cells")
    return config
end

function _wave_config_with(config::WaveConfig; kwargs...)
    base = (; (field => getfield(config, field) for field in fieldnames(WaveConfig))...)
    return WaveConfig(; base..., kwargs...)
end

function _wave_clear_config(config::ClosedLoopConfig)
    settle_time = config.rd_chain.tspan[2] - config.rd_chain.tspan[1]
    return _wave_config_with(
        config.wave;
        pre_decay=10.0,
        grn_settle_time_small=settle_time,
        grn_settle_time_large=settle_time,
    )
end

function _rd_profile_snapshot(state::Vector{Float64})
    n = length(state) ÷ 2
    return Dict(
        :A_profile => collect(@view state[1:n]),
        :I_profile => collect(@view state[n + 1:end]),
    )
end

function _adjust_controller!(state::Vector{Float64}, params::RDParameters, observed_peaks::Float64, target_peaks::Int)
    if observed_peaks > target_peaks
        params.D_a *= 1.21
        params.D_i = 30 * params.D_a
        return :increase
    end
    params.D_a /= 1.21
    params.D_i = 30 * params.D_a
    linear_spread!(state)
    return :decrease
end

function _apply_source_bootstrap!(state::Vector{Float64}, params::RDParameters)
    params.D_a /= 1.21
    params.D_i = 30 * params.D_a
    linear_spread!(state)
    return :decrease
end

function _phase_states(state::Vector{Float64})
    n = length(state) ÷ 2
    nodes = [Symbol("cell_$(idx)") for idx in 1:n]
    cells = [RDCellState(:rd, state[idx], state[n + idx]) for idx in 1:n]
    return PhaseState(nodes, cells)
end

_cell_index(node::Symbol) = parse(Int, split(String(node), "_")[end])

function _compiled_rd_routing(compiled::CompiledPhase)
    left = zeros(Int, length(compiled.program.wiring.nodes))
    right = zeros(Int, length(compiled.program.wiring.nodes))
    for route in compiled.routes
        dst_idx = _cell_index(route.dst_node)
        src_idx = _cell_index(route.src_node)
        if route.dst_port === :A_left || route.dst_port === :I_left
            left[dst_idx] == 0 || left[dst_idx] == src_idx || error("inconsistent RD left routing for $(route.dst_node)")
            left[dst_idx] = src_idx
        elseif route.dst_port === :A_right || route.dst_port === :I_right
            right[dst_idx] == 0 || right[dst_idx] == src_idx || error("inconsistent RD right routing for $(route.dst_node)")
            right[dst_idx] = src_idx
        end
    end
    return left, right
end

function _refresh_wave_input!(wave_state::WaveExecutionState, rd_state::Vector{Float64}, config::WaveConfig)
    n = length(wave_state.input_A)
    A = @view rd_state[1:n]
    normalize_profile!(wave_state.normalized_A, A)
    if config.normalize_input
        wave_state.input_A .= wave_state.normalized_A
    else
        wave_state.input_A .= A
    end
    return wave_state
end

struct HybridPhaseProblemData
    params::RDParameters
    rd_config::RDChainConfig
    rd_routing::Tuple{Vector{Int},Vector{Int}}
    wave_plan::CompiledWavePlan
    normalized_buffer::Vector{Float64}
end

function _pack_hybrid_state(state::ClosedLoopMachineState)
    return vcat(
        state.rd_state,
        vec(state.wave_state.pre),
        vec(state.wave_state.sig),
        state.wave_state.amdr,
    )
end

function _unpack_hybrid_state!(
    state::ClosedLoopMachineState,
    packed::AbstractVector{<:Real},
    wave_plan::CompiledWavePlan,
)
    n = wave_plan.plan.n_cells
    n_species = wave_plan.plan.n_species
    rd_len = 2 * n
    pre_len = n_species * n
    sig_len = pre_len

    state.rd_state .= @view packed[1:rd_len]
    state.wave_state.pre .= reshape(@view(packed[(rd_len + 1):(rd_len + pre_len)]), n_species, n)
    state.wave_state.sig .= reshape(
        @view(packed[(rd_len + pre_len + 1):(rd_len + pre_len + sig_len)]),
        n_species,
        n,
    )
    state.wave_state.amdr .= @view packed[(rd_len + pre_len + sig_len + 1):end]
    _refresh_wave_input!(state.wave_state, state.rd_state, wave_plan.plan.config)
    return state
end

function _hybrid_rhs!(du, u, problem::HybridPhaseProblemData, t)
    n = problem.rd_config.n_cells
    n_species = problem.wave_plan.plan.n_species
    rd_len = 2 * n
    pre_len = n_species * n
    sig_len = pre_len

    A = @view u[1:n]
    I = @view u[(n + 1):rd_len]
    dA = @view du[1:n]
    dI = @view du[(n + 1):rd_len]
    _rd_derivative!(dA, dI, A, I, problem.params, problem.rd_config, problem.rd_routing)

    pre = reshape(@view(u[(rd_len + 1):(rd_len + pre_len)]), n_species, n)
    sig = reshape(@view(u[(rd_len + pre_len + 1):(rd_len + pre_len + sig_len)]), n_species, n)
    amdr = @view u[(rd_len + pre_len + sig_len + 1):end]
    du_pre = reshape(@view(du[(rd_len + 1):(rd_len + pre_len)]), n_species, n)
    du_sig = reshape(@view(du[(rd_len + pre_len + 1):(rd_len + pre_len + sig_len)]), n_species, n)
    du_amdr = @view du[(rd_len + pre_len + sig_len + 1):end]

    wave_A = if problem.wave_plan.plan.config.normalize_input
        normalize_profile!(problem.normalized_buffer, A)
    else
        A
    end
    _wave_derivative!(
        du_amdr,
        du_pre,
        du_sig,
        amdr,
        pre,
        sig,
        wave_A,
        problem.wave_plan.plan.config,
        problem.wave_plan.plan.routing,
    )
    return nothing
end

function _update_wave_done!(
    wave_state::WaveExecutionState,
    du_amdr::Vector{Float64},
    du_pre::Matrix{Float64},
    du_sig::Matrix{Float64},
    dt::Float64,
    tol::Float64,
)
    for cell in eachindex(wave_state.done)
        cell_delta = abs(dt * du_amdr[cell])
        for species in axes(du_pre, 1)
            cell_delta = max(cell_delta, abs(dt * du_pre[species, cell]), abs(dt * du_sig[species, cell]))
        end
        wave_state.done[cell] = cell_delta <= tol
    end
    return wave_state.done
end

function _run_hybrid_phase!(
    machine::CompiledClosedLoopMachine,
    state::ClosedLoopMachineState,
    wave_plan::CompiledWavePlan,
)
    duration = wave_plan.plan.n_steps * wave_plan.plan.config.integration_dt
    problem = ODEProblem(
        _hybrid_rhs!,
        _pack_hybrid_state(state),
        (0.0, duration),
        HybridPhaseProblemData(
            state.params,
            machine.config.rd_chain,
            machine.rd_routing,
            wave_plan,
            similar(state.wave_state.normalized_A),
        ),
    )
    solution = solve(
        problem,
        Rosenbrock23(autodiff=false);
        save_everystep=false,
        save_start=false,
        save_end=true,
        dense=false,
        abstol=1.0e-6,
        reltol=1.0e-6,
        maxiters=10_000_000,
    )
    final_state = solution.u[end]
    _unpack_hybrid_state!(state, final_state, wave_plan)

    du = similar(final_state)
    _hybrid_rhs!(du, final_state, problem.p, solution.t[end])
    n = wave_plan.plan.n_cells
    n_species = wave_plan.plan.n_species
    rd_len = 2 * n
    pre_len = n_species * n
    sig_len = pre_len
    du_amdr = collect(@view(du[(rd_len + pre_len + sig_len + 1):end]))
    du_pre = reshape(copy(@view(du[(rd_len + 1):(rd_len + pre_len)])), n_species, n)
    du_sig = reshape(copy(@view(du[(rd_len + pre_len + 1):(rd_len + pre_len + sig_len)])), n_species, n)
    _update_wave_done!(state.wave_state, du_amdr, du_pre, du_sig, 1.0, wave_plan.plan.config.steady_tol)
    return HybridPhaseReport(solution.t[end], solution.stats.nf, copy(state.wave_state.done))
end

function compile_closed_loop_machine(config::ClosedLoopConfig)
    config = _validate_closed_loop_config(config)
    n = config.n_cells
    rd_program = compile_phase(rd_phase_program(config.rd, config.rd_chain))
    return CompiledClosedLoopMachine(
        config,
        rd_program,
        compile_wave_plan(_wave_clear_config(config), n),
        compile_wave_plan(config.wave, n),
        _compiled_rd_routing(rd_program),
        rd_to_wave_lens(n; normalize=config.wave.normalize_input),
        wave_to_ctrl_lens(n),
    )
end

function _initialize_closed_loop_state(machine::CompiledClosedLoopMachine)
    rd_state = make_rd_state(machine.config.rd_chain; rng_seed=machine.config.seed)
    params = deepcopy(machine.config.rd)
    controller_action = machine.config.source_bootstrap ? _apply_source_bootstrap!(rd_state, params) : :none
    wave_state = make_wave_state(machine.wave_grn_plan.plan, @view rd_state[1:machine.config.n_cells])
    return ClosedLoopMachineState(rd_state, wave_state, params, ControllerTraceEntry[], controller_action, nothing)
end

function _controller_history_entry(
    iteration::Int,
    machine::CompiledClosedLoopMachine,
    state::ClosedLoopMachineState,
    rd_outputs,
    rd_incoming,
    rd_phase,
    grn_phase,
    wave,
    ctrl_count::Float64;
    wave_input=nothing,
    ctrl_input=nothing,
)
    A = @view state.rd_state[1:(length(state.rd_state) ÷ 2)]
    I = @view state.rd_state[(length(state.rd_state) ÷ 2 + 1):end]
    previous_peak_count = iteration == 1 ? 0.0 : state.history[end].ctrl_peak_count
    head_pre = collect(@view state.wave_state.pre[:, end])
    active_pre_indices = findall(>(machine.config.wave.on_threshold), head_pre)
    highest_pre_on = isempty(active_pre_indices) ? nothing : last(active_pre_indices) - 1
    source_D_a, source_D_i = _source_gap_diffusions(state.params, machine.config.rd_chain)
    return ControllerTraceEntry(
        iteration,
        iteration - 1,
        previous_peak_count,
        wave.count,
        ctrl_count,
        peak_count(A),
        state.params.D_a,
        state.params.D_i,
        source_D_a,
        source_D_i,
        shape_string(A),
        state.controller_action,
        state.controller_action == :decrease,
        machine.wave_clear_plan.plan.config.pre_decay,
        machine.wave_grn_plan.plan.config.pre_decay,
        rd_phase.end_time,
        grn_phase.end_time,
        collect(A),
        collect(I),
        head_pre,
        Int[idx - 1 for idx in active_pre_indices],
        highest_pre_on,
        1.0,
        !isapprox(ctrl_count, machine.config.target_peaks; atol=1.0e-9) || iteration <= 8,
        rd_outputs,
        rd_incoming,
        wave_input,
        ctrl_input,
        copy(state.wave_state.done),
        ctrl_count,
    )
end

function _run_rd_iteration!(
    machine::CompiledClosedLoopMachine,
    state::ClosedLoopMachineState,
)
    preseed_lxh!(state.rd_state)
    rd_phase = _run_hybrid_phase!(machine, state, machine.wave_clear_plan)
    phase_states = _phase_states(state.rd_state)
    _, outputs, incoming = execute_phase(machine.rd_program, phase_states)
    return rd_phase, outputs, incoming
end

function _run_wave_iteration(machine::CompiledClosedLoopMachine, state::ClosedLoopMachineState)
    seed_wave_source!(state.wave_state; source_pre=1.0)
    grn_phase = _run_hybrid_phase!(machine, state, machine.wave_grn_plan)
    wave_input = machine.rd_wave_lens.forward(_rd_profile_snapshot(state.rd_state))
    wave = wave_result(state.wave_state, machine.config.wave)
    ctrl_input = machine.wave_ctrl_lens.forward(wave_phase_outputs(wave))
    return grn_phase, wave, wave_input, ctrl_input
end

function run_closed_loop_machine(machine::CompiledClosedLoopMachine; stop_on_target::Bool=true)
    state = _initialize_closed_loop_state(machine)

    for iteration in 1:machine.config.max_iterations
        rd_phase, outputs, incoming = _run_rd_iteration!(machine, state)
        grn_phase, wave, wave_input, ctrl_input = _run_wave_iteration(machine, state)
        state.last_wave = wave
        entry = _controller_history_entry(
            iteration,
            machine,
            state,
            outputs,
            incoming,
            rd_phase,
            grn_phase,
            wave,
            ctrl_input[:peak_count];
            wave_input=wave_input,
            ctrl_input=ctrl_input,
        )
        push!(state.history, entry)
        if stop_on_target &&
           iteration >= machine.config.min_iterations &&
           isapprox(ctrl_input[:peak_count], machine.config.target_peaks; atol=1.0e-9)
            return ClosedLoopRun(
                true,
                copy(state.rd_state),
                copy(state.wave_state),
                copy(state.history),
                wave,
                deepcopy(state.params),
            )
        end
        state.controller_action = _adjust_controller!(
            state.rd_state,
            state.params,
            ctrl_input[:peak_count],
            machine.config.target_peaks,
        )
    end

    return ClosedLoopRun(
        false,
        copy(state.rd_state),
        copy(state.wave_state),
        copy(state.history),
        state.last_wave,
        deepcopy(state.params),
    )
end

function closed_loop(config::ClosedLoopConfig; stop_on_target::Bool=true)
    return run_closed_loop_machine(compile_closed_loop_machine(config); stop_on_target=stop_on_target)
end

function closed_loop_composed(config::ClosedLoopConfig; stop_on_target::Bool=true)
    return run_closed_loop_machine(compile_closed_loop_machine(config); stop_on_target=stop_on_target)
end

function rd_pattern_demo(; n_cells::Int=100, seed::Int=0)
    config = ClosedLoopConfig(n_cells=n_cells, seed=seed)
    state = zeros(2 * n_cells)
    spread_pattern!(state, "LH"; A_template=[0.0, 0.5, 1.0], I_template=nothing)
    settle_rd_composed!(state, config.rd, config.rd_chain)
    n = length(state) ÷ 2
    A = state[1:n]
    return RDPatternDemoResult(
        n_cells,
        "LH",
        peak_count(A),
        shape_string(A),
        collect(A),
        collect(state[n + 1:end]),
    )
end

function wave_count_demo(; peaks::Int=3, cells_per_peak::Int=12)
    A = Float64[]
    for _ in 1:(peaks - 1)
        append!(A, collect(range(0.0, 1.0; length=cells_per_peak + 1))[1:end-1])
        append!(A, collect(range(1.0, 0.0; length=cells_per_peak + 1)))
    end
    append!(A, collect(range(0.0, 1.0; length=cells_per_peak + 1)))
    result = wave_count(A)
    return WaveCountDemoResult(peaks, result.count, string.(result.emitted))
end

function closed_loop_demo(; n_cells::Int=100, target_peaks::Int=3, seed::Int=0)
    return closed_loop(ClosedLoopConfig(n_cells=n_cells, target_peaks=target_peaks, seed=seed))
end

end
