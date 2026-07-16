module CompositionalPrediction

using JSON3
using OrdinaryDiffEq
using SciMLBase
using SHA

using ..RD: RDParameters
using ..RDGraph: RDGraphConfig,
    RD_GRAPH_ABSTOL,
    RD_GRAPH_MAXITERS,
    RD_GRAPH_RELTOL,
    RD_GRAPH_SOLVER_ALGORITHM,
    graph_connected_components,
    settle_rd_graph!
using ..GridLesions: graph_morphology_snapshot
using ..GraphRecovery: diffusion_parameters_at_exponent
using ..ResponseFunctor: ActionResponse,
    AggregateResponse,
    ComponentActionChoice,
    FiniteComponentResponse,
    FiniteResponseTensor,
    LocalActionOptimum,
    SharedActionOptimum,
    aggregate_response,
    best_local_action_vector,
    best_shared_action,
    factorization_rescue,
    has_local_capacity,
    has_shared_capacity,
    local_feasible_actions,
    response_at,
    shared_feasible_actions,
    tensor

export EXACT_FACTORIZATION_SCOPE,
    FrozenGraphConfig,
    FrozenRDParameters,
    FragmentScenario,
    FiniteResponseProtocol,
    FragmentResponseBuild,
    ComponentFeasibleActions,
    FrozenComposedPrediction,
    DisconnectedAssembly,
    FragmentTruthOutcome,
    AssemblyTruth,
    PredictionValidation,
    CompositionalProtocolFreeze,
    CompositionalValidationArtifact,
    graph_config,
    baseline_parameters,
    build_fragment_response,
    freeze_composed_prediction,
    ordinary_twin_prediction,
    assemble_disconnected,
    evaluate_monolithic_outcome,
    validate_composed_prediction,
    validation_passed,
    freeze_compositional_protocol,
    write_compositional_validation

const EXACT_FACTORIZATION_SCOPE =
    "exact_disconnected_rd_factorization_capacity_not_controller_reachability"

struct FrozenGraphConfig{X<:Tuple,Y<:Tuple,E<:Tuple,W<:Tuple}
    n_cells::Int
    x::X
    y::Y
    edges::E
    edge_weights::W
    tspan::Tuple{Float64,Float64}
    seed::Int
    steady_tol::Float64
end

function FrozenGraphConfig(config::RDGraphConfig)
    config.n_cells >= 1 || error("n_cells must be >= 1")
    length(config.x) == config.n_cells || error("x length must match n_cells")
    length(config.y) == config.n_cells || error("y length must match n_cells")
    all(isfinite, config.x) || error("x coordinates must be finite")
    all(isfinite, config.y) || error("y coordinates must be finite")
    length(config.edges) == length(config.edge_weights) ||
        error("edge_weights must match edges length")
    all(isfinite, config.tspan) || error("tspan values must be finite")
    config.tspan[2] >= config.tspan[1] || error("tspan end must be >= tspan start")
    isfinite(config.steady_tol) && config.steady_tol > 0 ||
        error("steady_tol must be finite and positive")

    pairs = Tuple{NTuple{2,Int},Float64}[]
    for (edge, raw_weight) in zip(config.edges, config.edge_weights)
        left, right = edge
        1 <= left <= config.n_cells || error("edge endpoint must lie in 1:n_cells")
        1 <= right <= config.n_cells || error("edge endpoint must lie in 1:n_cells")
        left != right || error("self-edges are not allowed")
        weight = Float64(raw_weight)
        isfinite(weight) && weight > 0 || error("edge weights must be finite and positive")
        normalized = left < right ? (left, right) : (right, left)
        push!(pairs, (normalized, weight))
    end
    sort!(pairs; by=first)
    edges = [pair[1] for pair in pairs]
    length(unique(edges)) == length(edges) || error("graph edges must be unique")
    weights = [pair[2] for pair in pairs]
    return FrozenGraphConfig(
        config.n_cells,
        Tuple(Float64.(config.x)),
        Tuple(Float64.(config.y)),
        Tuple(edges),
        Tuple(weights),
        (Float64(config.tspan[1]), Float64(config.tspan[2])),
        config.seed,
        Float64(config.steady_tol),
    )
end

Base.:(==)(left::FrozenGraphConfig, right::FrozenGraphConfig) =
    left.n_cells == right.n_cells &&
    left.x == right.x &&
    left.y == right.y &&
    left.edges == right.edges &&
    left.edge_weights == right.edge_weights &&
    left.tspan == right.tspan &&
    left.seed == right.seed &&
    left.steady_tol == right.steady_tol

function graph_config(config::FrozenGraphConfig)
    return RDGraphConfig(
        n_cells=config.n_cells,
        x=collect(config.x),
        y=collect(config.y),
        edges=collect(config.edges),
        edge_weights=collect(config.edge_weights),
        tspan=config.tspan,
        seed=config.seed,
        steady_tol=config.steady_tol,
    )
end

struct FrozenRDParameters
    hill_n::Float64
    gen_a::Float64
    gen_i::Float64
    decay_a::Float64
    decay_i::Float64
    D_a::Float64
    D_i::Float64
end

function FrozenRDParameters(parameters::RDParameters)
    values = Float64[
        parameters.hill_n,
        parameters.gen_a,
        parameters.gen_i,
        parameters.decay_a,
        parameters.decay_i,
        parameters.D_a,
        parameters.D_i,
    ]
    all(isfinite, values) || error("reaction-diffusion parameters must be finite")
    parameters.D_a > 0 || error("baseline D_a must be positive")
    parameters.D_i > 0 || error("baseline D_i must be positive")
    return FrozenRDParameters(values...)
