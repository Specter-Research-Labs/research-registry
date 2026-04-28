module RD

using OrdinaryDiffEq
using Random
using SciMLBase

using ..Algebra: AbstractCellState,
    PhaseProgram,
    PhaseState,
    PolynomialObject,
    PortSchema,
    WiringEdge,
    WiringSpec,
    compile_phase,
    execute_phase
export RDParameters,
    RDChainConfig,
    RDCellState,
    make_rd_state,
    spread_pattern!,
    linear_spread!,
    preseed_lxh!,
    direct_rd_step,
    settle_rd_source!,
    settle_rd!,
    settle_rd_composed!,
    settle_rd_via_catlab!,
    composed_rd_step,
    rd_phase_program,
    peak_count,
    shape_string

Base.@kwdef mutable struct RDParameters
    hill_n::Float64 = 10.0
    gen_a::Float64 = 1.0
    gen_i::Float64 = 4.0
    decay_a::Float64 = 1.0
    decay_i::Float64 = 2.0
    D_a::Float64 = 1.0
    D_i::Float64 = 30.0
end

mutable struct RDCellState <: AbstractCellState
    mode::Symbol
    A::Float64
    I::Float64
end

Base.copy(state::RDCellState) = RDCellState(state.mode, state.A, state.I)
Base.:(==)(left::RDCellState, right::RDCellState) = left.mode == right.mode && left.A == right.A && left.I == right.I
Base.haskey(state::RDCellState, key::Symbol) = key in (:mode, :A, :I)
Base.get(state::RDCellState, key::Symbol, default) = haskey(state, key) ? state[key] : default

function Base.getindex(state::RDCellState, key::Symbol)
    if key === :mode
        return state.mode
    elseif key === :A
        return state.A
    elseif key === :I
        return state.I
    end
    error("RDCellState has no key $(key)")
end

function Base.setindex!(state::RDCellState, value, key::Symbol)
    if key === :mode
        state.mode = Symbol(value)
    elseif key === :A
        state.A = Float64(value)
    elseif key === :I
        state.I = Float64(value)
    else
        error("RDCellState has no key $(key)")
    end
    return value
end

Base.@kwdef struct RDChainConfig
    n_cells::Int
    field_length::Float64 = 40.0
    tspan::Tuple{Float64,Float64} = (0.0, 300.0)
    seed::Int = 0
    steady_tol::Float64 = 1.0e-5
    cuts::Vector{Int} = Int[]
end

function _validate_rd_chain_config(config::RDChainConfig)
    config.n_cells >= 1 || error("n_cells must be >= 1")
    config.field_length > 0 || error("field_length must be > 0")
    config.steady_tol > 0 || error("steady_tol must be > 0")
    config.tspan[2] >= config.tspan[1] || error("tspan end must be >= tspan start")
    cuts = collect(sort(unique(config.cuts)))
    all(1 <= cut < config.n_cells for cut in cuts) || error("cuts must satisfy 1 <= cut < n_cells")
    return RDChainConfig(
        n_cells=config.n_cells,
        field_length=config.field_length,
        tspan=config.tspan,
        seed=config.seed,
        steady_tol=config.steady_tol,
        cuts=cuts,
    )
end

function _validate_rd_state(state::AbstractVector{<:Real}, config::RDChainConfig)
    expected_length = 2 * config.n_cells
    length(state) == expected_length || error("expected state length $expected_length for n_cells=$(config.n_cells)")
    return state
end

function make_rd_state(config::RDChainConfig; rng_seed::Int = config.seed)
    config = _validate_rd_chain_config(config)
    rng = MersenneTwister(rng_seed)
    A = collect(range(0.0, 1.0; length=config.n_cells))
    A .+= 0.002 .* randn(rng, config.n_cells)
    A = clamp.(A, 0.0, Inf)
    I = zeros(config.n_cells)
    return vcat(A, I)
end

