import Foundation
import Pappa

// Пайплайн PAPPA на Swift: CSV с сечениями -> папка образца.
// Пишет ТОТ ЖЕ формат, что референс Python и остальные порты:
//   <out-dir>/sample.json  +  <out-dir>/sections/NN.pappa.json
// Проверка: python python/studies/verify_port.py --cpp-dir <out-dir>
// Запуск: swift run pappa-cli --input FILE.csv --out-dir DIR [--name NAME]
//         [--description ТЕКСТ] [--no-pits] [--quiet]

func usage() {
    print("PAPPA (Swift): --input FILE.csv --out-dir DIR [--name NAME] "
        + "[--description ТЕКСТ] [--no-pits] [--quiet]")
}

let args = CommandLine.arguments
var input = ""
var outDir = ""
var name = "sample"
var description = "PAPPA Swift port"
var pits = true
var quiet = false

var i = 1
while i < args.count {
    switch args[i] {
    case "--input":
        i += 1
        if i < args.count { input = args[i] }
    case "--out-dir":
        i += 1
        if i < args.count { outDir = args[i] }
    case "--name":
        i += 1
        if i < args.count { name = args[i] }
    case "--description":
        i += 1
        if i < args.count { description = args[i] }
    case "--no-pits":
        pits = false
    case "--quiet":
        quiet = true
    default:
        usage()
        exit(2)
    }
    i += 1
}
if input.isEmpty || outDir.isEmpty {
    usage()
    exit(2)
}

do {
    let rows = try Csv.load(input)
    print("PAPPA (Swift): \(rows.count) точек, вход \(input)")

    var opt = PipelineOptions()
    opt.pits = pits
    opt.verbose = !quiet
    let sections = try Csv.processSections(rows, opt)

    var sample = Document.SampleOptions()
    sample.inputCsv = input
    sample.pits = pits
    sample.description = description
    sample.cleaner = opt.cleaner
    sample.detector = opt.detector

    let root = try Document.saveSample(outDir, name, sections, sample)
    print("\nОбразец записан: \(root)")
    print("  манифест: \(root)/sample.json")
    print("  сечений:  \(sections.count) (sections/*.pappa.json)")
    print("\nСверка с референсом Python:")
    print("  python python/studies/verify_port.py --cpp-dir \(root)")
} catch {
    FileHandle.standardError.write("Ошибка: \(error)\n".data(using: .utf8)!)
    exit(1)
}
