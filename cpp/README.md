# C++ порт PAPPA

Piecewise Adaptive Poly-Patch Approximation — порт на C++17. Пишет **тот же
формат документа**, что референс на Python, и проверяется численно
(`python/studies/verify_port.py`, а также тестом CTest, см. ниже).

Ядро порта (без I/O) зависит только от `<algorithm>`, `<cmath>`, `<vector>`,
`<stdexcept>`, поэтому его можно собирать и под микроконтроллеры: измеренные
стоимость, память и план оптимизаций — в `docs/embedded.md`.

## Сборка

```bash
# 1) CMake по пресету (канонический путь; пресеты — cpp/CMakePresets.json)
cmake --preset msvc-release          # Visual Studio 2026 (MSVC x64)
cmake --build --preset msvc-release  # -> cpp/build-cmake/msvc-release/Release/pappa_pipeline.exe

# 2) если нужен g++ (MSYS2) и в PATH есть make/ninja
cmake --preset gcc-release && cmake --build --preset gcc-release

# 3) совсем без CMake — прямой вызов компилятора
powershell -File cpp/build_gcc.ps1   # -> cpp/build/pappa_pipeline.exe
```

Проверенные компиляторы: **MSVC 14.51** (Visual Studio 2026 BuildTools, сборка
через CMake) и **g++ 15.2** (msys64/mingw64, скрипт `build_gcc.ps1`); оба дают
одинаковый результат сверки с Python.

## Проверка паритета

```bash
# двумя тестами:
#   1) conformance_vectors — проверка порта по spec/conformance/vectors (без Python)
#   2) port_parity_python — сборка папки образца на Python, портом и сверка чисел
ctest --preset msvc-release
```

Векторы конформанса можно проверять и вручную (полезно при отладке — печатает,
что именно разошлось):

```bash
cpp/build-cmake/msvc-release/Release/pappa_conformance spec/conformance/vectors
# коды: 0 — всё сошлось, 1 — расхождения, 2 — нет каталога
```

Векторы генерирует референс: `python python/studies/make_conformance.py`
(формат и допуски — в `spec/conformance/README.md`).

Если CMake нашёл Python без numpy (типичный случай: системный интерпретатор),
скрипт сам проверит наличие numpy и возьмёт окружение проекта; явно задать
интерпретатор можно так: `cmake --preset msvc-release -DPython3_EXECUTABLE=<путь>`.

Широкий рисунок сверки (профиль, остаток к эталону, паритет по сечениям, крупные
планы 3 ям) — отдельным скриптом, после того как числа сошлись):

```bash
python python/studies/verify_port_figure.py --py-dir samples/ref --cpp-dir samples/body_cpp
# -> python/plots/port_check.png (3520 x 1600 px)
```

Вручную то же самое:

```bash
python python/studies/build_sample.py --name ref          # эталон (с фичером ям)
cpp/build-cmake/msvc-release/Release/pappa_pipeline.exe \
     --input python/synthetic_data.csv --out-dir samples/body_cpp --name body
python python/studies/verify_port.py --py-dir samples/ref --cpp-dir samples/body_cpp
```

Коды возврата сверки: `0` — всё в допуске, `1` — расхождение, `2` — нет папки.
Результаты на синтетике (10 сечений × 6000 точек), допуск 1e-6 мм:

| Конфигурация | Степени совпали | Число ям совпало | max\|Δr\| |
|---|---|---|---|
| фичер ям включён (по умолчанию) | 10/10 | 10/10 (4/4/4/4/3/3/3/7/6/4) | 5.5e-14 … 1.3e-12 мм |
| фичер ям выключен (`--no-pits`) | 10/10 | — | 5.3e-14 … 4.4e-13 мм |

## Запуск

```bash
cpp/build-cmake/msvc-release/Release/pappa_pipeline.exe \
    --input python/synthetic_data.csv --out-dir samples/body_cpp --name body --self-check
```

Обязательны только `--input` и `--out-dir`; остальное — по умолчанию как в
референсе (N=7, фаза 24.75°, степени 4…14, авто-очистка iqr, правило «локтя»,
фичер ям включён). `--help` печатает полный список ключей. Пауза «нажмите ENTER»
выключена по умолчанию (включается `--pause`).

