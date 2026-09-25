# Swift порт PAPPA

Piecewise Adaptive Poly-Patch Approximation (PAPPA) на Swift — **полный порт**:
ядро метода (патчи с адаптивной степенью и нормированной координатой,
smoothstep-смешивание = partition of unity, фичер оконных гауссовых ям), детектор
трещин (band), авто-очистка выбросов (iqr) и пайплайн: CSV с сечениями → папка
образца в том же формате, что у референса Python и портов C++/C/Go/JS/Java/Kotlin/Rust/Pascal.

**Без зависимостей**: SwiftPM-пакет только со своими таргетами (свой JSON, свой CSV),
поэтому `swift build` не ходит в сеть. Проверено на **Swift 6.4 (swift-6.4-RELEASE)**
для `x86_64-unknown-windows-msvc`.

## Сборка и запуск

```powershell
powershell -File swift/build_swift.ps1            # swift build -c release
powershell -File swift/build_swift.ps1 -Test      # + swift test (XCTest)
powershell -File swift/build_swift.ps1 -Vectors   # + проверка конформанс-векторов
powershell -File swift/build_swift.ps1 -Clean     # пересобрать с нуля

.\swift\.build\release\ConformanceCLI.exe spec\conformance\vectors
.\swift\.build\release\PappaCLI.exe --input python\synthetic_data.csv `
    --out-dir samples\synthetic_sphere_swift --name synthetic_sphere
python python/studies/verify_port.py --py-dir samples/synthetic_sphere `
                                     --cpp-dir samples/synthetic_sphere_swift
```

**Про Windows-специфику запуска:** если вызывать `swift`/`.exe` вручную (не через
скрипт), нужно самим выставить окружение:

```powershell
$sb = "$env:LOCALAPPDATA\Programs\Swift"
$env:Path      = "$sb\Toolchains\6.4.0+Asserts\usr\bin;$sb\Runtimes\6.4.0\usr\bin;$env:Path"
$env:SDKROOT   = "$sb\Platforms\6.4.0\Windows.platform\Developer\SDKs\Windows.sdk"
```

Без `SDKROOT` компилятор падает с `unable to load standard library for target
'x86_64-unknown-windows-msvc'`; без `Runtimes\...\usr\bin` собранный `.exe` не стартует
(не находит `swiftCore.dll`).

Ключи пайплайна: `--input`, `--out-dir` (обязательны), `--name`, `--description`,
`--no-pits`, `--quiet`. По умолчанию — как в референсе: N=7, фаза 24.75°, степени
4…14, авто-iqr, фичер ям включён. CSV читается по заголовку: нужны колонки
`section_id, height_mm, angle_deg, radius_mm`.

## Результаты сверки (проверено на этом порте)

| Проверка | Результат |
|---|---|
| `ConformanceCLI.exe` | **4/4 OK** (прошёл с первого прогона) |
| вектор модели без ям | степени совпали, коэфф. `max|Δ| = 8.73e-11`, контур `3.02e-14 мм` |
| вектор модели с ямами | степени совпали, коэфф. `max|Δ| = 5.40e-10`, термины ям `4.36e-13`, контур `3.16e-13 мм` |
| вектор детектора | зон 2/2, ям 2/2, `max|Δ| = 0.00e+00°` |
| вектор очистки | выбросов 9/9, лишних 0, пропущено 0 |
| `swift test` | **3/3 passed** (векторы, гладкий контур, round-trip документа) |
| `PappaCLI.exe` (10 сечений × 6000 точек) | 10 сечений записано |
| `python/studies/verify_port.py` | **10/10 в допуске**, степени и число ям совпали, `max|Δr| = 1.339e-12 мм` (допуск 1e-6), код 0 |

## Состав

| Файл | Назначение |
|---|---|
| `Package.swift` | SwiftPM: библиотека `Pappa`, два CLI, тестовый таргет; зависимостей нет |
| `Sources/Pappa/Signal.swift` | медиана/перцентили/MAD/окна по кольцу/фильтры — как numpy |
| `Sources/Pappa/Linalg.swift` | МНК через QR (Хаусхолдер) + базис Чебышёва (схема Кленшоу) |
| `Sources/Pappa/Cleaner.swift` | авто-очистка выбросов (iqr) |
| `Sources/Pappa/Detector.swift` | детектор ям: узкая/широкая медиана → индикатор в MAD-ах → зоны |
| `Sources/Pappa/Model.swift` | `Model`: локальные степени, smoothstep-смешивание, фичер ям, метрики |
| `Sources/Pappa/Json.swift` | мини-JSON: `JsonValue` + парсер + запись, файловый ввод-вывод |
| `Sources/Pappa/Csv.swift` | чтение CSV по заголовку + посекционный расчёт |
| `Sources/Pappa/Document.swift` | документ `NN.pappa.json` и папка образца (`sample.json`) |
| `Sources/Pappa/Conformance.swift` | проверка конформанс-векторов (допуски как у остальных портов) |
| `Sources/ConformanceCLI/main.swift` | проверка порта по векторам (коды 0/1/2) |
| `Sources/PappaCLI/main.swift` | пайплайн: CSV → папка образца |
| `Tests/PappaTests/PappaTests.swift` | XCTest: векторы + гладкий контур + round-trip документа |
| `build_swift.ps1` | поиск тулчейна, `SDKROOT`, сборка, прогоны |

## Заметки по совместимости (что реально укусило)

* **`\r\n` в Swift — ОДИН `Character`** (CRLF является графемным кластером). Из-за
  этого разбор CSV через `split(whereSeparator: { $0 == "\n" })` дал **одну строку
  на весь файл** (в «заголовке» оказалось 660012 «колонок»), и пайплайн честно
  сказал «в CSV нет строк с данными». Лечится `whereSeparator: { $0.isNewline }`.
  Это самая коварная находка порта: ошибка выглядит как «данных нет», а не как
  ошибка разбора.
* **Округление окна** — `.rounded(.toNearestOrEven)`, а не `.rounded()`: последнее
  округляет половину **от нуля** (как Rust `round()` и Java `Math.round`), а Python
  `round(2.5) == 2`.
* **`key(key)` не компилируется**: параметр `key` затеняет метод `key(_:)` →
  «cannot call value of non-function type 'String'». Помогает явное `self.key(key)`.
* **Числа в документе** — `jsonNum`: целые без дробной части, иначе строковое
  представление Swift (shortest round-trip, как Python repr); очень большие/малые
  Swift печатает в экспоненте — это валидный JSON.
* **Дата в ISO** — свой расчёт (`civilFromDays`, алгоритм Хиннанта) от
  `Date().timeIntervalSince1970`: не зависим от локали и от настроек форматтера.
* **`pit_terms`** пишется у КАЖДОГО патча модели с ямами (включая пустой список) —
  этого требует загрузчик Python-референса; тест `testDocumentRoundTrip` это проверяет.
* **Свип степеней без QR**: одно накопление матрицы Грама в базисе Чебышёва на патч.
* Собранный `swift/.build` в git не попадает (см. корневой `.gitignore`).

## Лицензия

MIT + дополнительное условие об области применения: запрет использования ПО,
его производных, метода PAPPA и результатов его работы в военных системах,
произведённых вне Российской Федерации. Полный текст — в корневом `LICENSE`.
