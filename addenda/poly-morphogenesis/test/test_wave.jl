
using PolyMorphogenesis
using Test

function synthetic_profile(peaks::Int; cells_per_peak::Int=12)
    A = Float64[]
    for _ in 1:(peaks - 1)
        append!(A, collect(range(0.0, 1.0; length=cells_per_peak + 1))[1:end-1])
        append!(A, collect(range(1.0, 0.0; length=cells_per_peak + 1)))
    end
    append!(A, collect(range(0.0, 1.0; length=cells_per_peak + 1)))
    return A
end

@testset "wave counts peaks" begin
    single = wave_count(synthetic_profile(1))
    triple = wave_count(synthetic_profile(3))
    quintuple = wave_count(synthetic_profile(5))
    @test single.count == 1.0
    @test triple.count == 3.0
    @test quintuple.count == 5.0
    @test all(triple.done)
end

@testset "wave composed plan matches procedural path" begin
    for peaks in [1, 3, 5]
        profile = synthetic_profile(peaks)
        ref = wave_count(profile)
        plan = PolyMorphogenesis.Wave.compile_wave_plan(WaveConfig(), length(profile))
        composed = PolyMorphogenesis.Wave.wave_count_composed(profile, WaveConfig())
        normalized_composed = PolyMorphogenesis.Wave.wave_count_composed_from_normalized(plan, ref.input_A)
        @test composed.count == ref.count
        @test composed.final_pre ≈ ref.final_pre atol=1e-12
        @test composed.final_sig ≈ ref.final_sig atol=1e-12
        @test composed.final_amdr ≈ ref.final_amdr atol=1e-12
        @test composed.emitted == ref.emitted
        @test composed.done == ref.done
        @test normalized_composed.count == ref.count
    end
end

@testset "wave phase outputs expose controller-facing summary" begin
    result = wave_count(synthetic_profile(3))
    outputs = PolyMorphogenesis.Wave.wave_phase_outputs(result)
    @test outputs[:peak_count] == 3.0
    @test outputs[:emitted] == result.emitted
    @test outputs[:done] == result.done
end

@testset "wave can still normalize explicitly for exploratory use" begin
    profile = 0.6 .* synthetic_profile(3)
    raw = wave_count(profile)
    normalized = wave_count(profile, WaveConfig(normalize_input=true))

    @test raw.input_A ≈ profile
    @test raw.normalized_A ≈ PolyMorphogenesis.Wave.normalize_profile(profile)
    @test normalized.input_A ≈ profile
    @test normalized.normalized_A ≈ PolyMorphogenesis.Wave.normalize_profile(profile)
end