end

function baseline_parameters(parameters::FrozenRDParameters)
    return RDParameters(
        hill_n=parameters.hill_n,
        gen_a=parameters.gen_a,
        gen_i=parameters.gen_i,
        decay_a=parameters.decay_a,
        decay_i=parameters.decay_i,
        D_a=parameters.D_a,
        D_i=parameters.D_i,
    )
end

struct FragmentScenario{G<:FrozenGraphConfig,S<:Tuple,R<:Tuple}
    scenario_id::String
    graph::G
    lesion_state::S
    reference_state::R
    threshold::Float64
    target_count::Int
end

function FragmentScenario(
    scenario_id,
    config::RDGraphConfig,
    lesion_state::AbstractVector{<:Real};
    reference_state::AbstractVector{<:Real}=lesion_state,
    threshold::Real,
    target_count::Union{Nothing,Integer}=nothing,
)
    id = string(scenario_id)
    isempty(id) && error("scenario_id must not be empty")
    frozen_graph = FrozenGraphConfig(config)
    canonical_config = graph_config(frozen_graph)
    length(graph_connected_components(canonical_config)) == 1 ||
        error("a fragment scenario graph must be connected")
    expected_length = 2 * frozen_graph.n_cells
    length(lesion_state) == expected_length ||
        error("lesion_state length must be 2 * n_cells")
    length(reference_state) == expected_length ||
        error("reference_state length must be 2 * n_cells")
    lesion = Tuple(Float64.(lesion_state))
    reference = Tuple(Float64.(reference_state))
    all(isfinite, lesion) || error("lesion_state must be finite")
    all(isfinite, reference) || error("reference_state must be finite")
    threshold_value = Float64(threshold)
    isfinite(threshold_value) || error("threshold must be finite")
    reference_snapshot = graph_morphology_snapshot(
        collect(reference),
        canonical_config;
        threshold=threshold_value,
    )
    target = isnothing(target_count) ?
        reference_snapshot.component_count : Int(target_count)
    target >= 0 || error("target_count must be nonnegative")
    target <= frozen_graph.n_cells || error("target_count must not exceed n_cells")
    return FragmentScenario{typeof(frozen_graph),typeof(lesion),typeof(reference)}(
        id,
        frozen_graph,
        lesion,
        reference,
        threshold_value,
        target,
    )
end

graph_config(scenario::FragmentScenario) = graph_config(scenario.graph)

"""A frozen action protocol evaluated only at each scenario's fixed horizon."""
struct FiniteResponseProtocol{A<:Tuple}
    actions::A
    baseline::FrozenRDParameters
    step_factor::Float64
    scope::String
end

function FiniteResponseProtocol(
    actions,
    baseline::RDParameters=RDParameters();
    step_factor::Real=1.21,
)
    canonical_actions = sort!(unique(Int.(collect(actions))))
    isempty(canonical_actions) && error("the frozen action grid must not be empty")
    factor = Float64(step_factor)
    isfinite(factor) && factor > 1 || error("step_factor must be finite and > 1")
    action_tuple = Tuple(canonical_actions)
    return FiniteResponseProtocol{typeof(action_tuple)}(
        action_tuple,
        FrozenRDParameters(baseline),
        factor,
        EXACT_FACTORIZATION_SCOPE,
    )
end

baseline_parameters(protocol::FiniteResponseProtocol) =
    baseline_parameters(protocol.baseline)

function _require_exact_protocol(protocol::FiniteResponseProtocol)
    protocol.scope == EXACT_FACTORIZATION_SCOPE || error("protocol scope mismatch")
    return nothing
end

struct FragmentResponseBuild{R<:FiniteComponentResponse}
    scenario_id::String
    response::R
    simulation_count::Int

    function FragmentResponseBuild{R}(
        scenario_id::String,
        response::R,
        simulation_count::Int,
    ) where {R<:FiniteComponentResponse}
        isempty(scenario_id) && error("scenario_id must not be empty")
        simulation_count >= 0 || error("simulation_count must be nonnegative")
        return new{R}(scenario_id, response, simulation_count)
    end
end

function FragmentResponseBuild(
    scenario_id,
    response::FiniteComponentResponse,
    simulation_count::Integer,
)
    id = string(scenario_id)
    isempty(id) && error("scenario_id must not be empty")
    count = Int(simulation_count)
    count >= 0 || error("simulation_count must be nonnegative")
    return FragmentResponseBuild{typeof(response)}(id, response, count)
end

function _profile_squared_error(
    state::AbstractVector{<:Real},
    reference::Tuple,
    n_cells::Int,
)
    return sum(
        (Float64(state[index]) - reference[index]) ^ 2
        for index in 1:n_cells
    )
end

function _reference_energy(reference::Tuple, n_cells::Int)
    return sum(reference[index] ^ 2 for index in 1:n_cells)
end