const SOURCE_CC_INIT_A = Float64[
    0.0002, 0.0002, 0.0003, 0.0004, 0.0007, 0.0011, 0.0017, 0.0028, 0.0045, 0.0074,
    0.0120, 0.0196, 0.0320, 0.0523, 0.0856, 0.1401, 0.2292, 0.3723, 0.5317, 0.6119,
]
const SOURCE_CC_INIT_I = Float64[
    0.0841, 0.0855, 0.0883, 0.0926, 0.0984, 0.1059, 0.1151, 0.1263, 0.1395, 0.1551,
    0.1732, 0.1942, 0.2185, 0.2464, 0.2784, 0.3150, 0.3569, 0.4043, 0.4482, 0.4714,
]
const SIMPLE_LH_TEMPLATE_A = Float64[0.0, 0.5, 1.0]

function _interpolate_template(template::AbstractVector{<:Real}, coord::Float64)
    last_idx = length(template) - 1
    x = clamp(coord, 0.0, float(last_idx))
    lower = floor(Int, x)
    upper = ceil(Int, x)
    lower == upper && return Float64(template[lower + 1])
    weight = x - lower
    return (1 - weight) * Float64(template[lower + 1]) + weight * Float64(template[upper + 1])
end

function spread_pattern!(
    state::Vector{Float64},
    shape::AbstractString;
    A_template::AbstractVector{<:Real}=SOURCE_CC_INIT_A,
    I_template=SOURCE_CC_INIT_I,
)
    n = length(state) ÷ 2
    n >= 2 || error("spread_pattern! requires at least two cells")
    labels = collect(shape)
    length(labels) >= 2 || error("shape must contain at least two extrema")
    all(label in ('L', 'H') for label in labels) || error("shape must contain only 'L' and 'H'")
    all(labels[idx] != labels[idx + 1] for idx in 1:(length(labels) - 1)) || error("shape must alternate between 'L' and 'H'")
    length(A_template) >= 2 || error("A_template must contain at least two points")
    if I_template !== nothing
        length(I_template) == length(A_template) || error("I_template must match A_template length")
    end

    template_last = length(A_template) - 1
    indices = zeros(Float64, n)
    n_segments = length(labels) - 1
    for pos in 1:n_segments
        w0 = round(Int, (pos - 1) * (n - 1) / n_segments)
        w1 = round(Int, pos * (n - 1) / n_segments)
        seg = (labels[pos], labels[pos + 1])
        i0, i1 = if seg == ('L', 'H')
            (0.0, float(template_last))
        elseif seg == ('H', 'L')
            (float(template_last), 0.0)
        else
            error("shape must alternate between 'L' and 'H'")
        end
        indices[(w0 + 1):(w1 + 1)] .= range(i0, i1; length=w1 - w0 + 1)
    end

    for idx in eachindex(indices)
        state[idx] = _interpolate_template(A_template, indices[idx])
    end
    if I_template === nothing
        state[(n + 1):end] .= 0.0
    else
        for idx in eachindex(indices)
            state[n + idx] = _interpolate_template(I_template, indices[idx])
        end
    end
    return state
end

function linear_spread!(state::Vector{Float64})
    n = length(state) ÷ 2
    state[1:n] .= range(0.0, 1.0; length=n)
    state[n + 1:end] .= 0.0
    return state
end

function preseed_lxh!(state::Vector{Float64})
    n = length(state) ÷ 2
    state[1:min(2, n)] .= 0.0
    state[(n + 1):(n + min(2, n))] .= 0.0
    head_start = max(1, n - 1)
    state[head_start:n] .= 1.0
    state[(n + head_start):(2n)] .= 1.0
    return state
end

function _laplacian(values::AbstractVector{<:Real}, dx::Float64)
    n = length(values)
    T = promote_type(eltype(values), Float64)
    result = Vector{T}(undef, n)
    if n == 1
        result[1] = zero(T)
        return result
    end
    for i in 1:n
        left = i == 1 ? values[2] : values[i - 1]
        right = i == n ? values[n - 1] : values[i + 1]
        result[i] = (left + right - 2 * values[i]) / (dx * dx)
    end
    return result
end

function direct_rd_step(state::AbstractVector{<:Real}, params::RDParameters)
    return direct_rd_step(state, params, RDChainConfig(n_cells=length(state) ÷ 2))
