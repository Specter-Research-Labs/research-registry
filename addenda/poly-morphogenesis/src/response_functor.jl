module ResponseFunctor

export ActionResponse,
    FiniteComponentResponse,
    FiniteResponseTensor,
    ComponentActionChoice,
    AggregateResponse,
    SharedActionOptimum,
    LocalActionOptimum,
    response_identity,
    tensor,
    response_at,
    local_feasible_actions,
    shared_feasible_actions,
    has_local_capacity,
    has_shared_capacity,
    factorization_rescue,
    aggregate_response,
    aggregate_shared_response,
    best_shared_action,
    best_local_action_vector

"""One measured response at one member of the frozen finite action set."""
struct ActionResponse
    action::Int
    capacity::Bool
    profile_squared_error::Float64

    function ActionResponse(
        action::Integer,
        capacity::Bool,
        profile_squared_error::Real,
    )
        error_value = Float64(profile_squared_error)
        isfinite(error_value) || error("profile_squared_error must be finite")
        error_value >= 0 || error("profile_squared_error must be nonnegative")
        return new(Int(action), capacity, error_value)
    end
end

Base.:(==)(left::ActionResponse, right::ActionResponse) =
    left.action == right.action &&
    left.capacity == right.capacity &&
    left.profile_squared_error == right.profile_squared_error

"""
An immutable finite response map for one component.

Actions are canonicalized into ascending order. `capacity` is an existential
property of the frozen response map; it does not claim that an online policy can
observe, identify, or reach the corresponding action.
"""
struct FiniteComponentResponse{R<:Tuple}
    component_id::String
    reference_energy::Float64
    responses::R
end

function FiniteComponentResponse(
    component_id,
    reference_energy::Real,
    responses,
)
    canonical_id = string(component_id)
    isempty(canonical_id) && error("component_id must not be empty")
    energy = Float64(reference_energy)
    isfinite(energy) || error("reference_energy must be finite")
    energy >= 0 || error("reference_energy must be nonnegative")

    rows = ActionResponse[response for response in responses]
    isempty(rows) && error("a finite component response requires at least one action")
    sort!(rows; by=response -> response.action)
    actions = [response.action for response in rows]
    length(unique(actions)) == length(actions) ||
        error("component actions must be unique")
    canonical_rows = Tuple(rows)
    return FiniteComponentResponse{typeof(canonical_rows)}(
        canonical_id,
        energy,
        canonical_rows,
    )
end

Base.:(==)(left::FiniteComponentResponse, right::FiniteComponentResponse) =
    left.component_id == right.component_id &&
    left.reference_energy == right.reference_energy &&
    left.responses == right.responses

"""A canonical immutable tensor of zero or more component response maps."""
struct FiniteResponseTensor{C<:Tuple}
    components::C
end

function FiniteResponseTensor(components)
    entries = FiniteComponentResponse[component for component in components]
    sort!(entries; by=component -> component.component_id)
    ids = [component.component_id for component in entries]
    length(unique(ids)) == length(ids) || error("component_id values must be unique")
    canonical = Tuple(entries)
    return FiniteResponseTensor{typeof(canonical)}(canonical)
end

Base.:(==)(left::FiniteResponseTensor, right::FiniteResponseTensor) =
    left.components == right.components

"""The empty response tensor, serving as the composition identity."""
response_identity() = FiniteResponseTensor(())

function _append_components!(
    components::Vector{FiniteComponentResponse},
    factor::FiniteComponentResponse,
)
    push!(components, factor)
    return components
end

function _append_components!(
    components::Vector{FiniteComponentResponse},
    factor::FiniteResponseTensor,
)
    append!(components, factor.components)
    return components
end

"""
Tensor component maps or previously composed tensors.

Components are canonicalized by identifier, so evaluation is invariant to the
order in which independent factors are supplied.
"""
function tensor(factors::Union{FiniteComponentResponse,FiniteResponseTensor}...)
    components = FiniteComponentResponse[]
    for factor in factors
        _append_components!(components, factor)
    end
    return FiniteResponseTensor(components)
end

function response_at(component::FiniteComponentResponse, action::Integer)
    index = findfirst(response -> response.action == action, component.responses)
    isnothing(index) && error(
        "action $(Int(action)) is not registered for component $(component.component_id)",
    )
    return component.responses[index]
end

local_feasible_actions(component::FiniteComponentResponse) = Tuple(
    response.action for response in component.responses if response.capacity
)

function shared_feasible_actions(responses::FiniteResponseTensor)
    isempty(responses.components) && return ()
    shared = Set(local_feasible_actions(first(responses.components)))
    for component in Iterators.drop(responses.components, 1)
        intersect!(shared, Set(local_feasible_actions(component)))
    end
    return Tuple(sort!(collect(shared)))