"""
Build one finite component response map by direct ODE simulation per action.

Capacity means only that the fixed thresholded domain count equals the frozen
target. No online-controller reachability is inferred.
"""
function build_fragment_response(
    scenario::FragmentScenario,
    protocol::FiniteResponseProtocol,
)
    _require_exact_protocol(protocol)
    config = graph_config(scenario)
    baseline = baseline_parameters(protocol)
    rows = ActionResponse[]
    for action in protocol.actions
        parameters = diffusion_parameters_at_exponent(
            baseline,
            action,
            protocol.step_factor,
        )
        state = collect(scenario.lesion_state)
        settle_rd_graph!(
            state,
            parameters,
            config;
            steady_stop=false,
        )
        snapshot = graph_morphology_snapshot(
            state,
            config;
            threshold=scenario.threshold,
        )
        push!(
            rows,
            ActionResponse(
                action,
                snapshot.component_count == scenario.target_count,
                _profile_squared_error(
                    state,
                    scenario.reference_state,
                    config.n_cells,
                ),
            ),
        )
    end
    response = FiniteComponentResponse(
        scenario.scenario_id,
        _reference_energy(scenario.reference_state, config.n_cells),
        rows,
    )
    return FragmentResponseBuild(
        scenario.scenario_id,
        response,
        length(protocol.actions),
    )
end

struct ComponentFeasibleActions{A<:Tuple}
    component_id::String
    actions::A
end

Base.:(==)(left::ComponentFeasibleActions, right::ComponentFeasibleActions) =
    left.component_id == right.component_id && left.actions == right.actions

struct FrozenComposedPrediction{T<:FiniteResponseTensor,L<:Tuple,S<:Tuple,R<:Tuple}
    scope::String
    responses::T
    registered_shared_actions::R
    local_feasible::L
    shared_feasible::S
    local_capacity::Bool
    shared_capacity::Bool
    factorization_rescue::Bool
    best_shared::Union{Nothing,SharedActionOptimum}
    best_local::Union{Nothing,LocalActionOptimum}
    component_response_simulation_count::Int
    naive_assembly_simulation_count::Int
end

Base.:(==)(left::FrozenComposedPrediction, right::FrozenComposedPrediction) =
    left.scope == right.scope &&
    left.responses == right.responses &&
    left.registered_shared_actions == right.registered_shared_actions &&
    left.local_feasible == right.local_feasible &&
    left.shared_feasible == right.shared_feasible &&
    left.local_capacity == right.local_capacity &&
    left.shared_capacity == right.shared_capacity &&
    left.factorization_rescue == right.factorization_rescue &&
    left.best_shared == right.best_shared &&
    left.best_local == right.best_local &&
    left.component_response_simulation_count == right.component_response_simulation_count &&
    left.naive_assembly_simulation_count == right.naive_assembly_simulation_count

function _canonical_builds(builds)
    entries = FragmentResponseBuild[build for build in builds]
    length(entries) >= 2 || error("composition requires at least two fragments")
    sort!(entries; by=build -> build.scenario_id)
    ids = [build.scenario_id for build in entries]
    length(unique(ids)) == length(ids) || error("fragment scenario ids must be unique")
    all(build.scenario_id == build.response.component_id for build in entries) ||
        error("fragment build ids must match response component ids")
    return entries
end

function _registered_shared_actions(responses::FiniteResponseTensor)
    registered = Set(response.action for response in first(responses.components).responses)
    for component in Iterators.drop(responses.components, 1)
        intersect!(registered, Set(response.action for response in component.responses))
    end
    return Tuple(sort!(collect(registered)))
end

function _naive_simulation_count(responses::FiniteResponseTensor)
    count = 1
    for component in responses.components
        count = Base.checked_mul(count, length(component.responses))
    end
    return count
end

"""Freeze the compositional prediction before any assembly-level truth solve."""
function freeze_composed_prediction(builds...)
    canonical = _canonical_builds(builds)
    responses = tensor((build.response for build in canonical)...)
    local_feasible = Tuple(
        ComponentFeasibleActions(
            component.component_id,
            local_feasible_actions(component),
        ) for component in responses.components
    )
    return FrozenComposedPrediction(
        EXACT_FACTORIZATION_SCOPE,
        responses,
        _registered_shared_actions(responses),
        local_feasible,
        shared_feasible_actions(responses),
        has_local_capacity(responses),
        has_shared_capacity(responses),
        factorization_rescue(responses),
        best_shared_action(responses),
        best_local_action_vector(responses),
        sum(build.simulation_count for build in canonical),
        _naive_simulation_count(responses),
    )
end

function _ordinary_component_rows(component::FiniteComponentResponse)
    return Dict(
        response.action => (
            capacity=response.capacity,
            profile_squared_error=response.profile_squared_error,
        ) for response in component.responses
    )
end

function _ordinary_aggregate(
    components,
    rows,
    actions,
)
    squared_error = sum(
        rows[index][actions[index]].profile_squared_error
        for index in eachindex(components)
    )
    energy = sum(component.reference_energy for component in components)
    return AggregateResponse(
        squared_error,
        energy,
        sqrt(squared_error / max(energy, eps(Float64))),
    )
end