end

function direct_rd_step(
    state::AbstractVector{<:Real},
    params::RDParameters,
    config::RDChainConfig,
)
    config = _validate_rd_chain_config(config)
    _validate_rd_state(state, config)
    n = length(state) ÷ 2
    A = @view state[1:n]
    I = @view state[n + 1:end]
    dx = config.field_length / n
    ratio = (I ./ (A .+ 1.0e-20)) .^ params.hill_n
    gen = 1.0 ./ (1.0 .+ ratio)
    dA = params.gen_a .* gen .- params.decay_a .* A .+ params.D_a .* _laplacian(A, dx)
    dI = params.gen_i .* gen .- params.decay_i .* I .+ params.D_i .* _laplacian(I, dx)
    return vcat(dA, dI)
end

function _rd_cell_object(params::RDParameters, config::RDChainConfig, node::Symbol)
    config = _validate_rd_chain_config(config)
    schema = PortSchema([:A_left, :A_right, :I_left, :I_right], [:A_out, :I_out])
    return PolynomialObject(
        node,
        [:rd],
        Dict(:rd => schema),
        () -> RDCellState(:rd, 0.0, 0.0),
        (state) -> begin
            haskey(state, :mode) || error("RD cell state must include :mode")
            mode = state[:mode]
            mode == :rd || error("unsupported RD cell mode $(mode)")
            return Dict(:A_out => state[:A], :I_out => state[:I])
        end,
        (state, incoming) -> begin
            haskey(state, :mode) || error("RD cell state must include :mode")
            mode = state[:mode]
            mode == :rd || error("unsupported RD cell mode $(mode)")
            left_a = get(incoming, :A_left, state[:A])
            right_a = get(incoming, :A_right, state[:A])
            left_i = get(incoming, :I_left, state[:I])
            right_i = get(incoming, :I_right, state[:I])
            dx = config.field_length / config.n_cells
            ratio = (state[:I] / (state[:A] + 1.0e-20)) ^ params.hill_n
            gen = 1.0 / (1.0 + ratio)
            lap_a = (left_a + right_a - 2 * state[:A]) / (dx * dx)
            lap_i = (left_i + right_i - 2 * state[:I]) / (dx * dx)
            return RDCellState(
                mode,
                params.gen_a * gen - params.decay_a * state[:A] + params.D_a * lap_a,
                params.gen_i * gen - params.decay_i * state[:I] + params.D_i * lap_i,
            )
        end,
    )
end

function rd_phase_program(params::RDParameters, config::RDChainConfig)
    config = _validate_rd_chain_config(config)
    nodes = [Symbol("cell_$(idx)") for idx in 1:config.n_cells]
    objects = Dict(node => _rd_cell_object(params, config, node) for node in nodes)
    edges = WiringEdge[]
    cut_set = Set(config.cuts)
    for idx in eachindex(nodes)
        node = nodes[idx]
        if idx > 1 && (idx - 1) ∉ cut_set
            push!(edges, WiringEdge(nodes[idx - 1], :A_out, node, :A_left))
            push!(edges, WiringEdge(nodes[idx - 1], :I_out, node, :I_left))
        end
        if idx < length(nodes) && idx ∉ cut_set
            push!(edges, WiringEdge(nodes[idx + 1], :A_out, node, :A_right))
            push!(edges, WiringEdge(nodes[idx + 1], :I_out, node, :I_right))
        end
    end
    return PhaseProgram(:rd_tissue, :rd, objects, WiringSpec(nodes, edges))
end

function _rd_neighbor_indices(config::RDChainConfig)
    config = _validate_rd_chain_config(config)
    n = config.n_cells
    left = zeros(Int, n)
    right = zeros(Int, n)
    for idx in 1:n
        idx > 1 && (left[idx] = idx - 1)
        idx < n && (right[idx] = idx + 1)
    end
    for cut in config.cuts
        right[cut] = 0
        left[cut + 1] = 0
    end
    return left, right
end

