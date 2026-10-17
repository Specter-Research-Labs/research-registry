using Test

using JSON3
using PolyMorphogenesis
using SHA
using PolyMorphogenesis.RD: RDParameters
using PolyMorphogenesis.RDGraph: RDGraphConfig, graph_connected_components

using PolyMorphogenesis.ResponseFunctor: ActionResponse,
    ComponentActionChoice,
    FiniteComponentResponse,
    aggregate_response
using PolyMorphogenesis.CompositionalPrediction: EXACT_FACTORIZATION_SCOPE,
    FiniteResponseProtocol,
    FragmentResponseBuild,
    FragmentScenario,
    assemble_disconnected,
    build_fragment_response,
    evaluate_monolithic_outcome,
    freeze_composed_prediction,
    freeze_compositional_protocol,
    graph_config,
    ordinary_twin_prediction,
    validate_composed_prediction,
    validation_passed,
    write_compositional_validation

@testset "constructed finite factorization rescue and ordinary twin" begin
    left = FiniteComponentResponse(
        "left",
        4.0,
        (
            ActionResponse(-1, true, 0.25),
            ActionResponse(0, false, 0.50),
            ActionResponse(1, false, 0.75),
        ),
    )
    right = FiniteComponentResponse(
        "right",
        9.0,
        (
            ActionResponse(-1, false, 1.00),
            ActionResponse(0, false, 0.50),
            ActionResponse(1, true, 0.25),
        ),
    )
    left_build = FragmentResponseBuild("left", left, 3)
    right_build = FragmentResponseBuild("right", right, 3)

    prediction = freeze_composed_prediction(right_build, left_build)
    ordinary = ordinary_twin_prediction(left_build, right_build)

    @test prediction == ordinary
    @test prediction.scope == EXACT_FACTORIZATION_SCOPE
    @test prediction.registered_shared_actions == (-1, 0, 1)
    @test prediction.local_feasible[1].actions == (-1,)
    @test prediction.local_feasible[2].actions == (1,)
    @test prediction.shared_feasible == ()
    @test prediction.local_capacity
    @test !prediction.shared_capacity
    @test prediction.factorization_rescue
    @test isnothing(prediction.best_shared)
    @test Tuple(choice.action for choice in prediction.best_local.actions) == (-1, 1)
    @test prediction.best_local.aggregate.profile_squared_error == 0.5
    @test prediction.component_response_simulation_count == 6
    @test prediction.naive_assembly_simulation_count == 9
end