"""An explicit ordinary set-intersection/product twin of the response tensor."""
function ordinary_twin_prediction(builds...)
    canonical = _canonical_builds(builds)
    components = sort!(
        [build.response for build in canonical];
        by=component -> component.component_id,
    )
    rows = [_ordinary_component_rows(component) for component in components]
    registered_sets = [Set(keys(row)) for row in rows]
    registered_shared = Tuple(sort!(collect(reduce(intersect, registered_sets))))
    feasible_sets = [
        sort!([action for (action, row) in component_rows if row.capacity])
        for component_rows in rows
    ]
    shared = Tuple(sort!(collect(reduce(intersect, Set.(feasible_sets)))))
    local_capacity = all(!isempty, feasible_sets)
    shared_capacity = !isempty(shared)
    rescue = local_capacity && !shared_capacity

    shared_candidates = SharedActionOptimum[
        SharedActionOptimum(
            action,
            _ordinary_aggregate(
                components,
                rows,
                fill(action, length(components)),
            ),
        ) for action in shared
    ]
    best_shared = isempty(shared_candidates) ? nothing : argmin(
        candidate -> (candidate.aggregate.profile_squared_error, candidate.action),
        shared_candidates,
    )

    best_local = nothing
    if local_capacity
        products = vec([Tuple(actions) for actions in Iterators.product(feasible_sets...)])
        chosen_actions = argmin(
            actions -> (
                _ordinary_aggregate(components, rows, actions).profile_squared_error,
                actions,
            ),
            products,
        )
        choices = Tuple(
            ComponentActionChoice(component.component_id, action)
            for (component, action) in zip(components, chosen_actions)
        )
        best_local = LocalActionOptimum(
            choices,
            _ordinary_aggregate(components, rows, chosen_actions),
        )
    end

    responses = FiniteResponseTensor(Tuple(components))
    return FrozenComposedPrediction(
        EXACT_FACTORIZATION_SCOPE,
        responses,
        registered_shared,
        Tuple(
            ComponentFeasibleActions(component.component_id, Tuple(feasible))
            for (component, feasible) in zip(components, feasible_sets)
        ),
        shared,
        local_capacity,
        shared_capacity,
        rescue,
        best_shared,
        best_local,
        sum(build.simulation_count for build in canonical),
        _naive_simulation_count(responses),
    )
end

struct DisconnectedAssembly{F<:Tuple,G<:FrozenGraphConfig,R<:Tuple}
    assembly_id::String
    fragments::F
    graph::G
    component_ranges::R
end

function assemble_disconnected(fragments::FragmentScenario...; assembly_id="")
    length(fragments) >= 2 || error("a disconnected assembly requires at least two fragments")
    canonical = sort!(collect(fragments); by=fragment -> fragment.scenario_id)
    ids = [fragment.scenario_id for fragment in canonical]
    length(unique(ids)) == length(ids) || error("fragment scenario ids must be unique")
    first_config = first(canonical).graph
    all(fragment.graph.tspan == first_config.tspan for fragment in canonical) ||
        error("fragment tspan values must match")
    all(fragment.graph.steady_tol == first_config.steady_tol for fragment in canonical) ||
        error("fragment steady_tol values must match")

    x = Float64[]
    y = Float64[]
    edges = NTuple{2,Int}[]
    weights = Float64[]
    ranges = UnitRange{Int}[]
    offset = 0
    for fragment in canonical
        append!(x, fragment.graph.x)
        append!(y, fragment.graph.y)
        append!(
            edges,
            [(left + offset, right + offset) for (left, right) in fragment.graph.edges],
        )
        append!(weights, fragment.graph.edge_weights)
        push!(ranges, (offset + 1):(offset + fragment.graph.n_cells))
        offset += fragment.graph.n_cells
    end
    union_config = FrozenGraphConfig(
        RDGraphConfig(
            n_cells=offset,
            x=x,
            y=y,
            edges=edges,
            edge_weights=weights,
            tspan=first_config.tspan,
            seed=first_config.seed,
            steady_tol=first_config.steady_tol,
        ),
    )
    length(graph_connected_components(graph_config(union_config))) == length(canonical) ||
        error("assembled graph must be the disjoint union of its fragments")
    id = isempty(string(assembly_id)) ? join(ids, "__tensor__") : string(assembly_id)
    return DisconnectedAssembly(
        id,
        Tuple(canonical),
        union_config,
        Tuple(ranges),
    )
end

graph_config(assembly::DisconnectedAssembly) = graph_config(assembly.graph)

function _assembly_initial_state(assembly::DisconnectedAssembly)
    activator = Float64[]
    inhibitor = Float64[]
    for fragment in assembly.fragments
        n = fragment.graph.n_cells
        append!(activator, fragment.lesion_state[1:n])
        append!(inhibitor, fragment.lesion_state[(n + 1):(2n)])
    end
    return vcat(activator, inhibitor)
end

function _canonical_choices(assembly::DisconnectedAssembly, choices)
    entries = ComponentActionChoice[choice for choice in choices]
    sort!(entries; by=choice -> choice.component_id)
    ids = Tuple(choice.component_id for choice in entries)
    expected = Tuple(fragment.scenario_id for fragment in assembly.fragments)
    ids == expected || error("component action choices must match the assembly exactly")
    return Tuple(entries)
end

struct _AssemblyDynamics
    config::RDGraphConfig
    component_for_node::Vector{Int}
    parameters::Vector{RDParameters}
end

function _assembly_rhs!(du, state, dynamics::_AssemblyDynamics, _time)
    config = dynamics.config
    n = config.n_cells
    activator = @view state[1:n]
    inhibitor = @view state[(n + 1):(2n)]
    d_activator = @view du[1:n]
    d_inhibitor = @view du[(n + 1):(2n)]
    for node in 1:n
        parameters = dynamics.parameters[dynamics.component_for_node[node]]
        ratio = (inhibitor[node] / (activator[node] + 1.0e-20)) ^ parameters.hill_n
        generation = 1.0 / (1.0 + ratio)
        d_activator[node] = parameters.gen_a * generation -
            parameters.decay_a * activator[node]
        d_inhibitor[node] = parameters.gen_i * generation -
            parameters.decay_i * inhibitor[node]
    end
    for (edge, weight) in zip(config.edges, config.edge_weights)
        left, right = edge
        component = dynamics.component_for_node[left]
        component == dynamics.component_for_node[right] ||
            error("heterogeneous diffusion is valid only across disconnected components")
        parameters = dynamics.parameters[component]
        activator_flux = weight * (activator[right] - activator[left])
        inhibitor_flux = weight * (inhibitor[right] - inhibitor[left])
        d_activator[left] += parameters.D_a * activator_flux
        d_activator[right] -= parameters.D_a * activator_flux
        d_inhibitor[left] += parameters.D_i * inhibitor_flux
        d_inhibitor[right] -= parameters.D_i * inhibitor_flux
    end
    return nothing
