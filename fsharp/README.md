# F# порт PAPPA

Piecewise Adaptive Poly-Patch Approximation (PAPPA) на F# (.NET) — **полный порт**:
ядро метода (патчи с адаптивной степенью и нормированной координатой,
smoothstep-смешивание = partition of unity, фичер оконных гауссовых ям), детектор
трещин (band), авто-очистка выбросов (iqr) и пайплайн: CSV с сечениями → папка
образца в том же формате, что у референса Python и портов C++/C/Go/JS/Java/Kotlin/
Rust/Pascal/Swift/Julia/R/C#/VBA/Octave.

**Зависимостей нет** — ни одного пакета NuGet: JSON (разбор и запись), CSV,
медианы/перцентили/MAD, МНК (QR Хаусхолдера) и «дата в ISO» написаны своими силами.
Поэтому `dotnet build` не ходит в сеть. Проверено на **.NET 10.0.401** (SDK) /
рантайме 10.0.12, цель `net10.0`, F# 10.

Числа обязаны совпадать с референсом, поэтому повторены тонкости numpy: медиана как
`np.median`, перцентиль с линейной интерполяцией, округление «половина к чётному»
в окне, круговые окна.

## Сборка и запуск

```powershell
powershell -File fsharp/build_fsharp.ps1              # сборка Release
powershell -File fsharp/build_fsharp.ps1 -Test        # сборка + SelfTest
powershell -File fsharp/build_fsharp.ps1 -Vectors     # сборка + конформанс-векторы
powershell -File fsharp/build_fsharp.ps1 -Pipeline    # сборка + samples/synthetic_sphere_fsharp
powershell -File fsharp/build_fsharp.ps1 -Clean       # пересобрать с нуля

# то же вручную
dotnet build fsharp/Pappa.fsproj -c Release
fsharp/bin/Release/net10.0/pappa.exe conformance spec/conformance/vectors
fsharp/bin/Release/net10.0/pappa.exe selftest    spec/conformance/vectors
fsharp/bin/Release/net10.0/pappa.exe pipeline --input python/synthetic_data.csv `
    --out-dir samples/synthetic_sphere_fsharp --name synthetic_sphere --quiet

python python/studies/verify_port.py --py-dir samples/synthetic_sphere `
                                     --cpp-dir samples/synthetic_sphere_fsharp
```

**Без PowerShell** (Linux/macOS/Git Bash) — тот же сценарий, ядро запускается через
`pappa.dll`, поэтому не зависит от apphost:

```bash
bash fsharp/build_fsharp.sh --vectors      # --test | --pipeline | --clean
dotnet fsharp/bin/Release/net10.0/pappa.dll pipeline --input python/synthetic_data.csv \
    --out-dir samples/synthetic_sphere_fsharp --name synthetic_sphere --quiet
```

Один exe, три команды (`--help` печатает справку):

| Команда | Что делает | Коды |
|---|---|---|
| `conformance [каталог-векторов]` | проверка порта по `spec/conformance/vectors` | `0`/`1`/`2` |
| `selftest [каталог-векторов]` | векторы + дымовой фит + round-trip документа | `0`/`1` |
| `pipeline --input F.csv --out-dir DIR [--name N] [--description Т] [--no-pits] [--quiet]` | CSV → папка образца | `0`/`2`/`1` |

По умолчанию — как в референсе: N = 7, фаза 24.75°, степени 4…14, авто-iqr, фичер
ям включён. CSV читается по заголовку: нужны колонки
`section_id, height_mm, angle_deg, radius_mm`.

## Результаты сверки (проверено на этом порте)

| Проверка | Результат |
|---|---|
| `pappa conformance` | **4/4 OK** (прошёл с первого прогона) |
| вектор модели без ям | степени совпали, коэфф. `max|Δ| = 8.73e-11`, контур `3.02e-14 мм` |
| вектор модели с ямами | степени совпали, коэфф. `max|Δ| = 5.40e-10`, термины ям `4.36e-13`, контур `3.16e-13 мм` |
| вектор детектора | зон 2/2, ям 2/2, `max|Δ| = 0.00e+00°` |
| вектор очистки | выбросов 9/9, лишних 0, пропущено 0 |
| `pappa selftest` | **все проверки зелёные** (векторы, дымовой фит, round-trip документа) |
| дымовой фит гладкой синусоиды | 7 патчей, `max|Δ| = 4.93e-07 мм` при пороге `1e-6` |
| `pappa pipeline` (10 сечений × 6000 точек) | 10 сечений за **1.3 с** |
| `python/studies/verify_port.py` | **10/10 в допуске**, степени и число ям совпали, `max|Δr| = 1.339e-12 мм` (допуск 1e-6), код 0 |
| `python spec/check_schema.py samples/synthetic_sphere_fsharp` | 11 файлов (манифест + 10 документов) по схемам, код 0 |
| `dotnet build` | 0 ошибок, 0 предупреждений |

Диагностика совпала с C#-портом до последней цифры (`8.73e-11`, `5.40e-10`,
`4.93e-07`, `1.339e-12`) — это ожидаемо: оба порта повторяют один алгоритм и один
порядок операций, поэтому совпадение битовое, а не «в пределах допуска».

## Состав

