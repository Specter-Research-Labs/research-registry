module Algebra

using Catlab.WiringDiagrams
using AlgebraicDynamics

export PortSchema,
    AbstractCellState,
    PhaseState,
    PolynomialObject,
    DependentLens,
    LaxMonoidalFunctor,
    Laxator,
    WiringEdge,
    WiringSpec,
    PhaseProgram,
    identity_lens,
    compose_lenses,
    normalize_profile,
    normalize_profile!,
    CompiledPhase,
    compile_phase,
    execute_phase,
    routing_inputs,
    diagram_box_count,
    diagram_wire_count,
    rd_to_wave_lens,
    wave_to_ctrl_lens

struct PortSchema
    inputs::Vector{Symbol}
    outputs::Vector{Symbol}
end

abstract type AbstractCellState end

struct PhaseState{S<:AbstractCellState}
    nodes::Vector{Symbol}
    index::Dict{Symbol,Int}
    cells::Vector{S}
end

function PhaseState(nodes::Vector{Symbol}, cells::Vector{S}) where {S<:AbstractCellState}
    length(nodes) == length(cells) || error("PhaseState nodes and cells must have matching lengths")
    return PhaseState{S}(nodes, Dict(node => idx for (idx, node) in enumerate(nodes)), cells)
end

Base.length(state::PhaseState) = length(state.cells)
Base.getindex(state::PhaseState, node::Symbol) = state.cells[state.index[node]]

struct PolynomialObject{I,R,U}
    name::Symbol
    modes::Vector{Symbol}
    port_schemas::Dict{Symbol,PortSchema}
    initial_state::I
    readout::R
    update::U
end

struct DependentLens{F,B}
    name::Symbol
    source_schema::PortSchema
    target_schema::PortSchema
    forward::F
    backward::B
end

struct LaxMonoidalFunctor{M}
    name::Symbol
    map::M
end

struct Laxator{M}
    name::Symbol
    measure::M
end

struct WiringEdge
    src_node::Symbol
    src_port::Symbol
    dst_node::Symbol
    dst_port::Symbol
end

struct WiringSpec
    nodes::Vector{Symbol}
    edges::Vector{WiringEdge}
end

struct PhaseProgram
    name::Symbol
    mode::Symbol
    objects::Dict{Symbol,PolynomialObject}
    wiring::WiringSpec
end

function identity_lens(schema::PortSchema)
    return DependentLens(
        :identity,
        schema,
        schema,
        outputs -> Dict(key => get(outputs, key, nothing) for key in schema.outputs),
        (state, incoming) -> Dict(key => get(incoming, key, nothing) for key in schema.inputs),
    )
end

function compose_lenses(left::DependentLens, right::DependentLens)
    return DependentLens(
        Symbol("$(left.name)_then_$(right.name)"),
        left.source_schema,
        right.target_schema,
        outputs -> right.forward(left.forward(outputs)),
        (state, incoming) -> left.backward(state, right.backward(left.forward(state), incoming)),
    )
end

function normalize_profile(A::AbstractVector{<:Real})
    amin = minimum(A)
    amax = maximum(A)
    if isapprox(amax, amin; atol=1.0e-12)
        return fill(0.0, length(A))
    end
    return (A .- amin) ./ (amax - amin)
end

function normalize_profile!(dest::AbstractVector{<:Real}, values::AbstractVector{<:Real})
    length(dest) == length(values) || error("normalization buffers must match profile length")
    amin = minimum(values)
    amax = maximum(values)
    if isapprox(amax, amin; atol=1.0e-12)
        fill!(dest, 0.0)
        return dest
    end
    scale = amax - amin
    @inbounds for idx in eachindex(dest, values)
        dest[idx] = (values[idx] - amin) / scale
    end
    return dest
end

struct CompiledPhase
    program::PhaseProgram
    diagram::Any
    box_ids::Dict{Symbol,Int}
    routes::Vector{NamedTuple{(:src_node, :src_port, :dst_node, :dst_port),Tuple{Symbol,Symbol,Symbol,Symbol}}}
end

function _port_names(spec::WiringSpec)
    inputs = Symbol[]
    outputs = Symbol[]
    for edge in spec.edges
        push!(outputs, edge.src_port)
        push!(inputs, edge.dst_port)
    end
    return unique(inputs), unique(outputs)
end

function _build_diagram(program::PhaseProgram)
    inputs, outputs = _port_names(program.wiring)
    diagram = WiringDiagram(inputs, outputs)
    box_ids = Dict{Symbol,Int}()
    for node in program.wiring.nodes
        object = program.objects[node]
        schema = object.port_schemas[program.mode]
        box_ids[node] = add_box!(diagram, Box(string(node), schema.inputs, schema.outputs))
    end
    for edge in program.wiring.edges
        src_box = box_ids[edge.src_node]
        dst_box = box_ids[edge.dst_node]
        src_ports = program.objects[edge.src_node].port_schemas[program.mode].outputs
        dst_ports = program.objects[edge.dst_node].port_schemas[program.mode].inputs
        src_index = findfirst(==(edge.src_port), src_ports)
        dst_index = findfirst(==(edge.dst_port), dst_ports)
        if src_index === nothing || dst_index === nothing
            error("invalid wiring edge $(edge.src_node).$(edge.src_port) -> $(edge.dst_node).$(edge.dst_port)")
        end
        add_wire!(diagram, (src_box, src_index) => (dst_box, dst_index))
    end
    return diagram, box_ids
