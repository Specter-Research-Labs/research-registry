using PolyMorphogenesis
using Test

const PMAlgebra = PolyMorphogenesis.Algebra

@testset "core lenses" begin
    schema = PMAlgebra.PortSchema([:x], [:y])
    identity = PMAlgebra.identity_lens(schema)
    outputs = Dict(:y => 3)
    @test identity.forward(outputs) == Dict(:y => 3)
    @test identity.backward(Dict(), Dict(:x => 9)) == Dict(:x => 9)

    left = PMAlgebra.DependentLens(
        :left,
        schema,
        schema,
        outputs -> Dict(:y => get(outputs, :y, 0) + 1),
        (state, incoming) -> Dict(:x => get(incoming, :x, 0) + 1),
    )
    right = PMAlgebra.DependentLens(
        :right,
        schema,
        schema,
        outputs -> Dict(:y => get(outputs, :y, 0) * 2),
        (state, incoming) -> Dict(:x => get(incoming, :x, 0) * 2),
    )
    composed = PMAlgebra.compose_lenses(left, right)
    @test composed.forward(Dict(:y => 2)) == Dict(:y => 6)
end

@testset "compose_lenses backward uses forward-transformed state" begin
    schema = PMAlgebra.PortSchema([:x], [:y])
    tracker = Ref(:none)
    left = PMAlgebra.DependentLens(
        :left,
        schema,
        schema,
        outputs -> merge(outputs, Dict(:via_left => true)),
        (state, incoming) -> incoming,
    )
    right = PMAlgebra.DependentLens(
        :right,
        schema,
        schema,
        outputs -> outputs,
        (state, incoming) -> begin
            tracker[] = haskey(state, :via_left) ? :correct : :wrong
            return incoming
        end,
    )
    composed = PMAlgebra.compose_lenses(left, right)
    composed.backward(Dict(:y => 1), Dict(:x => 2))
    @test tracker[] == :correct
end

@testset "lens laws" begin
    schema = PMAlgebra.PortSchema([:value], [:value])
    identity = PMAlgebra.identity_lens(schema)
    state = Dict(:value => 5)
    incoming = Dict(:value => 3)

    @test identity.backward(state, identity.forward(state)) == state

    updated = identity.backward(state, incoming)
    @test identity.forward(updated) == incoming

    once = identity.backward(state, incoming)
    twice = identity.backward(once, incoming)
    @test once == twice
end

@testset "lax monoidal functor types" begin
    attractor_functor = PMAlgebra.LaxMonoidalFunctor(:attractor_set, compiled -> Set([:one_head]))
    @test attractor_functor.name == :attractor_set
    @test attractor_functor.map(nothing) == Set([:one_head])

    laxator = PMAlgebra.Laxator(
        :emergence,
        (compiled_ab, compiled_a, compiled_b) -> begin
            f_ab = attractor_functor.map(compiled_ab)
            f_a = attractor_functor.map(compiled_a)
            f_b = attractor_functor.map(compiled_b)
            return setdiff(f_ab, union(f_a, f_b))
        end,
    )
    @test laxator.name == :emergence
    @test laxator.measure(:ab, :a, :b) == Set{Symbol}()
end
