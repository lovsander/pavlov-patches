import Foundation
import Pappa

// Проверка Swift-порта PAPPA по конформанс-векторам.
// Запуск: swift run conformance [каталог с векторами]
// Коды:   0 — всё сошлось; 1 — расхождения; 2 — нет каталога.

let args = CommandLine.arguments
let dir = args.count > 1 ? args[1] : "../spec/conformance/vectors"

do {
    let vectors = try Conformance.load(dir)
    print("Swift-порт PAPPA: \(vectors.count) векторов (pappa \(Document.portVersion))")

    var bad = 0
    for v in vectors {
        let r = try Conformance.check(v.data)
        if !r.ok { bad += 1 }
        var name = v.file
        while name.count < 46 { name += " " }
        print("\(name) \(r.ok ? "OK   " : "FAIL ") \(r.detail)")
        for note in r.notes.prefix(4) {
            print(String(repeating: " ", count: 52) + "-> " + note)
        }
    }
    print(bad == 0 ? "ВЫВОД: Swift-порт проходит все векторы"
          : "ВЫВОД: расхождений \(bad)")
    exit(bad == 0 ? 0 : 1)
} catch {
    print("нет каталога векторов: \(dir)")
    exit(2)
}
