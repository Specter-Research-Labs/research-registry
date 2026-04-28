using PolyMorphogenesis
using Test

@testset "rd direct step" begin
    params = RDParameters()
    config = RDChainConfig(n_cells=8)
    state = vcat(fill(0.5, 8), fill(0.2, 8))
    delta = PolyMorphogenesis.RD.direct_rd_step(state, params)
    composed = PolyMorphogenesis.RD.composed_rd_step(state, params, config)
    @test length(delta) == length(state)
    @test all(isfinite, delta)
    @test delta ≈ composed atol=1.0e-10
end

@testset "rd direct step supports a single cell" begin
    params = RDParameters()
    config = RDChainConfig(n_cells=1, field_length=1.0)
    state = [0.5, 0.2]
    direct = PolyMorphogenesis.RD.direct_rd_step(state, params, config)
    composed = PolyMorphogenesis.RD.composed_rd_step(state, params, config)
    @test direct ≈ composed atol=1.0e-12
    @test all(isfinite, direct)
end

@testset "rd validation rejects malformed configs and states" begin
    params = RDParameters()
    @test_throws ErrorException PolyMorphogenesis.RD.make_rd_state(RDChainConfig(n_cells=4, cuts=[4]))
    @test_throws ErrorException PolyMorphogenesis.RD.composed_rd_step([0.5, 0.2, 0.1], params, RDChainConfig(n_cells=2))
end

@testset "RD cell approximate equilibrium is homeostatic under self-readout" begin
    params = RDParameters()
    config = RDChainConfig(n_cells=3)
    cell = PolyMorphogenesis.RD._rd_cell_object(params, config, :test)
    ratio = (params.gen_i * params.decay_a / (params.gen_a * params.decay_i)) ^ params.hill_n
    eq_A = params.gen_a / (params.decay_a * (1 + ratio))
    eq_I = params.gen_i / (params.decay_i * (1 + ratio))
    state = Dict(:mode => :rd, :A => eq_A, :I => eq_I)
    readout = cell.readout(state)
    incoming = Dict(
        :A_left => readout[:A_out],
        :A_right => readout[:A_out],
        :I_left => readout[:I_out],
        :I_right => readout[:I_out],
    )
    deriv = cell.update(state, incoming)
    @test deriv[:A] ≈ 0.0 atol=1.0e-12
    @test deriv[:I] ≈ 0.0 atol=1.0e-12
end

@testset "settle_rd_via_catlab matches composed integration" begin
    params = RDParameters()
    config = RDChainConfig(n_cells=6, field_length=12.0, tspan=(0.0, 5.0), seed=42)

    state_direct = PolyMorphogenesis.RD.make_rd_state(config; rng_seed=42)
    state_catlab = copy(state_direct)

    settle_rd_composed!(state_direct, params, config; tspan=(0.0, 5.0))
    PolyMorphogenesis.RD.settle_rd_via_catlab!(state_catlab, params, config; tspan=(0.0, 5.0))

    @test state_direct ≈ state_catlab atol=1.0e-6
end

@testset "rd demo" begin
    result = PolyMorphogenesis.Controller.rd_pattern_demo(n_cells=100, seed=0)
    @test result[:init_shape] == "LH"
    @test result[:peak_count] == 2
    @test result[:shape] == "LHLH"
    @test length(result[:A]) == 100
end