end

struct FragmentTruthOutcome
    component_id::String
    action::Int
    capacity::Bool
    observed_count::Int
    profile_squared_error::Float64
    reference_energy::Float64
end

struct AssemblyTruth{C<:Tuple,O<:Tuple,S<:Tuple}
    scope::String
    actions::C
    components::O
    aggregate::AggregateResponse
    final_state::S
end

function _component_substate(
    state::Vector{Float64},
    total_cells::Int,
    nodes::UnitRange{Int},
)
    inhibitor_nodes = (total_cells + first(nodes)):(total_cells + last(nodes))
    return vcat(
        collect(@view state[nodes]),
        collect(@view state[inhibitor_nodes]),
    )
end

"""
Evaluate one action vector through an independent monolithic disjoint-union ODE.

Different diffusion parameters are accepted only because every graph edge stays
inside one declared connected component.
"""
function evaluate_monolithic_outcome(
    assembly::DisconnectedAssembly,
    protocol::FiniteResponseProtocol,
    choices,
)
    _require_exact_protocol(protocol)
    canonical = _canonical_choices(assembly, choices)
    all(choice.action in protocol.actions for choice in canonical) ||
        error("component actions must belong to the frozen action grid")
    config = graph_config(assembly)
    baseline = baseline_parameters(protocol)
    parameters = [
        diffusion_parameters_at_exponent(
            baseline,
            choice.action,
            protocol.step_factor,
        ) for choice in canonical
    ]
    component_for_node = zeros(Int, config.n_cells)
    for (component, nodes) in enumerate(assembly.component_ranges)
        component_for_node[nodes] .= component
    end
    all(>(0), component_for_node) || error("every assembly node must belong to a component")
    dynamics = _AssemblyDynamics(config, component_for_node, parameters)
    initial_state = _assembly_initial_state(assembly)
    problem = ODEProblem(_assembly_rhs!, initial_state, config.tspan, dynamics)
    solution = solve(
        problem,
        Tsit5();
        save_everystep=false,
        save_start=false,
        save_end=true,
        dense=false,
        abstol=RD_GRAPH_ABSTOL,
        reltol=RD_GRAPH_RELTOL,
        maxiters=RD_GRAPH_MAXITERS,
    )
    SciMLBase.successful_retcode(solution) ||
        error("assembly RD solve failed with return code $(solution.retcode)")
    final_state = collect(solution.u[end])

    outcomes = FragmentTruthOutcome[]
    total_squared_error = 0.0
    total_reference_energy = 0.0
    for (index, fragment) in enumerate(assembly.fragments)
        fragment_config = graph_config(fragment)
        fragment_state = _component_substate(
            final_state,
            config.n_cells,
            assembly.component_ranges[index],
        )
        snapshot = graph_morphology_snapshot(
            fragment_state,
            fragment_config;
            threshold=fragment.threshold,
        )
        squared_error = _profile_squared_error(
            fragment_state,
            fragment.reference_state,
            fragment_config.n_cells,
        )
        energy = _reference_energy(
            fragment.reference_state,
            fragment_config.n_cells,
        )
        push!(
            outcomes,
            FragmentTruthOutcome(
                fragment.scenario_id,
                canonical[index].action,
                snapshot.component_count == fragment.target_count,
                snapshot.component_count,
                squared_error,
                energy,
            ),
        )
        total_squared_error += squared_error
        total_reference_energy += energy
    end
    aggregate = AggregateResponse(
        total_squared_error,
        total_reference_energy,
        sqrt(
            total_squared_error /
            max(total_reference_energy, eps(Float64)),
        ),
    )
    return AssemblyTruth(
        EXACT_FACTORIZATION_SCOPE,
        canonical,
        Tuple(outcomes),
        aggregate,
        Tuple(final_state),
    )
end

struct PredictionValidation
    scope::String
    absolute_tolerance::Float64
    relative_tolerance::Float64
    local_feasibility_match::Bool
    shared_feasibility_match::Bool
    factorization_rescue_match::Bool
    best_local_action_match::Bool
    best_shared_action_match::Bool
    all_profile_aggregates_match::Bool
    best_local_aggregate_match::Bool
    best_shared_aggregate_match::Bool
    max_profile_squared_error_delta::Float64
    max_profile_relative_rmse_delta::Float64
    component_response_simulation_count::Int
    naive_assembly_simulation_count::Int
    monolithic_truth_simulation_count::Int
end

validation_passed(validation::PredictionValidation) =
    validation.local_feasibility_match &&
    validation.shared_feasibility_match &&
    validation.factorization_rescue_match &&
    validation.best_local_action_match &&
    validation.best_shared_action_match &&
    validation.all_profile_aggregates_match &&
    validation.best_local_aggregate_match &&
    validation.best_shared_aggregate_match

function _all_registered_action_vectors(prediction::FrozenComposedPrediction)
    domains = [
        [response.action for response in component.responses]
        for component in prediction.responses.components
    ]
    return vec([Tuple(actions) for actions in Iterators.product(domains...)])
end