function _rd_derivative!(
    dA::AbstractVector,
    dI::AbstractVector,
    A::AbstractVector{<:Real},
    I::AbstractVector{<:Real},
    params::RDParameters,
    config::RDChainConfig,
    routing::Tuple{Vector{Int},Vector{Int}}=_rd_neighbor_indices(config),
)
    config = _validate_rd_chain_config(config)
    n = config.n_cells
    length(A) == n || error("A length must match config.n_cells")
    length(I) == n || error("I length must match config.n_cells")
    length(dA) == n || error("dA length must match config.n_cells")
    length(dI) == n || error("dI length must match config.n_cells")

    left, right = routing
    dx = config.field_length / n
    for idx in 1:n
        left_idx = left[idx] == 0 ? idx : left[idx]
        right_idx = right[idx] == 0 ? idx : right[idx]
        ratio = (I[idx] / (A[idx] + 1.0e-20)) ^ params.hill_n
        gen = 1.0 / (1.0 + ratio)
        lap_a = (A[left_idx] + A[right_idx] - 2 * A[idx]) / (dx * dx)
        lap_i = (I[left_idx] + I[right_idx] - 2 * I[idx]) / (dx * dx)
        dA[idx] = params.gen_a * gen - params.decay_a * A[idx] + params.D_a * lap_a
        dI[idx] = params.gen_i * gen - params.decay_i * I[idx] + params.D_i * lap_i
    end
    return nothing
end

function composed_rd_step(
    state::AbstractVector{<:Real},
    params::RDParameters,
    config::RDChainConfig,
)
    config = _validate_rd_chain_config(config)
    _validate_rd_state(state, config)
    left, right = _rd_neighbor_indices(config)
    n = config.n_cells
    A = @view state[1:n]
    I = @view state[n + 1:end]
    deriv = zeros(Float64, length(state))
    _rd_derivative!(@view(deriv[1:n]), @view(deriv[n + 1:end]), A, I, params, config, (left, right))
    return deriv
end

function _rd_phase_states(state::AbstractVector{<:Real}, n_cells::Int)
    nodes = [Symbol("cell_$(idx)") for idx in 1:n_cells]
    cells = [RDCellState(:rd, state[idx], state[n_cells + idx]) for idx in 1:n_cells]
    return PhaseState(nodes, cells)
end

function _rd_rhs!(du, u, params, t)
    rd_params, rd_config = params
    du .= direct_rd_step(u, rd_params, rd_config)
    return nothing
end

function _rd_composed_rhs!(du, u, params, t)
    rd_params, rd_config, routing = params
    n = rd_config.n_cells
    A = @view u[1:n]
    I = @view u[n + 1:end]
    _rd_derivative!(@view(du[1:n]), @view(du[n + 1:end]), A, I, rd_params, rd_config, routing)
    return nothing
end

function _rd_catlab_rhs!(du, u, params, t)
    compiled, n_cells = params
    states = _rd_phase_states(u, n_cells)
    next_states, _, _ = execute_phase(compiled, states)
    for idx in 1:n_cells
        cell = Symbol("cell_$(idx)")
        du[idx] = next_states[cell][:A]
        du[n_cells + idx] = next_states[cell][:I]
    end
    return nothing
end

function _source_explicit_dt(
    state::AbstractVector{<:Real},
    deriv::AbstractVector{<:Real},
    base_dt::Float64,
    max_delta_cc::Float64,
)
    max_t_cc = Inf
    for idx in eachindex(state)
        slope = deriv[idx]
        if slope != 0.0
            ratio = abs(state[idx] / slope)
            ratio < max_t_cc && (max_t_cc = ratio)
        end
    end
    if !isfinite(max_t_cc)
        return base_dt
    end
    n_steps = max(1, floor(Int, max_delta_cc * max_t_cc / base_dt))
    return n_steps * base_dt
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

function _solve_rd_problem(problem, config::RDChainConfig; steady_stop::Bool=true)
    callback = steady_stop ? _steady_state_callback(problem.u0, config.steady_tol) : nothing
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
        # The source model uses explicit adaptive integration. Some source-scaled
        # closed-loop cases need many internal steps before reaching the steady-state
        # callback, so raise SciML's default cap rather than terminating early.
        maxiters=10_000_000,
    )
    copyto!(problem.u0, solution.u[end])
    return solution
