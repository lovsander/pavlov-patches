import XCTest
import Foundation
@testable import Pappa

/// Тесты: конформанс-векторы + дымовые проверки (гладкий контур, round-trip документа).
/// Путь к векторам вычисляется от #filePath, поэтому `swift test` работает из любой папки.
final class PappaTests: XCTestCase {

    private func vectorsDir() -> String {
        // .../swift/Tests/PappaTests/PappaTests.swift -> .../spec/conformance/vectors
        let here = URL(fileURLWithPath: #filePath)
        let repo = here.deletingLastPathComponent()   // PappaTests
            .deletingLastPathComponent()              // Tests
            .deletingLastPathComponent()              // swift
            .deletingLastPathComponent()              // repo root
        return repo.appendingPathComponent("spec/conformance/vectors").path
    }

    func testPassesAllVectors() throws {
        let vectors = try Conformance.load(vectorsDir())
        XCTAssertGreaterThanOrEqual(vectors.count, 4, "ожидались минимум 4 вектора")
        for v in vectors {
            let r = try Conformance.check(v.data)
            XCTAssertTrue(r.ok, "\(v.file): \(r.detail) \(r.notes.joined(separator: "; "))")
        }
    }

    func testSmoothSineIsReproduced() throws {
        var angles: [Double] = []
        var radii: [Double] = []
        for i in 0..<360 {
            let a = Double(i)
            angles.append(a)
            radii.append(50 + 0.4 * sin(a * Double.pi / 180))
        }
        let m = Model()
        try m.fit(angles, radii)
        XCTAssertEqual(m.patches.count, 7)

        let curve = try m.eval(angles)
        var maxErr = 0.0
        for i in 0..<radii.count { maxErr = max(maxErr, abs(curve[i] - radii[i])) }
        XCTAssertLessThan(maxErr, 1e-6, "контур гладкой синусоиды: max|Δ| = \(maxErr)")
    }

    func testDocumentRoundTrip() throws {
        var csv = "section_id,height_mm,angle_deg,radius_mm\n"
        for i in 0..<360 {
            csv += "0,7.5,\(i),\(40 + 0.2 * sin(Double(i)))\n"
        }
        let tmpCsv = FileManager.default.temporaryDirectory
            .appendingPathComponent("pappa_swift_smoke.csv")
        try writeText(tmpCsv.path, csv)

        let rows = try Csv.load(tmpCsv.path)
        var opt = PipelineOptions()
        opt.verbose = false
        let sections = try Csv.processSections(rows, opt)

        let outDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("pappa_swift_doc_smoke")
        try? FileManager.default.removeItem(at: outDir)
        var sample = Document.SampleOptions()
        sample.inputCsv = tmpCsv.path
        _ = try Document.saveSample(outDir.path, "smoke", sections, sample)

        let manifest = try readText(outDir.appendingPathComponent("sample.json").path)
        XCTAssertTrue(manifest.contains("\"format\": \"pappa-sample\""))
        let section = try readText(outDir.appendingPathComponent("sections/00.pappa.json").path)
        XCTAssertTrue(section.contains("\"format\": \"pappa\""))
        XCTAssertTrue(section.contains("\"statistics\""))

        // Контракт: pit_terms есть у КАЖДОГО патча (7), когда модель с ямами, и нет иначе.
        let hasPits = sections[0].model.hasPits
        let count = section.components(separatedBy: "\"pit_terms\"").count - 1
        XCTAssertEqual(count, hasPits ? 7 : 0)

        try? FileManager.default.removeItem(at: tmpCsv)
        try? FileManager.default.removeItem(at: outDir)
    }
}
