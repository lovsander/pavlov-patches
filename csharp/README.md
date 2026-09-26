# C# порт PAPPA

Piecewise Adaptive Poly-Patch Approximation (PAPPA) на C# (.NET) — **полный порт**:
ядро метода (патчи с адаптивной степенью и нормированной координатой,
smoothstep-смешивание = partition of unity, фичер оконных гауссовых ям), детектор
трещин (band), авто-очистка выбросов (iqr) и пайплайн: CSV с сечениями → папка
образца в том же формате, что у референса Python и портов C++/C/Go/JS/Java/Kotlin/
Rust/Pascal/Swift/Julia/R.

**Зависимостей нет** — ни одного пакета NuGet: JSON (разбор и запись), CSV,
медианы/перцентили/MAD, МНК (QR Хаусхолдера) и «дата в ISO» написаны своими силами.
Поэтому `dotnet build` не ходит в сеть. Проверено на **.NET 10.0.401** (SDK) /
рантайме 10.0.12, цель `net10.0`.

Числа обязаны совпадать с референсом, поэтому повторены тонкости numpy: медиана как
`np.median`, перцентиль с линейной интерполяцией, округление «половина к чётному»
в окне, круговые окна.

## Сборка и запуск

```powershell
powershell -File csharp/build.ps1              # сборка Release
powershell -File csharp/build.ps1 -Test        # сборка + SelfTest
powershell -File csharp/build.ps1 -Vectors     # сборка + конформанс-векторы
powershell -File csharp/build.ps1 -Pipeline    # сборка + samples/synthetic_sphere_csharp
powershell -File csharp/build.ps1 -Clean       # пересобрать с нуля

# то же вручную
dotnet build csharp/Pappa.csproj -c Release
csharp/bin/Release/net10.0/pappa.exe conformance spec/conformance/vectors
csharp/bin/Release/net10.0/pappa.exe selftest    spec/conformance/vectors
csharp/bin/Release/net10.0/pappa.exe pipeline --input python/synthetic_data.csv `
    --out-dir samples/synthetic_sphere_csharp --name synthetic_sphere --quiet

python python/studies/verify_port.py --py-dir samples/synthetic_sphere `
                                     --cpp-dir samples/synthetic_sphere_csharp
```

Один exe, три команды (`--help` печатает справку):

| Команда | Что делает | Коды |
|---|---|---|
| `conformance [каталог-векторов]` | проверка порта по `spec/conformance/vectors` | `0`/`1`/`2` |
| `selftest [каталог-векторов]` | векторы + дымовой фит + round-trip документа | `0`/`1` |
| `pipeline --input F.csv --out-dir DIR [--name N] [--description Т] [--no-pits] [--quiet]` | CSV → папка образца | `0`/`2`/`1` |

Почему подкоманды, а не три бинарника: .NET-проект с несколькими `Main` собирается
только через `StartupObject`, а один exe с командами читается так же, как
`pappa_conformance`/`pappa_pipeline` у C++.

По умолчанию — как в референсе: N = 7, фаза 24.75°, степени 4…14, авто-iqr, фичер
ям включён. CSV читается по заголовку: нужны колонки
`section_id, height_mm, angle_deg, radius_mm`.

## Результаты сверки (проверено на этом порте)

| Проверка | Результат |
|---|---|
| `pappa.exe conformance` | **4/4 OK** (прошёл с первого прогона) |
| вектор модели без ям | степени совпали, коэфф. `max|Δ| = 8.73e-11`, контур `3.02e-14 мм` |
| вектор модели с ямами | степени совпали, коэфф. `max|Δ| = 5.40e-10`, термины ям `4.36e-13`, контур `3.16e-13 мм` |
| вектор детектора | зон 2/2, ям 2/2, `max|Δ| = 0.00e+00°` |
| вектор очистки | выбросов 9/9, лишних 0, пропущено 0 |
| `pappa.exe selftest` | **все проверки зелёные** (векторы, дымовой фит, round-trip документа) |
| дымовой фит гладкой синусоиды | 7 патчей, `max|Δ| = 4.93e-07 мм` при пороге `1e-6` |
| `pappa.exe pipeline` (10 сечений × 6000 точек) | 10 сечений за **1.05 с** (~0.1 с на сечение) |
| `python/studies/verify_port.py` | **10/10 в допуске**, степени и число ям совпали, `max|Δr| = 1.339e-12 мм` (допуск 1e-6), код 0 |
| `python spec/check_schema.py` | документы и манифест по схемам, инварианты выполнены |

## Состав

