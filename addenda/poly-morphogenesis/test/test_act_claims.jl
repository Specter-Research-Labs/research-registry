using PolyMorphogenesis
using Test

const PMAlgebra = PolyMorphogenesis.Algebra
const PMRD = PolyMorphogenesis.RD
const PMWave = PolyMorphogenesis.Wave
const PhaseProgram = PMAlgebra.PhaseProgram
const WiringEdge = PMAlgebra.WiringEdge
const WiringSpec = PMAlgebra.WiringSpec
const compile_phase = PMAlgebra.compile_phase
const execute_phase = PMAlgebra.execute_phase
const compile_wave_plan = PMWave.compile_wave_plan
const rd_phase_program = PMRD.rd_phase_program

function _program_components(program::PhaseProgram)
    adjacency = Dict(node => Set{Symbol}() for node in program.wiring.nodes)
    for edge in program.wiring.edges
        push!(adjacency[edge.src_node], edge.dst_node)
        push!(adjacency[edge.dst_node], edge.src_node)
    end

    visited = Set{Symbol}()
    components = Vector{Vector{Symbol}}()
    for node in program.wiring.nodes
        node in visited && continue
        stack = [node]
        component = Symbol[]
        while !isempty(stack)
            current = pop!(stack)
            current in visited && continue
            push!(visited, current)
            push!(component, current)
            append!(stack, collect(setdiff(adjacency[current], visited)))
        end
        sort!(component; by=_cell_index)
        push!(components, component)
    end

    sort!(components; by=comp -> _cell_index(first(comp)))
    return components
end

function _cell_index(node::Symbol)
    return parse(Int, split(String(node), "_")[end])
end

function _segment_ranges(n_cells::Int, cuts::Vector{Int})
    ranges = UnitRange{Int}[]
    start_idx = 1
    for cut in sort(unique(cuts))
        push!(ranges, start_idx:cut)
        start_idx = cut + 1
    end
    push!(ranges, start_idx:n_cells)
    return ranges
end

function _segmented_rd_derivative(state::Vector{Float64}, params::RDParameters, config::RDChainConfig)
    n = config.n_cells
    deriv = zeros(Float64, length(state))
    for range in _segment_ranges(n, config.cuts)
        idxs = collect(range)
        seg_length = length(range)
        seg_state = vcat(state[idxs], state[n .+ idxs])
        seg_config = RDChainConfig(
            n_cells=seg_length,
            field_length=config.field_length * seg_length / n,
            tspan=config.tspan,
            seed=config.seed,
            steady_tol=config.steady_tol,
        )
        seg_deriv = PMRD.composed_rd_step(seg_state, params, seg_config)
        deriv[idxs] .= seg_deriv[1:seg_length]
        deriv[n .+ idxs] .= seg_deriv[(seg_length + 1):end]
    end
    return deriv
end

function _rd_states(n_cells::Int; left_value::Float64=0.2, right_value::Float64=0.8, split::Int=n_cells ÷ 2)
    states = Dict{Symbol,Any}()
    for idx in 1:n_cells
        value = idx <= split ? left_value : right_value
        states[Symbol("cell_$(idx)")] = Dict(:mode => :rd, :A => value, :I => value / 2)
    end
    return states
end

function _rename_program(program::PhaseProgram, prefix::Symbol)
    renamed = Dict(node => Symbol("$(prefix)_$(node)") for node in program.wiring.nodes)
    objects = Dict(renamed[node] => program.objects[node] for node in program.wiring.nodes)
    edges = [
        WiringEdge(renamed[edge.src_node], edge.src_port, renamed[edge.dst_node], edge.dst_port)
        for edge in program.wiring.edges
    ]
    return PhaseProgram(
        Symbol("$(prefix)_$(program.name)"),
        program.mode,
        objects,
        WiringSpec([renamed[node] for node in program.wiring.nodes], edges),
    )
end

function _rename_states(states::Dict{Symbol,Any}, prefix::Symbol)
    return Dict(Symbol("$(prefix)_$(node)") => state for (node, state) in states)
end

function _merge_programs(left::PhaseProgram, right::PhaseProgram, name::Symbol)
    return PhaseProgram(
        name,
        left.mode,
        merge(copy(left.objects), right.objects),
        WiringSpec(vcat(left.wiring.nodes, right.wiring.nodes), vcat(left.wiring.edges, right.wiring.edges)),
    )
end

function _state_dicts_approx_equal(left::Dict{Symbol,Any}, right::Dict{Symbol,Any}; atol::Float64=1.0e-12)
    keys(left) == keys(right) || return false
    for key in keys(left)
        left_value = left[key]
        right_value = right[key]
        if left_value isa PMRD.RDCellState && right_value isa PMRD.RDCellState
            left_value.mode == right_value.mode || return false
            isapprox(left_value.A, right_value.A; atol=atol, rtol=0.0) || return false
            isapprox(left_value.I, right_value.I; atol=atol, rtol=0.0) || return false
        else
            left_value == right_value || return false
        end
    end
    return true
end

function _wave_states(compiled_plan::PMWave.CompiledWavePlan)
    states = Dict{Symbol,Any}()
    species_axis = Float64.(collect(1:compiled_plan.plan.n_species))
    for (idx, node) in enumerate(compiled_plan.nodes)
        state = compiled_plan.program.objects[node].initial_state()
        state[:A_local] = 0.1 * idx
        state[:amdr] = 0.05 * idx
        state[:pre] .= 0.01 * idx .* species_axis
        state[:sig] .= 0.02 * idx .* species_axis
        states[node] = state
    end
    return states
end