end

function _compile_routes(program::PhaseProgram, diagram, box_ids::Dict{Symbol,Int})
    id_to_node = Dict{Int,Symbol}(v => k for (k, v) in box_ids)
    routes = Vector{
        NamedTuple{(:src_node, :src_port, :dst_node, :dst_port),Tuple{Symbol,Symbol,Symbol,Symbol}}
    }()
    sizehint!(routes, nwires(diagram, :Wire))
    for w in wires(diagram, :Wire)
        src_node = id_to_node[w.source.box]
        dst_node = id_to_node[w.target.box]
        src_port = output_ports(diagram, w.source.box)[w.source.port]
        dst_port = input_ports(diagram, w.target.box)[w.target.port]
        push!(
            routes,
            (src_node=src_node, src_port=src_port, dst_node=dst_node, dst_port=dst_port),
        )
    end
    return routes
end

function compile_phase(program::PhaseProgram)
    diagram, box_ids = _build_diagram(program)
    routes = _compile_routes(program, diagram, box_ids)
    return CompiledPhase(program, diagram, box_ids, routes)
end

function routing_inputs(program::PhaseProgram, outputs::Dict{Symbol,Dict{Symbol,Any}})
    incoming = Dict{Symbol,Dict{Symbol,Any}}(
        node => Dict{Symbol,Any}() for node in program.wiring.nodes
    )
    for edge in program.wiring.edges
        incoming[edge.dst_node][edge.dst_port] = outputs[edge.src_node][edge.src_port]
    end
    return incoming
end

function _next_states(program::PhaseProgram, states::AbstractDict, incoming::Dict{Symbol,Dict{Symbol,Any}})
    next_states = Dict{Symbol,Any}()
    for node in program.wiring.nodes
        object = program.objects[node]
        next_states[node] = object.update(states[node], incoming[node])
    end
    return next_states
end

function _next_states(program::PhaseProgram, states::PhaseState, incoming::Dict{Symbol,Dict{Symbol,Any}})
    cells = [
        program.objects[node].update(states[node], incoming[node]) for
        node in program.wiring.nodes
    ]
    return PhaseState(program.wiring.nodes, cells)
end

function execute_phase(compiled::CompiledPhase, states::AbstractDict)
    program = compiled.program

    outputs = Dict{Symbol,Dict{Symbol,Any}}()
    for node in program.wiring.nodes
        object = program.objects[node]
        outputs[node] = object.readout(states[node])
    end

    incoming = Dict{Symbol,Dict{Symbol,Any}}(
        node => Dict{Symbol,Any}() for node in program.wiring.nodes
    )
    for route in compiled.routes
        incoming[route.dst_node][route.dst_port] = outputs[route.src_node][route.src_port]
    end

    next_states = _next_states(program, states, incoming)
    return next_states, outputs, incoming
end

function execute_phase(compiled::CompiledPhase, states::PhaseState)
    program = compiled.program

    outputs = Dict{Symbol,Dict{Symbol,Any}}()
    for node in program.wiring.nodes
        object = program.objects[node]
        outputs[node] = object.readout(states[node])
    end

    incoming = Dict{Symbol,Dict{Symbol,Any}}(
        node => Dict{Symbol,Any}() for node in program.wiring.nodes
    )
    for route in compiled.routes
        incoming[route.dst_node][route.dst_port] = outputs[route.src_node][route.src_port]
    end

    next_states = _next_states(program, states, incoming)
    return next_states, outputs, incoming
end

diagram_box_count(compiled::CompiledPhase) = nboxes(compiled.diagram)
diagram_wire_count(compiled::CompiledPhase) = nwires(compiled.diagram, :Wire)

function rd_to_wave_lens(n_cells::Int; normalize::Bool=false)
    n_cells >= 1 || error("n_cells must be >= 1")
    return DependentLens(
        :rd_to_wave,
        PortSchema(Symbol[], [:A_profile, :I_profile]),
        PortSchema([:wave_A, :normalized_A, :source_pre], Symbol[]),
        function (rd_outputs)
            haskey(rd_outputs, :A_profile) || error("rd_to_wave_lens expects :A_profile")
            A = Float64.(rd_outputs[:A_profile])
            length(A) == n_cells || error("rd_to_wave_lens expected $n_cells cells")
            if haskey(rd_outputs, :I_profile)
                length(rd_outputs[:I_profile]) == n_cells || error("rd_to_wave_lens expected :I_profile length $n_cells")
            end
            normalized = normalize_profile(A)
            return Dict(
                :wave_A => normalize ? normalized : copy(A),
                :normalized_A => normalized,
                :source_pre => 1.0,
            )
        end,
        (state, incoming) -> incoming,
    )
end

function wave_to_ctrl_lens(n_cells::Int)
    n_cells >= 1 || error("n_cells must be >= 1")
    return DependentLens(
        :wave_to_ctrl,
        PortSchema(Symbol[], [:peak_count, :emitted, :done]),
        PortSchema([:peak_count], Symbol[]),
        function (wave_outputs)
            haskey(wave_outputs, :peak_count) || error("wave_to_ctrl_lens expects :peak_count")
            return Dict(:peak_count => wave_outputs[:peak_count])
        end,
        (state, incoming) -> incoming,
    )
end

end