function _choices(components, actions)
    return Tuple(
        ComponentActionChoice(component.component_id, action)
        for (component, action) in zip(components, actions)
    )
end

function _same_aggregate(
    left::AggregateResponse,
    right::AggregateResponse,
    absolute_tolerance::Float64,
    relative_tolerance::Float64,
)
    return isapprox(
        left.profile_squared_error,
        right.profile_squared_error;
        atol=absolute_tolerance,
        rtol=relative_tolerance,
    ) && isapprox(
        left.reference_energy,
        right.reference_energy;
        atol=absolute_tolerance,
        rtol=relative_tolerance,
    ) && isapprox(
        left.profile_relative_rmse,
        right.profile_relative_rmse;
        atol=absolute_tolerance,
        rtol=relative_tolerance,
    )
end

"""Exhaustively validate a previously frozen prediction against monolithic truth."""
function validate_composed_prediction(
    assembly::DisconnectedAssembly,
    protocol::FiniteResponseProtocol,
    prediction::FrozenComposedPrediction;
    atol::Real=1.0e-7,
    rtol::Real=1.0e-6,
)
    _require_exact_protocol(protocol)
    prediction.scope == EXACT_FACTORIZATION_SCOPE || error("prediction scope mismatch")
    component_ids = Tuple(component.component_id for component in prediction.responses.components)
    assembly_ids = Tuple(fragment.scenario_id for fragment in assembly.fragments)
    component_ids == assembly_ids || error("prediction components must match the assembly")
    all(
        Tuple(row.action for row in component.responses) == protocol.actions
        for component in prediction.responses.components
    ) || error("prediction actions must match the frozen protocol grid")
    absolute_tolerance = Float64(atol)
    relative_tolerance = Float64(rtol)
    absolute_tolerance >= 0 || error("atol must be nonnegative")
    relative_tolerance >= 0 || error("rtol must be nonnegative")

    action_vectors = _all_registered_action_vectors(prediction)
    truth_by_actions = Dict{Tuple,AssemblyTruth}()
    capacity_matches = true
    aggregates_match = true
    max_squared_error_delta = 0.0
    max_relative_rmse_delta = 0.0
    for actions in action_vectors
        choices = _choices(prediction.responses.components, actions)
        truth = evaluate_monolithic_outcome(assembly, protocol, choices)
        truth_by_actions[actions] = truth
        predicted = aggregate_response(prediction.responses, choices)
        aggregates_match &= _same_aggregate(
            predicted,
            truth.aggregate,
            absolute_tolerance,
            relative_tolerance,
        )
        max_squared_error_delta = max(
            max_squared_error_delta,
            abs(predicted.profile_squared_error - truth.aggregate.profile_squared_error),
        )
        max_relative_rmse_delta = max(
            max_relative_rmse_delta,
            abs(predicted.profile_relative_rmse - truth.aggregate.profile_relative_rmse),
        )
        for (component, action, outcome) in zip(
            prediction.responses.components,
            actions,
            truth.components,
        )
            capacity_matches &= response_at(component, action).capacity == outcome.capacity
        end
    end

    truth_feasible = [
        actions for actions in action_vectors
        if all(outcome.capacity for outcome in truth_by_actions[actions].components)
    ]
    predicted_local_capacity = prediction.local_capacity
    truth_local_capacity = !isempty(truth_feasible)
    local_feasibility_match = capacity_matches &&
        predicted_local_capacity == truth_local_capacity

    truth_shared_feasible = Int[]
    for action in prediction.registered_shared_actions
        actions = ntuple(_ -> action, length(prediction.responses.components))
        if haskey(truth_by_actions, actions) &&
           all(outcome.capacity for outcome in truth_by_actions[actions].components)
            push!(truth_shared_feasible, action)
        end
    end
    shared_feasibility_match = Tuple(truth_shared_feasible) == prediction.shared_feasible
    truth_factorization_rescue = truth_local_capacity && isempty(truth_shared_feasible)
    factorization_rescue_match =
        prediction.factorization_rescue == truth_factorization_rescue

    truth_best_local_actions = isempty(truth_feasible) ? nothing : argmin(
        actions -> (
            truth_by_actions[actions].aggregate.profile_squared_error,
            actions,
        ),
        truth_feasible,
    )
    predicted_best_local_actions = isnothing(prediction.best_local) ? nothing : Tuple(
        choice.action for choice in prediction.best_local.actions
    )
    best_local_action_match = predicted_best_local_actions == truth_best_local_actions
    best_local_aggregate_match = if isnothing(truth_best_local_actions)
        isnothing(prediction.best_local)
    else
        _same_aggregate(
            prediction.best_local.aggregate,
            truth_by_actions[truth_best_local_actions].aggregate,
            absolute_tolerance,
            relative_tolerance,
        )
    end

    truth_best_shared_action = isempty(truth_shared_feasible) ? nothing : argmin(
        action -> (
            truth_by_actions[
                ntuple(_ -> action, length(prediction.responses.components))
            ].aggregate.profile_squared_error,
            action,
        ),
        truth_shared_feasible,
    )
    predicted_best_shared_action = isnothing(prediction.best_shared) ?
        nothing : prediction.best_shared.action
    best_shared_action_match = predicted_best_shared_action == truth_best_shared_action
    best_shared_aggregate_match = if isnothing(truth_best_shared_action)
        isnothing(prediction.best_shared)
    else
        _same_aggregate(
            prediction.best_shared.aggregate,
            truth_by_actions[ntuple(
                _ -> truth_best_shared_action,
                length(prediction.responses.components),
            )].aggregate,
            absolute_tolerance,
            relative_tolerance,
        )
    end

    return PredictionValidation(
        EXACT_FACTORIZATION_SCOPE,
        absolute_tolerance,
        relative_tolerance,
        local_feasibility_match,
        shared_feasibility_match,
        factorization_rescue_match,
        best_local_action_match,
        best_shared_action_match,
        aggregates_match,
        best_local_aggregate_match,
        best_shared_aggregate_match,
        max_squared_error_delta,
        max_relative_rmse_delta,
        prediction.component_response_simulation_count,
        prediction.naive_assembly_simulation_count,
        length(action_vectors),
    )
