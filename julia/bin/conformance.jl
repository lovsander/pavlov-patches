# Проверка Julia-порта PAPPA по конформанс-векторам.
# Запуск: julia --project=julia julia/bin/conformance.jl [каталог с векторами]
# Коды:   0 — всё сошлось; 1 — расхождения; 2 — нет каталога.

using Pappa

function main()
    dir = length(ARGS) >= 1 ? ARGS[1] :
          joinpath(@__DIR__, "..", "..", "spec", "conformance", "vectors")

    vectors = try
        Conformance.load_vectors(dir)
    catch e
        println("нет каталога векторов: $dir ($e)")
        return 2
    end

    println("Julia-порт PAPPA: $(length(vectors)) векторов (pappa $(Pappa.PORT_VERSION), Julia $(VERSION))")

    bad = 0
    for v in vectors
        r = Conformance.check_vector(v.data)
        r.ok || (bad += 1)
        println(rpad(v.file, 46), " ", r.ok ? "OK   " : "FAIL ", r.detail)
        for note in Iterators.take(r.notes, 4)
            println(repeat(" ", 52), "-> ", note)
        end
    end
    println(bad == 0 ? "ВЫВОД: Julia-порт проходит все векторы" : "ВЫВОД: расхождений $bad")
    bad == 0 ? 0 : 1
end

exit(main())