end

"""
Whether every component has at least one feasible local action.

This is finite-set capacity only. It is intentionally silent about controller
observability, path constraints, convergence, or online reachability.
"""
has_local_capacity(responses::FiniteResponseTensor) = all(
    component -> !isempty(local_feasible_actions(component)),
    responses.components,
)

"""Whether one registered action is feasible for every nonempty component."""
has_shared_capacity(responses::FiniteResponseTensor) =
    !isempty(responses.components) && !isempty(shared_feasible_actions(responses))

"""
Whether local capacity exists for every component while shared capacity does not.

This predicate compares the Cartesian product of local feasible sets with their
ordinary set intersection; it makes no online-controller claim.
"""
factorization_rescue(responses::FiniteResponseTensor) =
    !isempty(responses.components) &&
    has_local_capacity(responses) &&
    isempty(shared_feasible_actions(responses))

struct ComponentActionChoice
    component_id::String
    action::Int

    ComponentActionChoice(component_id, action::Integer) =
        new(string(component_id), Int(action))
end

Base.:(==)(left::ComponentActionChoice, right::ComponentActionChoice) =
    left.component_id == right.component_id && left.action == right.action

struct AggregateResponse
    profile_squared_error::Float64
    reference_energy::Float64
    profile_relative_rmse::Float64
end

Base.:(==)(left::AggregateResponse, right::AggregateResponse) =
    left.profile_squared_error == right.profile_squared_error &&
    left.reference_energy == right.reference_energy &&
    left.profile_relative_rmse == right.profile_relative_rmse

struct SharedActionOptimum
    action::Int
    aggregate::AggregateResponse
end

Base.:(==)(left::SharedActionOptimum, right::SharedActionOptimum) =
    left.action == right.action && left.aggregate == right.aggregate

struct LocalActionOptimum{C<:Tuple}
    actions::C
    aggregate::AggregateResponse
end

Base.:(==)(left::LocalActionOptimum, right::LocalActionOptimum) =
    left.actions == right.actions && left.aggregate == right.aggregate

function _canonical_choices(choices)
    entries = ComponentActionChoice[choice for choice in choices]
    sort!(entries; by=choice -> choice.component_id)
    ids = [choice.component_id for choice in entries]
    length(unique(ids)) == length(ids) || error("component action choices must be unique")
    return Tuple(entries)
end

function aggregate_response(responses::FiniteResponseTensor, choices)
    canonical = _canonical_choices(choices)
    component_ids = Tuple(component.component_id for component in responses.components)
    choice_ids = Tuple(choice.component_id for choice in canonical)
    choice_ids == component_ids || error(
        "component action choices must match the response tensor exactly",
    )

    total_squared_error = 0.0
    total_reference_energy = 0.0
    for (component, choice) in zip(responses.components, canonical)
        response = response_at(component, choice.action)
        total_squared_error += response.profile_squared_error
        total_reference_energy += component.reference_energy
    end
    relative_rmse = sqrt(
        total_squared_error / max(total_reference_energy, eps(Float64)),
    )
    return AggregateResponse(
        total_squared_error,
        total_reference_energy,
        relative_rmse,
    )
end

"""Evaluate the global diagonal by applying one registered action everywhere."""
function aggregate_shared_response(responses::FiniteResponseTensor, action::Integer)
    choices = Tuple(
        ComponentActionChoice(component.component_id, action)
        for component in responses.components
    )
    return aggregate_response(responses, choices)
end

"""Return the minimum-error capacity-feasible global action, or `nothing`."""
function best_shared_action(responses::FiniteResponseTensor)
    feasible = shared_feasible_actions(responses)
    isempty(feasible) && return nothing
    candidates = [
        SharedActionOptimum(action, aggregate_shared_response(responses, action))
        for action in feasible
    ]
    return argmin(
        candidate -> (
            candidate.aggregate.profile_squared_error,
            candidate.action,
        ),
        candidates,
    )
end

"""Return the minimum-error capacity-feasible local action vector, or `nothing`."""
function best_local_action_vector(responses::FiniteResponseTensor)
    has_local_capacity(responses) || return nothing
    choices = ComponentActionChoice[]
    for component in responses.components
        feasible = [response for response in component.responses if response.capacity]
        chosen = argmin(
            response -> (response.profile_squared_error, response.action),
            feasible,
        )
        push!(
            choices,
            ComponentActionChoice(component.component_id, chosen.action),
        )
    end
    canonical = Tuple(choices)
    return LocalActionOptimum(canonical, aggregate_response(responses, canonical))
end

end
