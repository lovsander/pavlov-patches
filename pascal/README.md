# Free Pascal порт PAPPA

Piecewise Adaptive Poly-Patch Approximation (PAPPA) на Object Pascal (Free Pascal) —
**полный порт**: ядро метода (патчи с адаптивной степенью и нормированной
координатой, smoothstep-смешивание = partition of unity, фичер оконных гауссовых ям),
детектор трещин (band), авто-очистка выбросов (iqr) и пайплайн: CSV с сечениями →
папка образца в том же формате, что у референса Python и портов C++/C/Go/JS/Java/Kotlin/Rust.

**Без зависимостей**: только компилятор FPC. JSON, CSV, форматирование чисел и
ISO-дата для манифеста — свои. Проверено на **Free Pascal 3.2.2** (target win32/i386;
компилятор лежит в `C:\FPC\3.2.2\bin\i386-win32\fpc.exe`, рядом есть Lazarus).

## Сборка и запуск

```powershell
powershell -File pascal/build_fpc.ps1              # соберёт conformance/selftest/pappa в pascal\bin
powershell -File pascal/build_fpc.ps1 -Test        # + SelfTest (векторы и дымовой тест)
powershell -File pascal/build_fpc.ps1 -Vectors     # + проверка конформанс-векторов
powershell -File pascal/build_fpc.ps1 -Clean       # пересобрать с нуля

.\pascal\bin\conformance.exe spec\conformance\vectors
.\pascal\bin\pappa.exe --input python\synthetic_data.csv `
    --out-dir samples\synthetic_sphere_pascal --name synthetic_sphere
python python/studies/verify_port.py --py-dir samples/synthetic_sphere `
                                     --cpp-dir samples/synthetic_sphere_pascal
```

Ключи пайплайна: `--input`, `--out-dir` (обязательны), `--name`, `--description`,
`--no-pits`, `--quiet`. По умолчанию — как в референсе: N=7, фаза 24.75°, степени
4…14, авто-iqr, фичер ям включён. CSV читается по заголовку: нужны колонки
`section_id, height_mm, angle_deg, radius_mm`.

## Результаты сверки (проверено на этом порте)

| Проверка | Результат |
|---|---|
| `conformance.exe` | **4/4 OK** (прошёл с первого прогона) |
| вектор модели без ям | степени совпали, коэфф. `max|Δ| = 1.4e-10`, контур `3.0e-14 мм` |
| вектор модели с ямами | степени совпали, коэфф. `max|Δ| = 1.6e-9`, термины ям `1.7e-12`, контур `3.2e-13 мм` |
| вектор детектора | зон 2/2, ям 2/2, `max|Δ| = 0.0e+0°` |
| вектор очистки | выбросов 9/9, лишних 0, пропущено 0 |
| `selftest.exe` | **9/9 ok** (векторы + разбор CSV + гладкий контур), код 0 |
| `pappa.exe` (10 сечений × 6000 точек) | 10 сечений записано |
| `python/studies/verify_port.py` | **10/10 в допуске**, степени и число ям совпали, `max|Δr| = 1.382e-12 мм` (допуск 1e-6), код 0 |

## Состав

| Файл | Назначение |
|---|---|
| `src/pappa_signal.pas` | медиана/перцентили/MAD/окна по кольцу/фильтры; общие типы (`TDoubleArray`, `TIntArray`, `TStrArray`) |
| `src/pappa_linalg.pas` | МНК через QR (Хаусхолдер) + базис Чебышёва (схема Кленшоу) |
| `src/pappa_cleaner.pas` | авто-очистка выбросов (iqr): медианный фильтр + усы Тьюки |
| `src/pappa_detector.pas` | детектор ям: узкая/широкая медиана → индикатор в MAD-ах → зоны (кольцо) |
| `src/pappa_model.pas` | `TModel`: локальные степени, smoothstep-смешивание, фичер ям, метрики |
| `src/pappa_json.pas` | мини-JSON: разбор в `TJsonNode` + запись, 0 зависимостей |
| `src/pappa_csv.pas` | чтение CSV по заголовку + посекционный расчёт |
| `src/pappa_document.pas` | документ `NN.pappa.json` и папка образца (`sample.json`) |
| `src/pappa_conformance.pas` | проверка конформанс-векторов (допуски как у остальных портов) |
| `src/conformance.lpr` | проверка порта по векторам (коды 0/1/2) |
| `src/selftest.lpr` | самопроверка: векторы + разбор CSV + гладкий контур |
| `src/pappa.lpr` | пайплайн: CSV → папка образца |
| `build_fpc.ps1` | поиск fpc + сборка трёх программ + прогоны |

## Заметки по совместимости (что реально укусило)

* **Опции FPC только со «приклеенным» значением**: `-Fusrc`, `-FUlib`, `-FEbin`,
  `-obin\pappa.exe`. Вариант `-Fu src` компилятор трактует как «исходник с именем
  `src`» — первая сборка молча уехала не туда и оставила `pappa_signal.ppu` в
  корне проекта, который потом **затенял свежий** юнит (симптом: «Identifier not
  found», хотя тип объявлен). `build_fpc.ps1 -Clean` чистит и `*.ppu`/`*.o`.
* **`Math` подключать обязательно**: `Floor`, `FMod`, `Exp`, `IsInfinite`, `IsNan`
  живут в `Math`, а не в `System` (в отличие от `Sqrt`/`Abs`/`Sin`).
* **`{` внутри комментария ломает разбор**: `{ { }` или `{ z_{k-2} … }` открывают
  вложенный комментарий — FPC выдаёт `Comment level 2 found` и следом
  `String exceeds line` (комментарий «съедает» остаток строки). Все такие
  комментарии переписаны.
* **Округление окна** — свой `RoundTiesEven` («половина к чётному», как Python
  `round()` и `math.RoundToEven` в Go / `Math.rint` в JVM-портах): на встроенный
  `Round` полагаться нельзя, у FPC это не гарантированно «по-банковски».
* **Числа в документе** — `FloatToStrF(V, ffGeneral, 17, 0)` (аналог `%.17g`);
  в `initialization` юнита `pappa_json` жёстко ставится
  `DefaultFormatSettings.DecimalSeparator := '.'`, иначе в русской локали в JSON
  попали бы запятые.
* **`pit_terms`** пишется у КАЖДОГО патча модели с ямами (включая пустой список) —
  этого требует загрузчик Python-референса.
* **Свип степеней без QR**: одно накопление матрицы Грама в базисе Чебышёва на
  патч вместо 6 факторизаций; нормальная матрица степени `d` — ведущая подматрица
  матрицы `degMax`, RMSE считается по явным остаткам (Кленшоу).
* **Общие типы объявлены один раз** (`pappa_signal`): `TDoubleArray`, `TIntArray`,
  `TStrArray` — иначе разные юниты получают несовместимые «одинаковые» типы.
* Собранные `pascal/bin` и `pascal/lib` в git не попадают (см. корневой `.gitignore`).
* Осталось 16 предупреждений компилятора вида «function result variable of a
  managed type does not seem to be initialized» — это про динамические массивы,
  которые заполняются в теле функции; на результат не влияют.

## Лицензия

MIT + дополнительное условие об области применения: запрет использования ПО,
его производных, метода PAPPA и результатов его работы в военных системах,
произведённых вне Российской Федерации. Полный текст — в корневом `LICENSE`.