@testset "weighted non-grid disconnected ODE factorization" begin
    config_a = RDGraphConfig(
        n_cells=3,
        x=[0.0, 1.3, 0.4],
        y=[0.0, 0.2, 1.1],
        edges=[(1, 2), (2, 3), (1, 3)],
        edge_weights=[0.8, 1.1, 0.6],
        tspan=(0.0, 0.2),
        seed=7,
        steady_tol=1.0e-9,
    )
    config_b = RDGraphConfig(
        n_cells=4,
        x=[2.1, 3.0, 2.4, 3.6],
        y=[-0.2, 0.1, 1.4, 1.0],
        edges=[(1, 2), (1, 3), (3, 4)],
        edge_weights=[0.7, 1.2, 0.9],
        tspan=(0.0, 0.2),
        seed=11,
        steady_tol=1.0e-9,
    )
    lesion_a = [0.90, 0.20, 0.70, 0.10, 0.40, 0.20]
    lesion_b = [0.15, 0.85, 0.65, 0.25, 0.35, 0.10, 0.20, 0.45]
    reference_a = copy(lesion_a)
    reference_b = copy(lesion_b)
    fragment_a = FragmentScenario(
        "fragment-a",
        config_a,
        lesion_a;
        reference_state=reference_a,
        threshold=0.5,
    )
    fragment_b = FragmentScenario(
        "fragment-b",
        config_b,
        lesion_b;
        reference_state=reference_b,
        threshold=0.5,
    )

    config_a.x[1] = 99.0
    config_a.edge_weights[1] = 99.0
    lesion_a[1] = 99.0
    reference_a[1] = 99.0
    @test fragment_a.graph.x[1] == 0.0
    @test fragment_a.graph.edge_weights[1] == 0.8
    @test fragment_a.lesion_state[1] == 0.90
    @test fragment_a.reference_state[1] == 0.90
    @test fragment_a.target_count == 1
    @test fragment_b.target_count == 2
    @test !ismutabletype(typeof(fragment_a))

    protocol = FiniteResponseProtocol(
        (1, -1, 0, 1),
        RDParameters(D_a=0.2, D_i=1.0);
        step_factor=1.4,
    )
    @test protocol.actions == (-1, 0, 1)
    @test protocol.scope == EXACT_FACTORIZATION_SCOPE

    build_a = build_fragment_response(fragment_a, protocol)
    build_b = build_fragment_response(fragment_b, protocol)
    @test build_a.simulation_count == 3
    @test build_b.simulation_count == 3
    @test all(response.capacity for response in build_a.response.responses)
    @test all(response.capacity for response in build_b.response.responses)
    @test all(
        isfinite(response.profile_squared_error) &&
        response.profile_squared_error >= 0
        for response in build_a.response.responses
    )

    prediction = freeze_composed_prediction(build_b, build_a)
    @test prediction == ordinary_twin_prediction(build_a, build_b)
    @test Tuple(
        component.component_id for component in prediction.responses.components
    ) == ("fragment-a", "fragment-b")
    @test prediction.component_response_simulation_count == 6
    @test prediction.naive_assembly_simulation_count == 9
    @test prediction.best_shared.action == 0
    @test Tuple(choice.action for choice in prediction.best_local.actions) == (0, 0)

    assembly = assemble_disconnected(
        fragment_b,
        fragment_a;
        assembly_id="weighted-non-grid-pair",
    )
    @test assembly.assembly_id == "weighted-non-grid-pair"
    @test Tuple(fragment.scenario_id for fragment in assembly.fragments) ==
        ("fragment-a", "fragment-b")
    @test assembly.component_ranges == (1:3, 4:7)
    @test length(graph_connected_components(graph_config(assembly))) == 2

    validation = nothing
    mktempdir() do output_dir
        frozen = freeze_compositional_protocol(
            assembly,
            protocol,
            prediction,
            output_dir,
        )
        @test freeze_compositional_protocol(
            assembly,
            protocol,
            prediction,
            output_dir,
        ) == frozen
        @test isfile(frozen.protocol_path)
        @test isfile(frozen.prediction_path)
        @test frozen.protocol_sha256 == bytes2hex(sha256(read(frozen.protocol_path)))
        @test frozen.prediction_sha256 == bytes2hex(sha256(read(frozen.prediction_path)))
        protocol_json = JSON3.read(read(frozen.protocol_path, String))
        prediction_json = JSON3.read(read(frozen.prediction_path, String))
        @test protocol_json.scope == EXACT_FACTORIZATION_SCOPE
        @test protocol_json.solver.fixed_horizon
        @test !protocol_json.solver.steady_stop
        @test protocol_json.action_grid == [-1, 0, 1]
        @test length(protocol_json.fragments) == 2
        @test prediction_json.frozen_protocol_sha256 == frozen.protocol_sha256
        @test prediction_json.component_response_simulation_count == 6
        @test prediction_json.naive_assembly_simulation_count == 9

        validation = validate_composed_prediction(
            assembly,
            protocol,
            prediction;
            atol=1.0e-7,
            rtol=1.0e-6,
        )
        artifact = write_compositional_validation(validation, frozen)
        @test artifact.frozen_protocol_sha256 == frozen.protocol_sha256
        @test artifact.frozen_prediction_sha256 == frozen.prediction_sha256
        @test artifact.sha256 == bytes2hex(sha256(read(artifact.path)))
        validation_json = JSON3.read(read(artifact.path, String))
        @test validation_json.schema_version == 2
        @test validation_json.frozen_prediction_sha256 == frozen.prediction_sha256
        @test validation_json.passed
        @test validation_json.validation.absolute_tolerance == 1.0e-7
        @test validation_json.validation.relative_tolerance == 1.0e-6
        @test validation_json.validation.monolithic_truth_simulation_count == 9
        @test write_compositional_validation(validation, frozen).sha256 == artifact.sha256

        open(artifact.path, "w") do io
            write(io, "tampered\n")
        end
        @test_throws ErrorException write_compositional_validation(validation, frozen)
    end
    @test validation_passed(validation)
    @test validation.absolute_tolerance == 1.0e-7
    @test validation.relative_tolerance == 1.0e-6
    @test validation.local_feasibility_match
    @test validation.shared_feasibility_match
    @test validation.factorization_rescue_match
    @test validation.best_local_action_match
    @test validation.best_shared_action_match
    @test validation.all_profile_aggregates_match
    @test validation.best_local_aggregate_match
    @test validation.best_shared_aggregate_match
    @test validation.max_profile_squared_error_delta < 1.0e-7
    @test validation.max_profile_relative_rmse_delta < 1.0e-7
    @test validation.component_response_simulation_count == 6
    @test validation.naive_assembly_simulation_count == 9
    @test validation.monolithic_truth_simulation_count == 9

    heterogeneous_choices = (
        ComponentActionChoice("fragment-b", 1),
        ComponentActionChoice("fragment-a", -1),
    )
    truth = evaluate_monolithic_outcome(
        assembly,
        protocol,
        heterogeneous_choices,
    )
    predicted = aggregate_response(prediction.responses, heterogeneous_choices)
    @test Tuple(choice.action for choice in truth.actions) == (-1, 1)
    @test isapprox(
        predicted.profile_squared_error,
        truth.aggregate.profile_squared_error;
        atol=1.0e-7,
        rtol=1.0e-6,
    )
    @test isapprox(
        predicted.profile_relative_rmse,
        truth.aggregate.profile_relative_rmse;
        atol=1.0e-7,
        rtol=1.0e-6,
    )
    @test length(truth.final_state) == 14

    @test_throws ErrorException assemble_disconnected(fragment_a)
    @test_throws ErrorException evaluate_monolithic_outcome(
        assembly,
        protocol,
        (
            ComponentActionChoice("fragment-a", -1),
            ComponentActionChoice("fragment-b", 2),
        ),
    )
    @test_throws ErrorException FragmentResponseBuild("fragment-a", build_a.response, -1)

    mktempdir() do output_dir
        frozen = freeze_compositional_protocol(
            assembly,
            protocol,
            prediction,
            output_dir,
        )
        open(frozen.prediction_path, "w") do io
            write(io, "tampered\n")
        end
        @test_throws ErrorException freeze_compositional_protocol(
            assembly,
            protocol,
            prediction,
            output_dir,
        )
        @test_throws ErrorException write_compositional_validation(validation, frozen)
    end
end
