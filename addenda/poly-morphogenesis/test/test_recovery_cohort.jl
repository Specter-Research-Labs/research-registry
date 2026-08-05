using PolyMorphogenesis
using Test

const RecoveryCohortAPI = PolyMorphogenesis.RecoveryCohort

function _tiny_cohort_spec()
    regime = RecoveryCohortAPI.RecoveryRegime(
        regime_id="tiny-grid",
        rows=2,
        cols=3,
        patch_rows=1,
        patch_cols=1,
        field_width=6.0,
        field_height=4.0,
        baseline=RDParameters(D_a=1.0, D_i=30.0),
    )
    protocol = RecoveryCohortAPI.RecoveryProtocol(
        settle_time=0.02,
        steady_tol=1.0e-5,
        recovery=PolyMorphogenesis.GraphRecovery.GraphRecoveryConfig(
            exponent_min=0,
            exponent_max=0,
            max_iterations=1,
            steady_stop=false,
            include_delayed_capacity=false,
            include_feedback=false,
        ),
        gates=RecoveryGateCriteria(bootstrap_replicates=100, bootstrap_seed=91),
        evidence_scope="tiny_contract",
    )
    return RecoveryCohortAPI.RecoveryCohortSpec(
        cohort_id="tiny-repeat",
        regime=regime,
        protocol=protocol,
        seeds=[8, 7],
        placements=[
            RecoveryPlacement(1, 2),
            RecoveryPlacement(1, 1),
        ],
    )
end

function _case_signature(case)
    return Tuple(getfield(case, name) for name in fieldnames(typeof(case)))
end

@testset "cohorts are canonical and deterministic" begin
    spec = _tiny_cohort_spec()
    first = run_recovery_cohort(spec)
    second = run_recovery_cohort(spec)

    @test first.seeds == [7, 8]
    @test [(placement.top, placement.left) for placement in first.placements] ==
        [(1, 1), (1, 2)]
    @test first.reference_preparation_count == 2
    @test length(first.cases) == 4
    @test length(unique(case.case_id for case in first.cases)) == 4
    @test [_case_signature(case) for case in first.cases] ==
        [_case_signature(case) for case in second.cases]
end

@testset "cohort artifacts are deterministic and immutable" begin
    spec = RecoveryCohortAPI.RecoveryCohortSpec(
        cohort_id="artifact-contract",
        regime=_tiny_cohort_spec().regime,
        protocol=_tiny_cohort_spec().protocol,
        seeds=[7],
        placements=[RecoveryPlacement(1, 1)],
    )
    result = run_recovery_cohort(spec)

    mktempdir() do root
        first_root = joinpath(root, "first")
        second_root = joinpath(root, "second")
        first_protocol = write_recovery_cohort_protocol_manifest(spec, first_root)
        second_protocol = write_recovery_cohort_protocol_manifest(spec, second_root)
        first = write_recovery_cohort_artifacts(result, first_root)
        second = write_recovery_cohort_artifacts(result, second_root)

        @test read(first_protocol.path) == read(second_protocol.path)
        @test read(first.cases_path) == read(second.cases_path)
        @test read(first.summary_path) == read(second.summary_path)
        @test read(first.manifest_path) == read(second.manifest_path)

        frozen_cases = read(first.cases_path)
        write(first.summary_path, "{}\n")
        @test_throws ErrorException write_recovery_cohort_artifacts(result, first_root)
        @test read(first.cases_path) == frozen_cases
        @test read(first.summary_path, String) == "{}\n"
    end
end
