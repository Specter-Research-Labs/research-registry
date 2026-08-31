using PolyMorphogenesis
using Test

const RecoveryAdaptiveAPI = PolyMorphogenesis.RecoveryAdaptive

@testset "adaptive settling is bounded and deterministic" begin
    config = grid_graph_config(1, 1; tspan=(0.0, 0.1), steady_tol=1.0e6)
    initial = make_rd_graph_state(config; rng_seed=2)
    protocol = RecoveryAdaptiveAPI.AdaptiveSettlingProtocol(
        chunk_time=0.03,
        max_time=0.07,
        confirmation_checks=2,
    )

    first_state = copy(initial)
    second_state = copy(initial)
    first = RecoveryAdaptiveAPI.settle_rd_graph_adaptive!(
        first_state,
        RDParameters(),
        config;
        protocol,
    )
    second = RecoveryAdaptiveAPI.settle_rd_graph_adaptive!(
        second_state,
        RDParameters(),
        config;
        protocol,
    )

    @test first.termination == :steady
    @test first.reached_steady
    @test first.elapsed_time <= protocol.max_time
    @test first.required_confirmation_checks == 2
    @test first.achieved_confirmation_checks == 2
    @test first.checkpoints == second.checkpoints
    @test first_state == second_state

    capped_config = grid_graph_config(1, 1; tspan=(0.0, 0.1), steady_tol=1.0e-30)
    capped = RecoveryAdaptiveAPI.settle_rd_graph_adaptive!(
        make_rd_graph_state(capped_config; rng_seed=3),
        RDParameters(),
        capped_config;
        protocol,
    )
    @test capped.termination == :time_cap
    @test !capped.reached_steady
    @test capped.elapsed_time == protocol.max_time
end

@testset "adaptive exponent search evaluates each exponent once" begin
    calls = Int[]
    result = RecoveryAdaptiveAPI.search_adaptive_exponent_bounds(
        exponent -> begin
            push!(calls, exponent)
            exponent ^ 2
        end,
        (bounds, _, values) -> if bounds == (-1, 1)
            RecoveryAdaptiveAPI.AdaptiveExponentStageDecision(
                sum(values);
                requested_sides=[:lower, :upper],
                objective=2.0,
            )
        else
            RecoveryAdaptiveAPI.AdaptiveExponentStageDecision(
                sum(values);
                objective=0.0,
                unresolved_boundary=false,
            )
        end;
        protocol=RecoveryAdaptiveAPI.AdaptiveExponentProtocol(
            initial_min=-1,
            initial_max=1,
            hard_min=-2,
            hard_max=2,
            expansion_step=1,
        ),
    )

    @test result.diagnostics.termination == :interior
    @test result.diagnostics.final_bounds == (-2, 2)
    @test calls == [-1, 0, 1, -2, 2]
    @test length(unique(calls)) == length(calls)
    @test result.cache == Dict(exponent => exponent ^ 2 for exponent in -2:2)
end
