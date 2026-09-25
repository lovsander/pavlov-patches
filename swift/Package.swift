// swift-tools-version:5.9
// Пакет PAPPA на Swift: библиотека Pappa + два CLI + тесты.
// Зависимостей НЕТ (свой JSON/CSV), поэтому `swift build` не ходит в сеть.
import PackageDescription

let package = Package(
    name: "pappa",
    targets: [
        .target(name: "Pappa"),
        .executableTarget(name: "ConformanceCLI", dependencies: ["Pappa"]),
        .executableTarget(name: "PappaCLI", dependencies: ["Pappa"]),
        .testTarget(name: "PappaTests", dependencies: ["Pappa"]),
    ]
)
