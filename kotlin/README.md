# Kotlin порт PAPPA

Piecewise Adaptive Poly-Patch Approximation (PAPPA) на Kotlin — **полный порт**:
ядро метода (патчи с адаптивной степенью и нормированной координатой,
smoothstep-смешивание = partition of unity, фичер оконных гауссовых ям), детектор
трещин (band), авто-очистка выбросов (iqr) и пайплайн: CSV с сечениями → папка
образца в том же формате, что у референса Python и портов C++/C/Go/JS/Java.

**Без зависимостей**: только компилятор Kotlin и JVM. Отдельно ставить Kotlin не
нужно — **Android Studio кладёт полный `kotlinc`** в
`plugins\Kotlin\kotlinc\bin\kotlinc.bat`; `build.ps1` находит его сам (или берёт
`kotlinc` из PATH). JSON — свой мини-парсер (`Json.kt`), тесты — свой `SelfTest`.
Собирается и работает под JRE/JDK 24 (проверено: kotlinc-jvm 2.0.21, JVM 24.0.1).

Числа обязаны совпадать с референсом, поэтому повторены тонкости numpy
(медиана как `np.median`, перцентиль с линейной интерполяцией, округление
«половина к чётному» в окне, круговые окна).

## Сборка и запуск

```powershell
powershell -File kotlin/build.ps1              # kotlinc -> kotlin/out
powershell -File kotlin/build.ps1 -Test        # сборка + SelfTest (векторы + дымовой тест)
powershell -File kotlin/build.ps1 -Clean       # пересобрать с нуля

# вручную (build.ps1 печатает ровно эти команды; stdlib обязан быть в classpath):
$cp = "kotlin/out;C:\Program Files\Android\Android Studio\plugins\Kotlin\kotlinc\lib\kotlin-stdlib.jar"
java -cp $cp pappa.cli.ConformanceMain spec/conformance/vectors
java -cp $cp pappa.cli.PappaMain --input python/synthetic_data.csv `
     --out-dir samples/synthetic_sphere_kotlin --name synthetic_sphere

python python/studies/verify_port.py --py-dir samples/synthetic_sphere `
                                     --cpp-dir samples/synthetic_sphere_kotlin
```

Ключи пайплайна: `--input`, `--out-dir` (обязательны), `--name`, `--description`,
`--no-pits`, `--quiet`. По умолчанию — как в референсе: N=7, фаза 24.75°, степени
4…14, авто-iqr, фичер ям включён. CSV читается по заголовку: нужны колонки
`section_id, height_mm, angle_deg, radius_mm`.

## Результаты сверки (проверено на этом порте)

| Проверка | Результат |
|---|---|
| `pappa.cli.ConformanceMain` | **4/4 OK** (прошёл с первого прогона) |
| вектор модели без ям | степени совпали, коэфф. `max|Δ| = 8.73e-11`, контур `3.02e-14 мм` |
| вектор модели с ямами | степени совпали, коэфф. `max|Δ| = 5.40e-10`, термины ям `4.34e-13`, контур `3.16e-13 мм` |
| вектор детектора | зон 2/2, ям 2/2, `max|Δ| = 0.00e+00°` |
| вектор очистки | выбросов 9/9, лишних 0, пропущено 0 |
| `pappa.SelfTest` | **9/9 ok**, код 0 |
| `pappa.cli.PappaMain` (10 сечений × 6000 точек) | 10 сечений записано |
| `python/studies/verify_port.py` | **10/10 в допуске**, степени и число ям совпали, `max|Δr| = 1.339e-12 мм` (допуск 1e-6), код 0 |

## Состав

| Файл | Назначение |
|---|---|
| `src/pappa/Signal.kt` | медиана/перцентили/MAD/окна по кольцу/фильтры — как numpy |
| `src/pappa/Linalg.kt` | МНК через QR (Хаусхолдер) + базис Чебышёва (схема Кленшоу) |
| `src/pappa/Cleaner.kt` | авто-очистка выбросов (iqr): медианный фильтр + усы Тьюки |
| `src/pappa/Detector.kt` | детектор ям: узкая/широкая медиана → индикатор в MAD-ах → зоны |
| `src/pappa/Model.kt` | `Model`: локальные степени, smoothstep-смешивание, фичер ям, метрики |
| `src/pappa/Json.kt` | мини-JSON: разбор (`Map`/`List`/`Double`) и запись, 0 зависимостей |
| `src/pappa/Csv.kt` | чтение CSV по заголовку + посекционный расчёт |
| `src/pappa/Document.kt` | документ `NN.pappa.json` и папка образца (`sample.json`) |
| `src/pappa/Conformance.kt` | проверка конформанс-векторов (допуски как у C++/Go/C/JS/Java) |
| `src/pappa/SelfTest.kt` | самопроверка: векторы + дымовой тест пайплайна |
| `src/pappa/cli/ConformanceMain.kt` | проверка порта по векторам (коды 0/1/2) |
| `src/pappa/cli/PappaMain.kt` | пайплайн: CSV → папка образца |
| `build.ps1` | поиск `kotlinc` (Android Studio) + сборка + SelfTest |

## Заметки по совместимости

* **Округление окна** — `Math.rint`, а не `Math.round`: Python `round(2.5) == 2`
  (половина к чётному), `Math.round(2.5) == 3`; иначе окна разъехались бы.
* **Числа в документе** — `Json.num`: целые без дробной части, иначе
  `Double.toString` (shortest round-trip, «как Python repr»).
* **Имена классов CLI** — `@file:JvmName("ConformanceMain")`: без этого
  файл-функции `main` попали бы в класс `ConformanceMainKt` и запуск
  `java -cp out pappa.cli.ConformanceMain` не нашёл бы класс.
* **stdlib в classpath**: `kotlinc` компилирует против своей stdlib, но
  `java -cp out` её не видит — `build.ps1` подставляет
  `...\kotlinc\lib\kotlin-stdlib.jar` (путь печатается вместе с командами).
* **`pit_terms`** пишется у КАЖДОГО патча модели с ямами (включая пустой список) —
  этого требует загрузчик Python-референса.
* **Свип степеней без QR**: одно накопление матрицы Грама в базисе Чебышёва на
  патч вместо 6 факторизаций; нормальная матрица степени `d` — ведущая
  подматрица матрицы `degMax`, RMSE считается по явным остаткам (Кленшоу).
* **Локаль вывода**: CLI выставляют `Locale.ROOT`, иначе в русской локали числа
  печатались бы с запятой (`8,73e-11`) — при сверке логов портов это ловушка.
* Собранный `kotlin/out` в git не попадает (см. корневой `.gitignore`).

## Лицензия

MIT + дополнительное условие об области применения: запрет использования ПО,
его производных, метода PAPPA и результатов его работы в военных системах,
произведённых вне Российской Федерации. Полный текст — в корневом `LICENSE`.