end

function settle_rd_source!(
    state::Vector{Float64},
    params::RDParameters,
    config::RDChainConfig;
    tspan::Tuple{Float64,Float64}=config.tspan,
    steady_stop::Bool=false,
    base_dt::Float64=0.0002,
    max_delta_cc::Float64=0.001,
)
    config = _validate_rd_chain_config(config)
    _validate_rd_state(state, config)
    base_dt > 0 || error("base_dt must be > 0")
    max_delta_cc > 0 || error("max_delta_cc must be > 0")

    deriv = similar(state)
    t = float(tspan[1])
    t_end = float(tspan[2])
    steps = 0
    steady_reached = false

    while t < t_end
        deriv .= composed_rd_step(state, params, config)
        if steady_stop && maximum(abs, deriv) <= config.steady_tol
            steady_reached = true
            break
        end
        dt = _source_explicit_dt(state, deriv, base_dt, max_delta_cc)
        if t + dt > t_end
            dt = t_end - t
        end
        @inbounds @simd for idx in eachindex(state)
            state[idx] += deriv[idx] * dt
        end
        t += dt
        steps += 1
    end

    return (end_time=t, steps=steps, steady_reached=steady_reached)
end

function settle_rd!(
    state::Vector{Float64},
    params::RDParameters,
    config::RDChainConfig;
    tspan::Tuple{Float64,Float64}=config.tspan,
    steady_stop::Bool=true,
)
    config = _validate_rd_chain_config(config)
    _validate_rd_state(state, config)
    problem = ODEProblem(_rd_rhs!, state, tspan, (params, config))
    return _solve_rd_problem(problem, config; steady_stop=steady_stop)
end

function settle_rd_composed!(
    state::Vector{Float64},
    params::RDParameters,
    config::RDChainConfig;
    tspan::Tuple{Float64,Float64}=config.tspan,
    steady_stop::Bool=true,
)
    config = _validate_rd_chain_config(config)
    _validate_rd_state(state, config)
    routing = _rd_neighbor_indices(config)
    problem = ODEProblem(_rd_composed_rhs!, state, tspan, (params, config, routing))
    return _solve_rd_problem(problem, config; steady_stop=steady_stop)
end

function settle_rd_via_catlab!(
    state::Vector{Float64},
    params::RDParameters,
    config::RDChainConfig;
    tspan::Tuple{Float64,Float64}=config.tspan,
    steady_stop::Bool=true,
)
    config = _validate_rd_chain_config(config)
    _validate_rd_state(state, config)
    compiled = compile_phase(rd_phase_program(params, config))
    problem = ODEProblem(_rd_catlab_rhs!, state, tspan, (compiled, config.n_cells))
    return _solve_rd_problem(problem, config; steady_stop=steady_stop)
end

function shape_string(A::AbstractVector{<:Real}; delta::Float64=0.02)
    isempty(A) && return ""
    shape = IOBuffer()
    mode = :unset
    a_min = A[1]
    a_max = A[1]
    for idx in 2:length(A)
        value = A[idx]
        if mode == :rising && value < a_max - delta
            mode = :falling
            print(shape, 'L')
            a_min = value
            a_max = value
        elseif mode == :falling && value > a_min + delta
            mode = :rising
            print(shape, 'H')
            a_min = value
            a_max = value
        elseif mode == :unset && value > a_min + delta
            mode = :rising
            print(shape, "LH")
            a_min = value
            a_max = value
        elseif mode == :unset && value < a_max - delta
            mode = :falling
            print(shape, "HL")
            a_min = value
            a_max = value
        end
        a_min = min(a_min, value)
        a_max = max(a_max, value)
    end
    return String(take!(shape))
end

function peak_count(A::AbstractVector{<:Real}; threshold::Float64=0.02)
    return count(==('H'), shape_string(A; delta=threshold))
end

end
