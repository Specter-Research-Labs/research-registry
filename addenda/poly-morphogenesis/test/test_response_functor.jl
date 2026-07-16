using PolyMorphogenesis
using PolyMorphogenesis.ResponseFunctor
using Test

function _component(id, energy, rows)
    return FiniteComponentResponse(
        id,
        energy,
        [ActionResponse(action, feasible, error) for (action, feasible, error) in rows],
    )
end

function _ordinary_local_product(components)
    feasible_sets = [collect(local_feasible_actions(component)) for component in components]
    any(isempty, feasible_sets) && return Tuple[]
    return vec([Tuple(actions) for actions in Iterators.product(feasible_sets...)])
end

function _ordinary_aggregate(components, actions)
    squared_error = sum(
        response_at(component, action).profile_squared_error
        for (component, action) in zip(components, actions)
    )
    reference_energy = sum(component.reference_energy for component in components)
    return AggregateResponse(
        squared_error,
        reference_energy,
        sqrt(squared_error / max(reference_energy, eps(Float64))),
    )
end

@testset "finite component maps are canonical and immutable" begin
    component = _component(
        :right,
        5.0,
        [(2, true, 3.0), (-1, false, 7.0), (0, true, 1.0)],
    )

    @test component.component_id == "right"
    @test Tuple(response.action for response in component.responses) == (-1, 0, 2)
    @test local_feasible_actions(component) == (0, 2)
    @test response_at(component, 2) == ActionResponse(2, true, 3.0)
    @test_throws ErrorException response_at(component, 1)
    @test_throws ErrorException _component(:duplicate, 1.0, [(0, true, 1.0), (0, false, 2.0)])
    @test_throws ErrorException _component(:negative, -1.0, [(0, true, 1.0)])
    @test_throws ErrorException ActionResponse(0, true, -1.0)
end

@testset "tensor has identity, associativity, and component permutation invariance" begin
    left = _component(:left, 4.0, [(-1, true, 4.0), (0, true, 1.0)])
    middle = _component(:middle, 5.0, [(0, true, 2.0), (1, true, 1.0)])
    right = _component(:right, 6.0, [(0, true, 3.0), (2, true, 2.0)])
    identity = response_identity()

    @test tensor() == identity
    @test tensor(identity, left) == tensor(left, identity) == tensor(left)
    @test tensor(tensor(left, middle), right) == tensor(left, tensor(middle, right))

    canonical = tensor(left, middle, right)
    permuted = tensor(right, left, middle)
    @test canonical == permuted
    @test shared_feasible_actions(canonical) == shared_feasible_actions(permuted) == (0,)
    @test best_shared_action(canonical) == best_shared_action(permuted)
    @test best_local_action_vector(canonical) == best_local_action_vector(permuted)
    @test_throws ErrorException tensor(left, left)
end

@testset "shared intersection and local product match ordinary finite sets" begin
    left = _component(:left, 4.0, [(-1, true, 5.0), (0, true, 1.0), (1, false, 0.5)])
    right = _component(:right, 5.0, [(-1, false, 2.0), (0, true, 3.0), (1, true, 1.0)])
    responses = tensor(left, right)
    components = responses.components

    ordinary_sets = [Set(local_feasible_actions(component)) for component in components]
    ordinary_intersection = reduce(intersect, ordinary_sets)
    ordinary_product = _ordinary_local_product(components)

    @test Set(shared_feasible_actions(responses)) == ordinary_intersection == Set([0])
    @test has_shared_capacity(responses) == !isempty(ordinary_intersection)
    @test has_local_capacity(responses) == !isempty(ordinary_product)
    @test !factorization_rescue(responses)

    explicit_shared = argmin(
        candidate -> (candidate.aggregate.profile_squared_error, candidate.action),
        [
            SharedActionOptimum(action, _ordinary_aggregate(components, fill(action, length(components))))
            for action in ordinary_intersection
        ],
    )
    @test best_shared_action(responses) == explicit_shared

    explicit_local_actions = argmin(
        actions -> (
            _ordinary_aggregate(components, actions).profile_squared_error,
            actions,
        ),
        ordinary_product,
    )
    explicit_choices = Tuple(
        ComponentActionChoice(component.component_id, action)
        for (component, action) in zip(components, explicit_local_actions)
    )
    explicit_local = LocalActionOptimum(
        explicit_choices,
        _ordinary_aggregate(components, explicit_local_actions),
    )
    @test best_local_action_vector(responses) == explicit_local
end

@testset "factorization rescue is capacity without reachability semantics" begin
    left = _component(:left, 4.0, [(-10, true, 1.0), (10, false, 2.0)])
    right = _component(:right, 5.0, [(-10, false, 2.0), (10, true, 1.0)])
    responses = tensor(left, right)

    ordinary_sets = [Set(local_feasible_actions(component)) for component in responses.components]
    ordinary_intersection = reduce(intersect, ordinary_sets)
    ordinary_product = _ordinary_local_product(responses.components)

    @test isempty(ordinary_intersection)
    @test ordinary_product == [(-10, 10)]
    @test has_local_capacity(responses)
    @test !has_shared_capacity(responses)
    @test factorization_rescue(responses)
    @test isnothing(best_shared_action(responses))
    @test Tuple(choice.action for choice in best_local_action_vector(responses).actions) == (-10, 10)
end

@testset "profile aggregation matches recovery SSE and energy composition" begin
    left = _component(:left, 4.0, [(0, true, 1.0), (1, true, 4.0)])
    right = _component(:right, 5.0, [(0, true, 8.0), (1, true, 1.0)])
    responses = tensor(left, right)

    shared = aggregate_shared_response(responses, 0)
    @test shared.profile_squared_error == 9.0
    @test shared.reference_energy == 9.0
    @test shared.profile_relative_rmse == 1.0

    local_optimum = best_local_action_vector(responses)
    @test Tuple(choice.action for choice in local_optimum.actions) == (0, 1)
    @test local_optimum.aggregate.profile_squared_error == 2.0
    @test local_optimum.aggregate.reference_energy == 9.0
    @test local_optimum.aggregate.profile_relative_rmse == sqrt(2 / 9)
end

@testset "missing local capacity remains distinct from factorization rescue" begin
    left = _component(:left, 1.0, [(0, false, 0.0)])
    right = _component(:right, 1.0, [(0, true, 0.0)])
    responses = tensor(left, right)

    @test !has_local_capacity(responses)
    @test !has_shared_capacity(responses)
    @test !factorization_rescue(responses)
    @test isnothing(best_local_action_vector(responses))
end
