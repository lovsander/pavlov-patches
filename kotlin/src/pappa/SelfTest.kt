package pappa

import java.nio.file.Files
import java.nio.file.Path
import java.util.Locale

/**
 * Самопроверка без внешних зависимостей (JUnit не тащим): конформанс-векторы +
 * дымовой тест пайплайна. Запуск: java -cp out pappa.SelfTest
 * Код возврата: 0 — всё прошло, 1 — расхождения.
 */
object SelfTest {

    private var failures = 0

    private fun check(ok: Boolean, what: String) {
        println("  ${if (ok) "[ok]" else "[FAIL]"} $what")
        if (!ok) failures++
    }

    @JvmStatic
    fun main(args: Array<String>) {
        Locale.setDefault(Locale.ROOT)
        val vecDir = Path.of(if (args.isNotEmpty()) args[0] else "../spec/conformance/vectors")
        println("Kotlin SelfTest: ${vecDir.toAbsolutePath()}")

        val vectors = Conformance.load(vecDir)
        println("векторы конформанса (${vectors.size}):")
        check(vectors.size >= 4, "не меньше 4 векторов")
        for (v in vectors) {
            val r = Conformance.check(v.data)
            check(r.ok, "${v.file} — ${r.detail}")
        }

        println("дымовой тест пайплайна (гладкая синусоида, 360 точек):")
        val csv = StringBuilder("section_id,height_mm,angle_deg,radius_mm\n")
        for (i in 0 until 360) {
            csv.append(String.format("0,0,%d,%.6f%n", i, 50 + 0.4 * Math.sin(i * Math.PI / 180)))
        }
        val tmp = Files.createTempFile("pappa_kotlin_selftest", ".csv")
        Files.writeString(tmp, csv.toString())
        val rows = Csv.load(tmp.toString())
        Files.deleteIfExists(tmp)
        check(rows.size == 360, "разбор CSV: 360 точек")

        val angles = DoubleArray(rows.size) { rows[it].angleDeg }
        val radii = DoubleArray(rows.size) { rows[it].radiusMm }
        val m = Model().fit(angles, radii)
        check(m.patches.size == 7, "патчей ${m.patches.size}")
        val curve = m.eval(angles)
        var maxErr = 0.0
        for (i in radii.indices) maxErr = Math.max(maxErr, Math.abs(curve[i] - radii[i]))
        check(maxErr < 1e-6, String.format("контур гладкой синусоиды: max|Δ| = %.2e мм", maxErr))

        println(if (failures == 0) "ВЫВОД: SelfTest пройден" else "ВЫВОД: провалов $failures")
        kotlin.system.exitProcess(if (failures == 0) 0 else 1)
    }
}