end

struct CompositionalProtocolFreeze
    protocol_path::String
    prediction_path::String
    protocol_sha256::String
    prediction_sha256::String
end

Base.:(==)(left::CompositionalProtocolFreeze, right::CompositionalProtocolFreeze) =
    left.protocol_path == right.protocol_path &&
    left.prediction_path == right.prediction_path &&
    left.protocol_sha256 == right.protocol_sha256 &&
    left.prediction_sha256 == right.prediction_sha256

struct CompositionalValidationArtifact
    path::String
    sha256::String
    frozen_protocol_sha256::String
    frozen_prediction_sha256::String
end

function _aggregate_payload(aggregate::AggregateResponse)
    return (
        profile_squared_error=aggregate.profile_squared_error,
        reference_energy=aggregate.reference_energy,
        profile_relative_rmse=aggregate.profile_relative_rmse,
    )
end

function _fragment_protocol_payload(fragment::FragmentScenario)
    graph = fragment.graph
    return (
        scenario_id=fragment.scenario_id,
        graph=(
            n_cells=graph.n_cells,
            x=collect(graph.x),
            y=collect(graph.y),
            edges=collect(graph.edges),
            edge_weights=collect(graph.edge_weights),
            tspan=collect(graph.tspan),
            seed=graph.seed,
            steady_tol=graph.steady_tol,
        ),
        lesion_state=collect(fragment.lesion_state),
        reference_state=collect(fragment.reference_state),
        threshold=fragment.threshold,
        target_count=fragment.target_count,
    )
end

function _protocol_payload(
    assembly::DisconnectedAssembly,
    protocol::FiniteResponseProtocol,
)
    baseline = protocol.baseline
    return (
        schema_version=1,
        scope=EXACT_FACTORIZATION_SCOPE,
        assembly_id=assembly.assembly_id,
        action_grid=collect(protocol.actions),
        baseline=(
            hill_n=baseline.hill_n,
            gen_a=baseline.gen_a,
            gen_i=baseline.gen_i,
            decay_a=baseline.decay_a,
            decay_i=baseline.decay_i,
            D_a=baseline.D_a,
            D_i=baseline.D_i,
        ),
        step_factor=protocol.step_factor,
        solver=(
            algorithm=RD_GRAPH_SOLVER_ALGORITHM,
            abstol=RD_GRAPH_ABSTOL,
            reltol=RD_GRAPH_RELTOL,
            maxiters=RD_GRAPH_MAXITERS,
            fixed_horizon=true,
            steady_stop=false,
        ),
        fragments=[
            _fragment_protocol_payload(fragment)
            for fragment in assembly.fragments
        ],
        component_ranges=[collect(nodes) for nodes in assembly.component_ranges],
    )
end

function _shared_optimum_payload(optimum::Nothing)
    return nothing
end

function _shared_optimum_payload(optimum::SharedActionOptimum)
    return (
        action=optimum.action,
        aggregate=_aggregate_payload(optimum.aggregate),
    )
end

function _local_optimum_payload(optimum::Nothing)
    return nothing
end

function _local_optimum_payload(optimum::LocalActionOptimum)
    return (
        actions=[
            (component_id=choice.component_id, action=choice.action)
            for choice in optimum.actions
        ],
        aggregate=_aggregate_payload(optimum.aggregate),
    )
end

function _prediction_payload(
    prediction::FrozenComposedPrediction,
    protocol_sha256::String,
)
    return (
        schema_version=1,
        scope=prediction.scope,
        frozen_protocol_sha256=protocol_sha256,
        components=[
            (
                component_id=component.component_id,
                reference_energy=component.reference_energy,
                responses=[
                    (
                        action=response.action,
                        capacity=response.capacity,
                        profile_squared_error=response.profile_squared_error,
                    ) for response in component.responses
                ],
            ) for component in prediction.responses.components
        ],
        registered_shared_actions=collect(prediction.registered_shared_actions),
        local_feasible=[
            (
                component_id=entry.component_id,
                actions=collect(entry.actions),
            ) for entry in prediction.local_feasible
        ],
        shared_feasible=collect(prediction.shared_feasible),
        local_capacity=prediction.local_capacity,
        shared_capacity=prediction.shared_capacity,
        factorization_rescue=prediction.factorization_rescue,
        best_shared=_shared_optimum_payload(prediction.best_shared),
        best_local=_local_optimum_payload(prediction.best_local),
        component_response_simulation_count=
            prediction.component_response_simulation_count,
        naive_assembly_simulation_count=
            prediction.naive_assembly_simulation_count,
    )
end

function _json_bytes(payload)
    io = IOBuffer()
    JSON3.write(io, payload)
    write(io, '\n')
    return take!(io)
end

function _artifact_path(output_dir::AbstractString, filename::String)
    directory = String(output_dir)
    isempty(directory) && error("output_dir must not be empty")
    ispath(directory) && !isdir(directory) && error("output_dir must be a directory")
    path = joinpath(directory, filename)
    ispath(path) && !isfile(path) && error("$(filename) must be a regular file")
    return path
