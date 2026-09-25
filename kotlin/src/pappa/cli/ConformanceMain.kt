@file:JvmName("ConformanceMain")

package pappa.cli

import java.nio.file.Files
import java.nio.file.Path
import java.util.Locale

import pappa.Conformance

/**
 * Проверка Kotlin-порта PAPPA по конформанс-векторам.
 * Запуск: java -cp out pappa.cli.ConformanceMain [каталог с векторами]
 * Коды:   0 — всё сошлось; 1 — расхождения; 2 — нет каталога.
 */
fun main(args: Array<String>) {
    Locale.setDefault(Locale.ROOT)   // вывод не должен зависеть от локали (ru-RU дал бы "8,73e-11")
    val vecDir = Path.of(if (args.isNotEmpty()) args[0] else "../spec/conformance/vectors")
    if (!Files.isDirectory(vecDir)) {
        println("нет каталога векторов: $vecDir")
        kotlin.system.exitProcess(2)
    }
    val vectors = Conformance.load(vecDir)
    println("Kotlin-порт PAPPA: ${vectors.size} векторов (Kotlin, JVM ${System.getProperty("java.version")})")

    var bad = 0
    for (v in vectors) {
        val r = Conformance.check(v.data)
        if (!r.ok) bad++
        println(String.format("%-46s %-5s %s", v.file, if (r.ok) "OK" else "FAIL", r.detail))
        for (n in r.notes.take(4)) println(" ".repeat(52) + "-> " + n)
    }
    println(if (bad == 0) "ВЫВОД: Kotlin-порт проходит все векторы" else "ВЫВОД: расхождений $bad")
    kotlin.system.exitProcess(if (bad == 0) 0 else 1)
}