@testset "severed RD wiring decomposes into fragment components" begin
    config = RDChainConfig(n_cells=10, cuts=[3, 7])
    program = rd_phase_program(RDParameters(), config)
    components = sort(_program_components(program); by=first)
    @test components == [
        [:cell_1, :cell_2, :cell_3],
        [:cell_4, :cell_5, :cell_6, :cell_7],
        [:cell_8, :cell_9, :cell_10],
    ]
end

@testset "multi-cut RD step factors over contiguous fragments" begin
    config = RDChainConfig(n_cells=10, field_length=40.0, cuts=[3, 8])
    params = RDParameters(D_a=0.7, D_i=21.0)
    state = vcat(collect(range(0.1, 0.9; length=10)), collect(range(0.6, 0.15; length=10)))

    @test PMRD.composed_rd_step(state, params, config) ≈ _segmented_rd_derivative(state, params, config) atol=1.0e-12
end

@testset "severed RD compilation preserves one-step fragment independence" begin
    config = RDChainConfig(n_cells=8, cuts=[4])
    compiled = compile_phase(rd_phase_program(RDParameters(), config))

    left_fixed = _rd_states(8; left_value=0.2, right_value=0.8, split=4)
    right_perturbed = _rd_states(8; left_value=0.2, right_value=1.4, split=4)

    next_left_fixed, _, _ = execute_phase(compiled, left_fixed)
    next_right_perturbed, _, _ = execute_phase(compiled, right_perturbed)

    for idx in 1:4
        cell = Symbol("cell_$(idx)")
        @test next_left_fixed[cell][:A] == next_right_perturbed[cell][:A]
        @test next_left_fixed[cell][:I] == next_right_perturbed[cell][:I]
    end
end

@testset "compiled routing matches wiring spec for RD and wave programs" begin
    rd_program = rd_phase_program(RDParameters(), RDChainConfig(n_cells=7, cuts=[3, 5]))
    rd_compiled = compile_phase(rd_program)
    rd_states = _rd_states(7; left_value=0.2, right_value=0.9, split=3)
    _, rd_outputs, rd_incoming = execute_phase(rd_compiled, rd_states)
    @test rd_incoming == PMAlgebra.routing_inputs(rd_program, rd_outputs)

    wave_compiled = compile_wave_plan(WaveConfig(n_peaks_max=2), 4)
    wave_states = _wave_states(wave_compiled)
    _, wave_outputs, wave_incoming = execute_phase(wave_compiled.compiled, wave_states)
    @test wave_incoming == PMAlgebra.routing_inputs(wave_compiled.program, wave_outputs)
end

@testset "diagram wire counts encode severing laws" begin
    rd_config = RDChainConfig(n_cells=10, cuts=[3, 7])
    rd_program = rd_phase_program(RDParameters(), rd_config)
    rd_compiled = compile_phase(rd_program)
    @test PMAlgebra.diagram_wire_count(rd_compiled) == 4 * ((rd_config.n_cells - 1) - length(rd_config.cuts))

    for edge in rd_program.wiring.edges
        src = _cell_index(edge.src_node)
        dst = _cell_index(edge.dst_node)
        @test abs(src - dst) == 1
        @test !(min(src, dst) in rd_config.cuts && max(src, dst) == min(src, dst) + 1)
    end

    wave_config = WaveConfig(n_peaks_max=3)
    wave_compiled = compile_wave_plan(wave_config, 5)
    @test PMAlgebra.diagram_wire_count(wave_compiled.compiled) == 4 * wave_config.n_peaks_max * (wave_compiled.plan.n_cells - 1)
end

@testset "compile and execute are additive on disconnected unions" begin
    left_program = _rename_program(rd_phase_program(RDParameters(), RDChainConfig(n_cells=3)), :left)
    right_program = _rename_program(rd_phase_program(RDParameters(), RDChainConfig(n_cells=2)), :right)
    union_program = _merge_programs(left_program, right_program, :rd_union)

    left_states = _rename_states(_rd_states(3; left_value=0.2, right_value=0.5, split=2), :left)
    right_states = _rename_states(_rd_states(2; left_value=0.8, right_value=1.1, split=1), :right)
    union_states = merge(copy(left_states), right_states)

    compiled_union = compile_phase(union_program)
    next_union, outputs_union, incoming_union = execute_phase(compiled_union, union_states)

    compiled_left = compile_phase(left_program)
    next_left, outputs_left, incoming_left = execute_phase(compiled_left, left_states)

    compiled_right = compile_phase(right_program)
    next_right, outputs_right, incoming_right = execute_phase(compiled_right, right_states)

    @test outputs_union == merge(copy(outputs_left), outputs_right)
    @test incoming_union == merge(copy(incoming_left), incoming_right)
    @test _state_dicts_approx_equal(next_union, merge(copy(next_left), next_right))
    @test PMAlgebra.diagram_box_count(compiled_union) == PMAlgebra.diagram_box_count(compiled_left) + PMAlgebra.diagram_box_count(compiled_right)
    @test PMAlgebra.diagram_wire_count(compiled_union) == PMAlgebra.diagram_wire_count(compiled_left) + PMAlgebra.diagram_wire_count(compiled_right)
end

@testset "severed compiled wire count is additive over fragments" begin
    full = compile_phase(rd_phase_program(RDParameters(), RDChainConfig(n_cells=8, cuts=[4])))
    left = compile_phase(rd_phase_program(RDParameters(), RDChainConfig(n_cells=4)))
    right = compile_phase(rd_phase_program(RDParameters(), RDChainConfig(n_cells=4)))

    @test PMAlgebra.diagram_box_count(full) == PMAlgebra.diagram_box_count(left) + PMAlgebra.diagram_box_count(right)
    @test PMAlgebra.diagram_wire_count(full) == PMAlgebra.diagram_wire_count(left) + PMAlgebra.diagram_wire_count(right)
end
