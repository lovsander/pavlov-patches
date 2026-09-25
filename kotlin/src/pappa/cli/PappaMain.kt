@file:JvmName("PappaMain")

package pappa.cli

import java.util.Locale

import pappa.Csv
import pappa.Document

/**
 * Пайплайн PAPPA на Kotlin: CSV с сечениями → папка образца.
 *
 * Пишет ТОТ ЖЕ формат, что референс Python и порты C++/C/Go/JS/Java:
 *   <out-dir>/sample.json  +  <out-dir>/sections/NN.pappa.json
 *
 * Проверка: python python/studies/verify_port.py --py-dir <эталон> --cpp-dir <out-dir>
 *
 * Запуск: java -cp out pappa.cli.PappaMain --input python/synthetic_data.csv \
 *         --out-dir samples/synthetic_sphere_kotlin --name synthetic_sphere
 */
fun main(args: Array<String>) {
    Locale.setDefault(Locale.ROOT)   // стабильный вывод (точка, а не запятая) при любой локали
    var input: String? = null
    var outDir: String? = null
    var name = "sample"
    var description = "PAPPA Kotlin port"
    var pits = true
    var quiet = false

    var i = 0
    while (i < args.size) {
        when (args[i]) {
            "--input" -> input = args[++i]
            "--out-dir" -> outDir = args[++i]
            "--name" -> name = args[++i]
            "--description" -> description = args[++i]
            "--no-pits" -> pits = false
            "--quiet" -> quiet = true
            else -> {
                usage()
                kotlin.system.exitProcess(2)
            }
        }
        i++
    }
    if (input == null || outDir == null) {
        usage()
        kotlin.system.exitProcess(2)
    }

    val rows = Csv.load(input!!)
    println("PAPPA (Kotlin): ${rows.size} точек, вход $input")

    val opt = Csv.PipelineOptions(pits = pits, verbose = !quiet)
    val sections = Csv.processSections(rows, opt)
    val root = Document.saveSample(outDir!!, name, sections,
        Document.SampleOptions(name, input!!, pits, description, opt.cleaner, opt.detector))

    println("\nОбразец записан: $root")
    println("  манифест: $root/sample.json")
    println("  сечений:  ${sections.size} (sections/*.pappa.json)")
    println("\nСверка с референсом Python:")
    println("  python python/studies/verify_port.py --cpp-dir $root")
}

private fun usage() {
    println("PAPPA (Kotlin): --input FILE.csv --out-dir DIR [--name NAME] "
        + "[--description ТЕКСТ] [--no-pits] [--quiet]")
}