| Файл | Назначение |
|---|---|
| `src/Fmt.fs` | InvariantCulture, формат `%.2e`/`%.0f` своими руками |
| `src/Json.fs` | мини-JSON: разбор в размеченное объединение, доступ по ключам, запись чисел |
| `src/Linalg.fs` | МНК через QR (Хаусхолдер) + базис Чебышёва (схема Кленшоу) |
| `src/Signal.fs` | медиана/перцентили/MAD/окна по кольцу/фильтры — как numpy |
| `src/Analysis.fs` | модули `Cleaner` (авто-очистка iqr) и `Detector` (band → зоны → центры ям) |
| `src/Model.fs` | `Model`: локальные степени, smoothstep-смешивание, фичер ям, метрики |
| `src/Io.fs` | `Csv` (чтение по заголовку + посекционный расчёт) и `Document` (`pappa v2.0` + манифест) |
| `src/Cli.fs` | `Conformance`, `SelfTest`, `Program` (entry point, три подкоманды) |
| `Pappa.fsproj` | проект: `net10.0`, **явный порядок `<Compile>`**, `InvariantGlobalization`, без пакетов |
| `build_fsharp.ps1` | сборка и режимы `-Test` / `-Vectors` / `-Pipeline` / `-Clean` |
| `build_fsharp.sh` | тот же сценарий для Linux/macOS/Git Bash (без PowerShell) |

## Заметки по совместимости (ловушки F#)

Все пункты ниже проверены на этом порте (`dotnet fsi`-пробники и сам порт), а не
пересказаны из документации.

* **Порядок компиляции — часть языка.** Файл в F# видит только объявленное ВЫШЕ:
  циклических ссылок между файлами не бывает, forward-деклараций внутри файла нет,
  типы обязаны стоять до класса, который их использует (`Options` → `Model`).
  Поэтому в `.fsproj` список `<Compile>` задан явно, а
  `EnableDefaultCompileItems=false`: иначе SDK добавит `*.fs` по алфавиту и сборка
  развалится на «not defined».
* **`round` уже банковский.** `round 2.5 = 2`, `round 3.5 = 4` — это ровно
  `Math.Round(x, MidpointRounding.ToEven)`. Ловушка здесь обратна C#-мифу: у
  `Math.Round(x)` **без** второго аргумента поведение тоже «к чётному»
  (`Math.Round(2.5) = 2` — проверено на .NET 10). Половину ОТ НУЛЯ дают `round` в
  C/Go/Rust/Octave и `Math.round` в JS — вот их и приходится эмулировать.
* **Культура: printf и `ToString` ведут себя ПРОТИВОПОЛОЖНО C#.** В F#
  `sprintf "%f"`/`"%.2e"` инвариантны к культуре (`1.5 → 1.500000` даже при
  `ru-RU`), а `ToString()`/`Parse()` — зависят от неё (`1,5` при `ru-RU`). В C#
  всё наоборот. Вывод: в F# безопасны `sprintf`-форматы, но обязателен явный
  `CultureInfo.InvariantCulture` в каждом `ToString`/`Parse` (и `InvariantGlobalization`
  в `.fsproj` как страховка).
* **`sprintf "%.2e"` печатает по-сишному** — с трёхзначным порядком
  (`8.73e-011`), тогда как numpy/Python и остальные порты печатают `8.73e-11`.
  Для сравнимости диагностики написан свой `Fmt.e` со спецификатором `"0.00e+00"`.
* **Нет `break`/`continue`/раннего `return`.** Разбор аргументов CLI и поиск
  «локтя» переписаны через флаги (`badArgs`, `found`) вместо `break`.
* **Нет `object`-боксинга.** JSON — размеченное объединение `JVal` с
  сопоставлением с образцом: `JOfObj` (`Dictionary`), `JOfArr` (`list`), `JOfNum`,
  `JOfStr`, `JOfBool`, `JNull`. Попытка повторить C#-версию на `object` дала бы
  десятки приведений типов и `InvalidCastException` вместо ошибки компиляции.
* **Члены класса видят друг друга только через self-идентификатор.**
  `member this.Fit` внутри вызывает `this.WindowOf`/`this.PitShapeDeg`; `member _.X`
  для этого не годится. Состояние — `let mutable` + `member … with get() and set()`
  (автосвойств нет).
* **`try … with … finally` не совмещается.** В F# это два разных `try`, поэтому
  round-trip документа обёрнут вложенно, иначе компилятор требует один из двух.
* **`string true` = `"True"`** — в JSON нужен `Fmt.boolStr` (та же ловушка, что в
  C#-порте, где `StringBuilder.Append(bool)` печатает `True`).
* **`Array.Sort` неустойчив** (как и в .NET из C#), поэтому сортировка точек
  сечения по углу сделана через `Seq.sortBy` — устойчивую сортировку
  FSharp.Core: при равных углах сохраняется порядок файла, а от него зависит
  `height_mm` «первой» строки.
* **PowerShell-ловушка в `build_fsharp.ps1`**: функция вида
  `& $app …; return $LASTEXITCODE` захватывает в свой выход ВЕСЬ вывод приложения,
  и сравнение с `0` начинает врать (у меня это дало вечный `throw`). Обёртки-функции
  нет: префикс команды собирается в массив, а код берётся из `$LASTEXITCODE`.
* **Запуск без apphost.** На Linux/macOS `pappa` (apphost) может не собраться, а
  `pappa.dll` есть всегда — `build_fsharp.sh` запускает именно dll через `dotnet`.
  В `build_fsharp.ps1` есть такой же запасной путь.
* **Кириллица.** Исходники UTF-8 без BOM, вывод в консоль — через
  `Console.OutputEncoding = UTF8Encoding(false)`. В Windows PowerShell 5.1
  диагностика всё равно может показаться кракозябрами (файл читается как ANSI):
  на ворота это не влияет — `verify_all.ps1` смотрит на код возврата.
* Собранные `fsharp/bin` и `fsharp/obj` в git не попадают (см. корневой `.gitignore`).

## Лицензия

MIT + дополнительное условие об области применения: запрет использования ПО,
его производных, метода PAPPA и результатов его работы в военных системах,
произведённых вне Российской Федерации. Полный текст — в корневом `LICENSE`.

