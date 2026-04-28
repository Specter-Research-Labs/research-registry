using PolyMorphogenesis
using Test

@testset "closed loop defaults follow source controller semantics" begin
    default_config = ClosedLoopConfig()
    small_config = ClosedLoopConfig(n_cells=50)
    large_config = ClosedLoopConfig(n_cells=200)

    @test default_config.source_bootstrap
    @test default_config.min_iterations == 9
    @test default_config.max_iterations >= default_config.min_iterations
    @test default_config.rd_chain.field_length == 20.0
    @test small_config.rd_chain.field_length == 10.0
    @test large_config.rd_chain.field_length == 40.0
    @test default_config.wave.normalize_input == false
end

@testset "closed loop records source bootstrap before the first settle" begin
    config = ClosedLoopConfig(n_cells=10, target_peaks=1, min_iterations=1, max_iterations=1, seed=0)
    result = closed_loop(config)
    @test length(result[:history]) == 1
    @test result[:history][1][:controller_action] == :decrease
    @test result[:history][1][:D_a] ≈ 1 / 1.21 atol=1.0e-12
    @test result[:history][1][:source_D_a] ≈ (6.25e-13 / 1.21) atol=1.0e-18
    @test all(haskey(entry, :controller_action) for entry in result[:history])
    @test all(haskey(entry, :ctrl_peak_count) for entry in result[:history])
end

@testset "composed and procedural closed loops produce identical source-default histories" begin
    cases = [
        ClosedLoopConfig(n_cells=10, target_peaks=1, min_iterations=1, max_iterations=1, seed=0),
        ClosedLoopConfig(n_cells=10, target_peaks=0, min_iterations=1, max_iterations=1, seed=0),
    ]

    for config in cases
        proc = closed_loop(config)
        comp = PolyMorphogenesis.Controller.closed_loop_composed(config)

        @test proc[:converged] == comp[:converged]
        @test length(proc[:history]) == length(comp[:history])
        for i in eachindex(proc[:history])
            @test proc[:history][i][:wave_count] == comp[:history][i][:wave_count]
            @test proc[:history][i][:local_peak_count] == comp[:history][i][:local_peak_count]
            @test proc[:history][i][:shape] == comp[:history][i][:shape]
            @test proc[:history][i][:D_a] == comp[:history][i][:D_a]
            @test proc[:history][i][:controller_action] == comp[:history][i][:controller_action]
        end
    end
end

@testset "compiled closed-loop machine carries separate clear and GRN phases" begin
    machine = compile_closed_loop_machine(
        ClosedLoopConfig(n_cells=10, target_peaks=1, min_iterations=1, max_iterations=1, seed=0),
    )
    @test machine.wave_clear_plan.plan.config.pre_decay == 10.0
    @test machine.wave_grn_plan.plan.config.pre_decay == 1.0

    result = run_closed_loop_machine(machine)
    @test !isempty(result[:history])
    @test result[:history][1][:lens_wave_input][:source_pre] == 1.0
end

@testset "closed loop validates config invariants" begin
    bad_cells = ClosedLoopConfig(n_cells=10, rd_chain=RDChainConfig(n_cells=8))
    bad_iters = ClosedLoopConfig(min_iterations=9, max_iterations=8)
    @test_throws ErrorException closed_loop(bad_cells)
    @test_throws ErrorException PolyMorphogenesis.Controller.closed_loop_composed(bad_cells)
    @test_throws ErrorException closed_loop(bad_iters)
    @test_throws ErrorException PolyMorphogenesis.Controller.closed_loop_composed(bad_iters)
end
