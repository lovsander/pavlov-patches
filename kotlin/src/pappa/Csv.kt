package pappa

import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path

/** Чтение CSV по заголовку и посекционный расчёт (как go/pappa/csv.go). */
object Csv {

    data class Row(val sectionId: Int, val heightMm: Double, val angleDeg: Double, val radiusMm: Double)

    /** Сечение + обученная модель + метаданные для документа. */
    data class SectionModel(
        val sectionId: Int, val heightMm: Double, val model: Model, val nPointsTotal: Int,
        val nOutliers: Int, val fitTimeMs: Double, val description: String,
        val pits: DoubleArray, val nUsed: Int,
    ) {
        override fun equals(other: Any?): Boolean = this === other
        override fun hashCode(): Int = System.identityHashCode(this)
    }

    /** Параметры посекционного расчёта: значения по умолчанию — как в референсе. */
    data class PipelineOptions(
        val model: Model.Options = Model.Options(),
        val cleaner: Cleaner.Options = Cleaner.Options(),
        val detector: Detector.Options = Detector.Options(),
        val pits: Boolean = true,
        val verbose: Boolean = true,
    )

    /** Чтение CSV ПО ЗАГОЛОВКУ (имена колонок, а не их порядок). */
    fun load(path: String): List<Row> {
        val lines = Files.readAllLines(Path.of(path), StandardCharsets.UTF_8).filter { it.isNotBlank() }
        require(lines.isNotEmpty()) { "пустой CSV: $path" }

        val head = lines[0].split(",")
        val index = HashMap<String, Int>()
        head.forEachIndexed { i, h -> index[h.trim()] = i }
        for (need in listOf("section_id", "height_mm", "angle_deg", "radius_mm")) {
            require(index.containsKey(need)) { "в CSV нет колонки \"$need\"" }
        }
        val iSec = index.getValue("section_id")
        val iH = index.getValue("height_mm")
        val iA = index.getValue("angle_deg")
        val iR = index.getValue("radius_mm")
        val need = maxOf(iSec, iH, iA, iR)

        val rows = ArrayList<Row>(lines.size - 1)
        for (k in 1 until lines.size) {
            val f = lines[k].split(",")
            if (f.size <= need) continue
            rows.add(Row(f[iSec].trim().toInt(), f[iH].trim().toDouble(),
                f[iA].trim().toDouble(), f[iR].trim().toDouble()))
        }
        require(rows.isNotEmpty()) { "в CSV нет строк с данными" }
        return rows
    }

    /** Посекционный расчёт: сортировка по углу, авто-очистка, детектор ям, обучение. */
    fun processSections(rows: List<Row>, opt: PipelineOptions = PipelineOptions()): List<SectionModel> {
        val bySection = LinkedHashMap<Int, MutableList<Row>>()
        for (r in rows) bySection.getOrPut(r.sectionId) { ArrayList() }.add(r)

        val out = ArrayList<SectionModel>(bySection.size)
        for ((sid, group) in bySection.toSortedMap()) {
            group.sortBy { it.angleDeg }
            val n = group.size
            val angles = DoubleArray(n) { group[it].angleDeg }
            val radii = DoubleArray(n) { group[it].radiusMm }

            val cl = Cleaner.cleanIqr(angles, radii, opt.cleaner)
            val aClean = ArrayList<Double>()
            val rClean = ArrayList<Double>()
            for (i in 0 until n) {
                if (cl.mask[i]) continue
                aClean.add(angles[i])
                rClean.add(radii[i])
            }
            val ang = aClean.toDoubleArray()
            val rad = rClean.toDoubleArray()

            val pits = if (opt.pits) Detector.pits(ang, rad, opt.detector) else DoubleArray(0)
            val model = Model(opt.model, pits)

            val t0 = System.nanoTime()
            model.fit(ang, rad)
            val fitMs = (System.nanoTime() - t0) / 1e6

            val sec = SectionModel(sid, group[0].heightMm, model, n, cl.nOutliers, fitMs,
                String.format("сечение %d, h=%.0f мм", sid, group[0].heightMm), pits, ang.size)
            if (opt.verbose) {
                println(String.format("  секция %d (h=%.0f мм): точек %d, выброшено %d, "
                        + "ям найдено %d, степени %s, обучение %.1f мс",
                    sid, sec.heightMm, n, cl.nOutliers, pits.size, model.degrees.contentToString(), fitMs))
            }
            out.add(sec)
        }
        return out
    }
}
