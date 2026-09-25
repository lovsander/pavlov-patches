import Foundation

/// Чтение CSV по заголовку и посекционный расчёт (как go/pappa/csv.go).
public struct Row {
    public let sectionId: Int
    public let heightMm: Double
    public let angleDeg: Double
    public let radiusMm: Double
}

/// Сечение + обученная модель + метаданные для документа.
public final class SectionModel {
    public let sectionId: Int
    public let heightMm: Double
    public let model: Model
    public let nPointsTotal: Int
    public let nOutliers: Int
    public let nUsed: Int
    public let fitTimeMs: Double
    public let description: String
    public let pits: [Double]

    public init(sectionId: Int, heightMm: Double, model: Model, nPointsTotal: Int,
                nOutliers: Int, nUsed: Int, fitTimeMs: Double, description: String,
                pits: [Double]) {
        self.sectionId = sectionId
        self.heightMm = heightMm
        self.model = model
        self.nPointsTotal = nPointsTotal
        self.nOutliers = nOutliers
        self.nUsed = nUsed
        self.fitTimeMs = fitTimeMs
        self.description = description
        self.pits = pits
    }
}

/// Параметры посекционного расчёта: значения по умолчанию — как в референсе.
public struct PipelineOptions {
    public var model = Model.Options()
    public var cleaner = Cleaner.Options()
    public var detector = Detector.Options()
    public var pits = true
    public var verbose = true
    public init() {}
}

public enum Csv {

    /// Чтение CSV ПО ЗАГОЛОВКУ (имена колонок, а не их порядок).
    public static func load(_ path: String) throws -> [Row] {
        let text = try readText(path)
        // ВАЖНО: в Swift последовательность CRLF — ОДИН Character (графемный кластер),
        // поэтому сравнение с "\n"/"\r" не работает: файл выглядел бы одной строкой.
        // isNewline покрывает \n, \r, CRLF, NEL и прочие разделители строк.
        let lines = text.split(whereSeparator: { $0.isNewline })
            .map { String($0) }
            .filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
        guard let header = lines.first else {
            throw Linalg.PappaError("пустой CSV: \(path)")
        }

        func split(_ s: String) -> [String] {
            s.split(separator: ",", omittingEmptySubsequences: false)
                .map { $0.trimmingCharacters(in: .whitespaces) }
        }

        let head = split(header)
        func col(_ name: String) throws -> Int {
            guard let i = head.firstIndex(of: name) else {
                throw Linalg.PappaError("в CSV нет колонки \(name)")
            }
            return i
        }
        let iSec = try col("section_id")
        let iH = try col("height_mm")
        let iA = try col("angle_deg")
        let iR = try col("radius_mm")
        let need = max(max(iSec, iH), max(iA, iR))

        var rows: [Row] = []
        for line in lines.dropFirst() {
            let f = split(line)
            if f.count <= need { continue }
            guard let sec = Int(f[iSec]), let h = Double(f[iH]),
                  let a = Double(f[iA]), let r = Double(f[iR]) else {
                throw Linalg.PappaError("плохая строка CSV: \(line)")
            }
            rows.append(Row(sectionId: sec, heightMm: h, angleDeg: a, radiusMm: r))
        }
        if rows.isEmpty { throw Linalg.PappaError("в CSV нет строк с данными") }
        return rows
    }

    /// Посекционный расчёт: сортировка по углу, авто-очистка, детектор ям, обучение.
    public static func processSections(_ rows: [Row],
                                       _ opt: PipelineOptions = PipelineOptions())
        throws -> [SectionModel] {
        let ids = Set(rows.map { $0.sectionId }).sorted()
        var out: [SectionModel] = []

        for sid in ids {
            let group = rows.filter { $0.sectionId == sid }.sorted { $0.angleDeg < $1.angleDeg }
            let n = group.count
            let angles = group.map { $0.angleDeg }
            let radii = group.map { $0.radiusMm }

            let cl = Cleaner.cleanIqr(angles, radii, opt.cleaner)
            var aClean: [Double] = []
            var rClean: [Double] = []
            for i in 0..<n where !cl.mask[i] {
                aClean.append(angles[i])
                rClean.append(radii[i])
            }

            let pits = opt.pits ? Detector.pits(aClean, rClean, opt.detector) : []
            let model = Model(options: opt.model, pitsDeg: pits)

            let t0 = Date()
            try model.fit(aClean, rClean)
            let fitMs = Date().timeIntervalSince(t0) * 1000.0

            if opt.verbose {
                let degs = model.degrees().map { String($0) }.joined(separator: ", ")
                let h = Int(group[0].heightMm.rounded())
                let ms = (fitMs * 10).rounded() / 10
                print("  секция \(sid) (h=\(h) мм): точек \(n), выброшено \(cl.nOutliers), "
                    + "ям найдено \(pits.count), степени [\(degs)], обучение \(ms) мс")
            }
            out.append(SectionModel(sectionId: sid, heightMm: group[0].heightMm, model: model,
                                    nPointsTotal: n, nOutliers: cl.nOutliers, nUsed: aClean.count,
                                    fitTimeMs: fitMs,
                                    description: "сечение \(sid), h=\(Int(group[0].heightMm.rounded())) мм",
                                    pits: pits))
        }
        return out
    }
}
