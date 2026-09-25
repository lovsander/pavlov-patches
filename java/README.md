# Java порт PAPPA

Piecewise Adaptive Poly-Patch Approximation (PAPPA) на Java — **полный порт**:
ядро метода (патчи с адаптивной степенью и нормированной координатой,
smoothstep-смешивание = partition of unity, фичер оконных гауссовых ям), детектор
трещин (band), авто-очистка выбросов (iqr) и пайплайн: CSV с сечениями → папка
образца в том же формате, что у референса Python и портов C++/C/Go/JS.

**Без зависимостей**: только JDK (проверено на 24.0.1), сборка голым `javac`,
JSON — свой мини-парсер/писатель (`Json.java`), тесты — свой `SelfTest`.
Числа обязаны совпадать с референсом, поэтому повторены тонкости numpy
(медиана как `np.median`, перцентиль с линейной интерполяцией, округление
«половина к чётному» в окне, круговые окна).

## Сборка и запуск

```powershell
powershell -File java/build.ps1              # javac -Xlint:all -d java/out
powershell -File java/build.ps1 -Test        # сборка + SelfTest (векторы + дымовой тест)
java -cp java/out pappa.cli.ConformanceMain spec/conformance/vectors
java -cp java/out pappa.cli.PappaMain --input python/synthetic_data.csv `
     --out-dir samples/synthetic_sphere_java --name synthetic_sphere
python python/studies/verify_port.py --py-dir samples/synthetic_sphere `
                                     --cpp-dir samples/synthetic_sphere_java
```

Ключи пайплайна: `--input`, `--out-dir` (обязательны), `--name`, `--description`,
`--no-pits`, `--quiet`. По умолчанию — как в референсе: N=7, фаза 24.75°, степени
4…14, авто-iqr, фичер ям включён. CSV читается по заголовку: нужны колонки
`section_id, height_mm, angle_deg, radius_mm`.

## Результаты сверки (проверено на этом порте)

| Проверка | Результат |
|---|---|
| `pappa.cli.ConformanceMain` | **4/4 OK** |
| вектор модели без ям | степени совпали, коэфф. `max|Δ| = 8.73e-11`, контур `3.02e-14 мм` |
| вектор модели с ямами | степени совпали, коэфф. `max|Δ| = 5.40e-10`, термины ям `4.34e-13`, контур `3.16e-13 мм` |
| вектор детектора | зон 2/2, ям 2/2, `max|Δ| = 0.00e+00°` |
| вектор очистки | выбросов 9/9, лишних 0, пропущено 0 |
| `pappa.SelfTest` | **9/9 ok**, код 0 |
| `java -cp java/out pappa.cli.PappaMain` (10 сечений × 6000 точек) | 10 сечений записано |
| `python/studies/verify_port.py` | **10/10 в допуске**, степени и число ям совпали, `max|Δr| = 1.339e-12 мм` (допуск 1e-6), код 0 |

## Состав

| Файл | Назначение |
|---|---|
| `src/pappa/Signal.java` | медиана/перцентили/MAD/окна по кольцу/фильтры — как numpy |
| `src/pappa/Linalg.java` | МНК через QR (Хаусхолдер) + базис Чебышёва (схема Кленшоу) |
| `src/pappa/Cleaner.java` | авто-очистка выбросов (iqr): медианный фильтр + усы Тьюки |
| `src/pappa/Detector.java` | детектор ям: узкая/широкая медиана → индикатор в MAD-ах → зоны |
| `src/pappa/Model.java` | `PatchApproximator`: локальные степени, smoothstep-смешивание, фичер ям, метрики |
| `src/pappa/Json.java` | мини-JSON: разбор (`Map`/`List`/`Double`) и запись, 0 зависимостей |
| `src/pappa/Csv.java` | чтение CSV по заголовку + посекционный расчёт |
| `src/pappa/Document.java` | документ `NN.pappa.json` и папка образца (`sample.json`) |
| `src/pappa/Conformance.java` | проверка конформанс-векторов (допуски как у C++/Go/C/JS) |
| `src/pappa/SelfTest.java` | самопроверка: векторы + дымовой тест пайплайна |
| `src/pappa/cli/ConformanceMain.java` | проверка порта по векторам (коды 0/1/2) |
| `src/pappa/cli/PappaMain.java` | пайплайн: CSV → папка образца |
| `build.ps1` | сборка `javac` и прогон SelfTest |

## Заметки по совместимости

* **Округление окна** — `Math.rint`, а не `Math.round`: Python `round(2.5) == 2`
  (половина к чётному), `Math.round(2.5) == 3`; иначе окна разъехались бы
  (та же тонкость отмечена в Go-порте).
* **Числа в документе** — `Json.num`: целые без дробной части, иначе
  `Double.toString` (shortest round-trip, «как Python repr»). JSON-парсер Python
  принимает и `1.0E-12`.
* **`pit_terms`** пишется у КАЖДОГО патча модели с ямами (включая пустой список) —
  этого требует загрузчик Python-референса.
* **Свип степеней без QR**: одно накопление матрицы Грама в базисе Чебышёва на
  патч вместо 6 факторизаций; нормальная матрица степени `d` — ведущая
  подматрица матрицы `degMax`, RMSE считается по явным остаткам (Кленшоу).
* **Локаль вывода**: CLI выставляют `Locale.ROOT`, иначе в русской локали числа
  печатались бы с запятой (`8,73e-11`) — при сверке логов это ловушка.
* Собранный `java/out` в git не попадает (см. корневой `.gitignore`).

## Лицензия

MIT + дополнительное условие об области применения: запрет использования ПО,
его производных, метода PAPPA и результатов его работы в военных системах,
произведённых вне Российской Федерации. Полный текст — в корневом `LICENSE`.
