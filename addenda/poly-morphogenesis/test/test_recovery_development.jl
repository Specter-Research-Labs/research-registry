using PolyMorphogenesis
using Test

const RecoveryDevelopmentAPI = PolyMorphogenesis.RecoveryDevelopment
const RecoveryAdaptiveForDevelopment = PolyMorphogenesis.RecoveryAdaptive
const RecoveryCohortForDevelopment = PolyMorphogenesis.RecoveryCohort

function _tiny_development_spec(;
    development_id::String="tiny-development-run",
    seeds::Vector{Int}=[7],
    steady_tol::Float64=1.0e6,
)
    regime = RecoveryCohortForDevelopment.RecoveryRegime(
        regime_id="tiny-development",
        rows=1,
        cols=2,
        patch_rows=1,
        patch_cols=1,
        field_width=2.0,
        field_height=1.0,
        baseline=RDParameters(D_a=1.0, D_i=30.0),
    )
    protocol = RecoveryDevelopmentAPI.RecoveryDevelopmentProtocol(
        steady_tol=steady_tol,
        settling=RecoveryAdaptiveForDevelopment.AdaptiveSettlingProtocol(
            chunk_time=0.01,
            max_time=0.02,
        ),
        exponents=RecoveryAdaptiveForDevelopment.AdaptiveExponentProtocol(
            initial_min=0,
            initial_max=0,
            hard_min=-1,
            hard_max=1,
            expansion_step=1,
            plateau_relative_tolerance=0.0,
            plateau_patience=2,
        ),
        alias_resolutions=[1.0e-3],
    )
    return RecoveryDevelopmentAPI.RecoveryDevelopmentSpec(
        development_id=development_id,
        regime=regime,
        protocol=protocol,
        seeds=seeds,
        placements=[RecoveryCohortForDevelopment.RecoveryPlacement(1, 1)],
    )
end

@testset "development protocol keeps holdouts inaccessible" begin
    for seed in (100, 111, 200, 211)
        @test_throws ErrorException RecoveryDevelopmentAPI.run_recovery_development(
            _tiny_development_spec(; seeds=[seed]),
        )
    end

    mktempdir() do root
        @test_throws ErrorException RecoveryDevelopmentAPI.write_recovery_development_protocol(
            _tiny_development_spec(),
            joinpath(root, "holdout-a", "development"),
        )
    end
end

@testset "development artifacts are deterministic and immutable" begin
    spec = _tiny_development_spec()
    result = RecoveryDevelopmentAPI.run_recovery_development(spec)
    @test !isempty(result.response_surface_rows)
    @test length(result.observability_cases) == 1

    withenv("POLY_MORPHOGENESIS_REVISION" => "development-test-revision") do
        mktempdir() do root
            first_root = joinpath(root, "first")
            second_root = joinpath(root, "second")
            first_protocol = RecoveryDevelopmentAPI.write_recovery_development_protocol(
                spec,
                first_root,
            )
            second_protocol = RecoveryDevelopmentAPI.write_recovery_development_protocol(
                spec,
                second_root,
            )
            first = RecoveryDevelopmentAPI.write_recovery_development_artifacts(
                result,
                first_root,
            )
            second = RecoveryDevelopmentAPI.write_recovery_development_artifacts(
                result,
                second_root,
            )

            @test read(first_protocol.path) == read(second_protocol.path)
            for (left, right) in (
                (first.response_surfaces_path, second.response_surfaces_path),
                (first.observability_cases_path, second.observability_cases_path),
                (first.summary_path, second.summary_path),
                (first.manifest_path, second.manifest_path),
            )
                @test read(left) == read(right)
            end

            frozen_response = read(first.response_surfaces_path)
            write(first.summary_path, "{}\n")
            @test_throws ErrorException RecoveryDevelopmentAPI.write_recovery_development_artifacts(
                result,
                first_root,
            )
            @test read(first.response_surfaces_path) == frozen_response
            @test read(first.summary_path, String) == "{}\n"
        end
    end
end
