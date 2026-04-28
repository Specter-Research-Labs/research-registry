using PolyMorphogenesis
using Test

const PMAlgebra = PolyMorphogenesis.Algebra
const PMRD = PolyMorphogenesis.RD

@testset "compile routing" begin
    cell_schema = PMAlgebra.PortSchema([:in_left], [:out])
    cell = PMAlgebra.PolynomialObject(
        :cell,
        [:wave],
        Dict(:wave => cell_schema),
        () -> Dict(:mode => :wave, :value => 0),
        state -> Dict(:out => state[:value]),
        (state, incoming) -> Dict(:mode => state[:mode], :value => get(incoming, :in_left, 0)),
    )
    program = PMAlgebra.PhaseProgram(
        :toy,
        :wave,
        Dict(:a => cell, :b => cell),
        PMAlgebra.WiringSpec([:a, :b], [PMAlgebra.WiringEdge(:a, :out, :b, :in_left)]),
    )
    compiled = PMAlgebra.compile_phase(program)
    next_states, _, incoming = PMAlgebra.execute_phase(
        compiled,
        Dict(:a => Dict(:mode => :wave, :value => 7), :b => Dict(:mode => :wave, :value => 0)),
    )
    @test length(compiled.routes) == PMAlgebra.diagram_wire_count(compiled)
    @test incoming[:b][:in_left] == 7
    @test next_states[:b][:value] == 7
end

@testset "3-node chain routed through diagram" begin
    sender_schema = PMAlgebra.PortSchema(Symbol[], [:out])
    receiver_schema = PMAlgebra.PortSchema([:in_left, :in_right], Symbol[])

    sender = PMAlgebra.PolynomialObject(
        :sender,
        [:wave],
        Dict(:wave => sender_schema),
        () -> Dict(:mode => :wave, :value => 0),
        state -> Dict(:out => state[:value]),
        (state, incoming) -> state,
    )
    receiver = PMAlgebra.PolynomialObject(
        :receiver,
        [:wave],
        Dict(:wave => receiver_schema),
        () -> Dict(:mode => :wave, :value => 0),
        state -> Dict{Symbol,Any}(),
        (state, incoming) -> Dict(
            :mode => state[:mode],
            :value => get(incoming, :in_left, 0) + get(incoming, :in_right, 0),
        ),
    )

    program = PMAlgebra.PhaseProgram(
        :chain3,
        :wave,
        Dict(:a => sender, :b => receiver, :c => sender),
        PMAlgebra.WiringSpec(
            [:a, :b, :c],
            [PMAlgebra.WiringEdge(:a, :out, :b, :in_left), PMAlgebra.WiringEdge(:c, :out, :b, :in_right)],
        ),
    )
    compiled = PMAlgebra.compile_phase(program)

    states = Dict(
        :a => Dict(:mode => :wave, :value => 3),
        :b => Dict(:mode => :wave, :value => 0),
        :c => Dict(:mode => :wave, :value => 5),
    )
    next_states, _, incoming = PMAlgebra.execute_phase(compiled, states)

    @test incoming[:b][:in_left] == 3
    @test incoming[:b][:in_right] == 5
    @test next_states[:b][:value] == 8

    @test PMAlgebra.diagram_box_count(compiled) == 3
    @test PMAlgebra.diagram_wire_count(compiled) == 2
    @test length(compiled.routes) == 2
end

@testset "compiled phases execute typed phase state" begin
    nodes = [:cell_1, :cell_2]
    program = PMRD.rd_phase_program(RDParameters(), RDChainConfig(n_cells=2))
    compiled = PMAlgebra.compile_phase(program)
    states = PMAlgebra.PhaseState(
        nodes,
        [
            PolyMorphogenesis.RD.RDCellState(:rd, 0.2, 0.1),
            PolyMorphogenesis.RD.RDCellState(:rd, 0.8, 0.3),
        ],
    )

    next_states, outputs, incoming = PMAlgebra.execute_phase(compiled, states)

    @test next_states isa PMAlgebra.PhaseState{PolyMorphogenesis.RD.RDCellState}
    @test outputs[:cell_1][:A_out] == 0.2
    @test incoming[:cell_2][:A_left] == 0.2
end
