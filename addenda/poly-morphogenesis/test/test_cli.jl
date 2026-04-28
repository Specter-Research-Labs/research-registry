using PolyMorphogenesis
using Test

function _capture_error(f)
    try
        f()
        return nothing
    catch err
        return sprint(showerror, err)
    end
end

@testset "cli main smoke" begin
    tempdir = mktempdir()
    redirect_stdout(devnull) do
        @test isnothing(main(["demo", "wave-count", "--peaks", "3"]))
        @test isnothing(main(["diagrams", "--base-dir", tempdir, "--n-cells", "4"]))
    end
    @test isfile(joinpath(tempdir, "docs", "diagrams", "rd_default.dot"))
    @test isfile(joinpath(tempdir, "docs", "diagrams", "wave_default.dot"))
end

@testset "cli missing or invalid flag values" begin
    err = _capture_error() do
        main(["demo", "wave-count", "--peaks"])
    end
    @test !isnothing(err)
    @test occursin("missing value for `--peaks`", err)

    err = _capture_error() do
        main(["demo", "fragment-family", "--left-cuts"])
    end
    @test !isnothing(err)
    @test occursin("missing value for `--left-cuts`", err)

    err = _capture_error() do
        main(["demo", "cut-sweep", "--validation-mode", "bad"])
    end
    @test !isnothing(err)
    @test occursin("validation mode must be one of none, auto, all", err)

    err = _capture_error() do
        main(["demo", "grid-patch-sweep", "--patch-sizes", "bad"])
    end
    @test !isnothing(err)
    @test occursin("expected patch sizes formatted as HxW,HxW,...", err)

    err = _capture_error() do
        main(["demo", "grid-patch-sensitivity", "--metrics", "bad"])
    end
    @test !isnothing(err)
    @test occursin("expected metrics drawn from balanced, structure, profile", err)

    err = _capture_error() do
        main(["demo", "grid-patch-threshold-sensitivity", "--active-fractions", ""])
    end
    @test !isnothing(err)
    @test occursin("expected at least one float", err)
end