| Файл | Назначение |
|---|---|
| `src/Signal.cs` | медиана/перцентили/MAD/окна по кольцу/фильтры — как numpy |
| `src/Linalg.cs` | МНК через QR (Хаусхолдер) + базис Чебышёва (схема Кленшоу) |
| `src/Cleaner.cs` | авто-очистка выбросов (iqr): медианный фильтр + усы Тьюки |
| `src/Detector.cs` | детектор ям: узкая/широкая медиана → индикатор в MAD-ах → зоны |
| `src/Model.cs` | `Model`: локальные степени, smoothstep-смешивание, фичер ям, метрики |
| `src/Json.cs`, `src/JsonParser.cs` | мини-JSON: разбор (`Dictionary`/`List`/`double`) и запись |
| `src/Fmt.cs` | InvariantCulture и формат `%.2e` для диагностики |
| `src/Csv.cs` | чтение CSV по заголовку + посекционный расчёт |
| `src/Document.cs` | документ `NN.pappa.json` и папка образца (`sample.json`) |
| `src/Conformance.cs` | проверка конформанс-векторов (допуски как у остальных портов) |
| `src/SelfTest.cs` | векторы + дымовой фит + round-trip документа (без xUnit/NUnit) |
| `src/Cli/Program.cs` | точка входа: `conformance` / `selftest` / `pipeline` |
| `Pappa.csproj` | проект: `net10.0`, `InvariantGlobalization`, `UseAppHost`, без пакетов |
| `build.ps1` | сборка и режимы `-Test` / `-Vectors` / `-Pipeline` / `-Clean` |

## Заметки по совместимости (ловушки C#)

* **Округление окна** — `Math.Round(x, MidpointRounding.ToEven)`; `MidpointRounding`
  выписан явно, чтобы намерение читалось, хотя в .NET «к чётному» — поведение по
  умолчанию (`Math.Round(2.5) == 2`, проверено). Опасна не «половина к чётному», а
  «половина ОТ НУЛЯ»: `f64::round` в Rust, `round` в C, `math.Round` в Go — и
  `Math.round` в JS («к +∞»). Та же тонкость, что `f64::round_ties_even` в Rust,
  `Math.rint` в JVM-портах и `math.RoundToEven` в Go.
* **`%` со знаком делимого** — `-1 % 360 == -1`, а не `359`: все кольцевые формулы
  пишутся как `((a - b + 180) % 360 + 360) % 360`.
* **Булевы в JSON** — `StringBuilder.Append(bool)` печатает `True`/`False`; в
  `Document.W` есть отдельная перегрузка `Kv(string, bool)`, которая пишет
  `true`/`false` (иначе документ не прошёл бы схему).
* **Локаль машины** — `InvariantGlobalization` в `.csproj` плюс `CultureInfo` в
  парсерах/форматтерах: без этого `ru-RU` дал бы `8,73e-11` и запятую в CSV.
* **Устойчивая сортировка точек сечения** — `List.Sort` в C# неустойчив, поэтому
  сортировка по углу сделана через `OrderBy` (при равных углах сохраняется порядок
  файла, от него зависит `height_mm` «первой» строки).
* **Числа в документе** — `Json.Num`: целые без дробной части, иначе shortest
  round-trip (.NET Core 3.0+), очень большие/малые — в экспоненциальной форме
  (`1E-12`). Это валидный JSON, Python и `spec/check_schema.py` его читают.
* **`pit_terms`** пишется у КАЖДОГО патча модели с ямами (включая пустой список) —
  этого требует загрузчик Python-референса; `selftest` проверяет ровно это
  (7 ключей при ямах, 0 без ям).
* **Свип степеней без QR**: одно накопление матрицы Грама в базисе Чебышёва на патч
  вместо 6 факторизаций; нормальная матрица степени `d` — ведущая подматрица матрицы
  `degMax`, RMSE считается по явным остаткам (Кленшоу).
* **Ключевое слово `ref`** и вложенный тип `PitShape` — C# не даёт назвать вложенный
  тип так же, как свойство, и запрещает `var ref = …`; в порте это
  `PitShapeOptions` и `refTerm`.
* **PowerShell-ловушка в `build.ps1`**: имена переменных регистронезависимы, поэтому
  локальная `$vectors` рядом с параметром `[switch]$Vectors` — это присваивание
  строки в switch (`Cannot convert value … SwitchParameter`); переменная названа
  `$vecDir`.
* Собранные `csharp/bin` и `csharp/obj` в git не попадают (см. корневой `.gitignore`).

## Лицензия

MIT + дополнительное условие об области применения: запрет использования ПО,
его производных, метода PAPPA и результатов его работы в военных системах,
произведённых вне Российской Федерации. Полный текст — в корневом `LICENSE`.