## Состав

| Файл | Назначение |
|------|-----------|
| `main.cpp` | CLI: CSV → пайплайн → папка образца (`--self-check`, `--dump-points`) |
| `geometry_pipeline.{h,cpp}` | посекционный расчёт: сортировка, очистка, детектор ям, обучение |
| `patch_approximator.{h,cpp}` | модель: нормированный базис `[-1,1]`, фаза сетки, правило «локтя», фичер ям |
| `pit_detector.{h,cpp}` | детектор трещин (band: узкая 1° − широкая 10°, порог 5.5 MAD, зона ≥ 2°) |
| `linalg.{h,cpp}` | МНК через QR (Хаусхолдер) — как `np.polyfit`/`lstsq` |
| `signal_tools.{h,cpp}` | медиана/перцентили/окна — как numpy (иначе маска очистки сдвинется) |
| `auto_outlier_cleaner.{h,cpp}` | авто-iqr (штатный режим очистки) |
| `json_writer.{h,cpp}` | минимальный писатель JSON (17 значащих цифр, без зависимостей) |
| `sample_writer.{h,cpp}` | запись `sample.json` + `sections/NN.pappa.json` |
| `section_model.h` | описание сечения (данные + модель) |
| `parity_check.ps1` | скрипт CTest-теста паритета с Python (`port_parity_python`) |
| `conformance.{h,cpp}*` | утилита `pappa_conformance`: проверка порта по spec/conformance/vectors |
| `json_reader.{h,cpp}` | минимальный читатель JSON (для конформанс-векторов) |
| `build_gcc.ps1` | сборка без CMake (g++, msys64) |

**Не входят в сборку (история):** `outlier_cleaner.{h,cpp}` — ручной чистильщик
(LEGACY, §13); `debug_csv.cpp`, `debug_patch.cpp` — отладочные утилиты старого
API; `legacy/eval.legacy.cpp` — прежний двойник класса (перенесён в `legacy/`).

## Лицензия

MIT + дополнительное условие об области применения: запрет использования ПО,
его производных, метода PAPPA и результатов его работы в военных системах,
произведённых вне Российской Федерации. Полный текст — в корневом `LICENSE`.

## Свип степеней без QR (наработка из embedded-экспериментов)

Правило «локтя» раньше стоило 6 факторизаций QR на патч (85 % времени обучения).
Теперь: **одно** накопление матрицы Грама в **базисе Чебышёва** — нормальная
матрица степени `d` является ведущей подматрицей матрицы `deg_max`, поэтому все
степени получаются из одной проходки. RMSE по-прежнему считается по **явным
остаткам** (схема Кленшоу) по тем же точкам окна, данные центрируются.

Замерено на синтетике (n=6000, 7 патчей, степени 4..14):

| фаза | было | стало |
|------|-----:|------:|
| обучение патчей | 18.5 мс | **7.5 мс** |
| всё сечение (очистка+детектор+обучение+контур) | 26.5 мс | **18.0 мс** |

Числа не поехали: `ctest --preset msvc-release` — **2/2 Passed**
(конформанс-векторы + паритет с референсом Python), степени по патчам те же.
Режим `--coord-mode raw` (легаси, без нормировки) остался на прежнем пути: базис
Чебышёва требует x ∈ [-1, 1].

## Абсолютный пол RMSE (опция, по умолчанию выключен)

`--deg-floor-mm X` (0 = выключен): если RMSE обучающего окна уже ниже `X`, степень
дальше не наращивается. Зачем: на **гладких** окнах RMSE уходит в машинный ноль и
степень выбирает разрядность решателя, а не данные (разбор — `docs/embedded.md`
§11-13).

Проверено на образце из 10 сечений: при `--deg-floor-mm 1e-6` степени совпали с
режимом без пола **10/10** — то есть на реальных (физических) сечениях пол ничего
не меняет и лишь страхует патологические гладкие окна. Включение по умолчанию —
смена контракта: нужно повторить правило в Python-референсе и перегенерировать
`spec/conformance` (там сравниваются степени).