end

function _atomic_bytes_write(path::String, bytes::Vector{UInt8})
    mkpath(dirname(path))
    temporary, io = mktemp(dirname(path))
    moved = false
    try
        write(io, bytes)
        close(io)
        mv(temporary, path; force=false)
        moved = true
    finally
        isopen(io) && close(io)
        !moved && rm(temporary; force=true)
    end
    return path
end

function _freeze_artifact_set(artifacts::Vector{Tuple{String,Vector{UInt8}}})
    existing = [isfile(path) for (path, _) in artifacts]
    any(existing) && !all(existing) && error(
        "refusing a partial compositional artifact set; use a new output directory",
    )
    for (path, bytes) in artifacts
        if isfile(path)
            read(path) == bytes || error(
                "$(basename(path)) is immutable and refuses overwrite",
            )
        end
    end
    for (path, bytes) in artifacts
        isfile(path) || _atomic_bytes_write(path, bytes)
    end
    return nothing
end

_sha256_file(path::String) = bytes2hex(sha256(read(path)))

"""
Freeze the complete prospective protocol and its composed prediction to disk.

The response prediction is written before any truth artifact and records the
protocol hash. Existing identical bytes are accepted idempotently; divergent or
partial files are never overwritten.
"""
function freeze_compositional_protocol(
    assembly::DisconnectedAssembly,
    protocol::FiniteResponseProtocol,
    prediction::FrozenComposedPrediction,
    output_dir::AbstractString,
)
    _require_exact_protocol(protocol)
    prediction.scope == EXACT_FACTORIZATION_SCOPE || error("prediction scope mismatch")
    component_ids = Tuple(
        component.component_id for component in prediction.responses.components
    )
    assembly_ids = Tuple(fragment.scenario_id for fragment in assembly.fragments)
    component_ids == assembly_ids || error("prediction components must match the assembly")
    all(
        Tuple(response.action for response in component.responses) == protocol.actions
        for component in prediction.responses.components
    ) || error("prediction actions must match the frozen protocol grid")

    protocol_path = _artifact_path(output_dir, "compositional-protocol.json")
    prediction_path = _artifact_path(output_dir, "composed-prediction.json")
    protocol_bytes = _json_bytes(_protocol_payload(assembly, protocol))
    protocol_hash = bytes2hex(sha256(protocol_bytes))
    prediction_bytes = _json_bytes(_prediction_payload(prediction, protocol_hash))
    prediction_hash = bytes2hex(sha256(prediction_bytes))
    _freeze_artifact_set([
        (protocol_path, protocol_bytes),
        (prediction_path, prediction_bytes),
    ])
    return CompositionalProtocolFreeze(
        protocol_path,
        prediction_path,
        protocol_hash,
        prediction_hash,
    )
end

function _validation_payload(
    validation::PredictionValidation,
    frozen::CompositionalProtocolFreeze,
)
    return (
        schema_version=2,
        scope=validation.scope,
        frozen_protocol_sha256=frozen.protocol_sha256,
        frozen_prediction_sha256=frozen.prediction_sha256,
        passed=validation_passed(validation),
        validation=(
            absolute_tolerance=validation.absolute_tolerance,
            relative_tolerance=validation.relative_tolerance,
            local_feasibility_match=validation.local_feasibility_match,
            shared_feasibility_match=validation.shared_feasibility_match,
            factorization_rescue_match=validation.factorization_rescue_match,
            best_local_action_match=validation.best_local_action_match,
            best_shared_action_match=validation.best_shared_action_match,
            all_profile_aggregates_match=validation.all_profile_aggregates_match,
            best_local_aggregate_match=validation.best_local_aggregate_match,
            best_shared_aggregate_match=validation.best_shared_aggregate_match,
            max_profile_squared_error_delta=
                validation.max_profile_squared_error_delta,
            max_profile_relative_rmse_delta=
                validation.max_profile_relative_rmse_delta,
            component_response_simulation_count=
                validation.component_response_simulation_count,
            naive_assembly_simulation_count=
                validation.naive_assembly_simulation_count,
            monolithic_truth_simulation_count=
                validation.monolithic_truth_simulation_count,
        ),
    )
end

"""Write immutable validation evidence bound to the frozen prediction hash."""
function write_compositional_validation(
    validation::PredictionValidation,
    frozen::CompositionalProtocolFreeze,
)
    validation.scope == EXACT_FACTORIZATION_SCOPE || error("validation scope mismatch")
    isfile(frozen.protocol_path) || error("the frozen protocol file is missing")
    isfile(frozen.prediction_path) || error("the frozen prediction file is missing")
    _sha256_file(frozen.protocol_path) == frozen.protocol_sha256 ||
        error("the frozen protocol hash no longer matches")
    _sha256_file(frozen.prediction_path) == frozen.prediction_sha256 ||
        error("the frozen prediction hash no longer matches")
    dirname(frozen.protocol_path) == dirname(frozen.prediction_path) ||
        error("frozen protocol and prediction files must share an output directory")

    path = _artifact_path(
        dirname(frozen.prediction_path),
        "compositional-validation.json",
    )
    bytes = _json_bytes(_validation_payload(validation, frozen))
    _freeze_artifact_set([(path, bytes)])
    return CompositionalValidationArtifact(
        path,
        bytes2hex(sha256(bytes)),
        frozen.protocol_sha256,
        frozen.prediction_sha256,
    )
end

end
