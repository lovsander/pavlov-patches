# Тесты Julia-порта: конформанс-векторы + дымовые проверки.
# Запуск: julia --project=julia julia/test/runtests.jl
#     или: julia --project=julia -e 'using Pkg; Pkg.test()'

using Test
using Pappa

const VECTORS = normpath(joinpath(@__DIR__, "..", "..", "spec", "conformance", "vectors"))

@testset "конформанс-векторы" begin
    vectors = Conformance.load_vectors(VECTORS)
    @test length(vectors) >= 4
    for v in vectors
        r = Conformance.check_vector(v.data)
        @test r.ok
        r.ok || @info "$(v.file): $(r.detail) $(join(r.notes, "; "))"
    end
end

@testset "гладкая синусоида воспроизводится" begin
    angles = collect(0.0:1.0:359.0)
    radii = [50 + 0.4 * sin(a * pi / 180) for a in angles]
    m = Model.Model()
    Model.fit!(m, angles, radii)
    @test length(m.patches) == 7
    curve = Model.eval_model(m, angles)
    max_err = maximum(abs.(curve .- radii))
    @test max_err < 1e-6
end

@testset "документ: формат и контракт pit_terms" begin
    csv_path = joinpath(mktempdir(), "smoke.csv")
    open(csv_path, "w") do io
        println(io, "section_id,height_mm,angle_deg,radius_mm")
        for i in 0:359
            println(io, "0,7.5,$i,$(40 + 0.2 * sin(i))")
        end
    end
    rows = Csv.load_csv(csv_path)
    @test length(rows) == 360
    sections = Csv.process_sections(rows, Csv.PipelineOptions(; verbose = false))

    out = joinpath(mktempdir(), "sample")
    Document.save_sample(out, "smoke", sections,
                         Document.SampleOptions(; input_csv = csv_path))

    manifest = read(joinpath(out, "sample.json"), String)
    @test occursin("\"format\": \"pappa-sample\"", manifest)
    section = read(joinpath(out, "sections", "00.pappa.json"), String)
    @test occursin("\"format\": \"pappa\"", section)
    @test occursin("\"statistics\"", section)

    # Контракт: pit_terms есть у КАЖДОГО патча (7), когда модель с ямами, и нет иначе.
    has_pits = Model.has_pits(sections[1].model)
    @test count("\"pit_terms\"", section) == (has_pits ? 7 : 0)
end
