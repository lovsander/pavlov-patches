# C++ порт PAPPA

Piecewise Adaptive Poly-Patch Approximation — порт на C++17. Пишет **тот же
формат документа**, что референс на Python, и проверяется численно
(`python/studies/verify_port.py`).

## Сборка

```bash
# вариант 1: CMake
cmake -S cpp -B cpp/build && cmake --build cpp/build

# вариант 2: без CMake — скрипт под g++ (msys64/mingw64)
powershell -File cpp/build_gcc.ps1              # -> cpp/build/pappa_pipeline.exe
```

## Запуск

```bash
cpp/build/pappa_pipeline --input python/synthetic_data.csv \
                         --out-dir samples/body_cpp --name body --self-check
```

Обязательны только `--input` и `--out-dir`; остальное — по умолчанию как в
референсе (N=7, фаза 24.75°, степени 4…14, авто-очистка iqr, правило «локтя»).
`--help` печатает полный список ключей. Пауза «нажмите ENTER» выключена по
умолчанию (включается `--pause`).

## Проверка паритета

```bash
# 1) папка-эталон от Python (тот же CSV, те же параметры)
python python/studies/build_sample.py --no-pits --name ref_nopits
# 2) папка от порта
cpp/build/pappa_pipeline --input python/synthetic_data.csv \
                         --out-dir samples/body_cpp --no-pits
# 3) числовая сверка: степени, max|Δr| по сетке, RMSE к эталону
python python/studies/verify_port.py --py-dir samples/ref_nopits --cpp-dir samples/body_cpp
```

Коды возврата сверки: `0` — всё в допуске, `1` — расхождение, `2` — нет папки.
Замер на синтетике (10 сечений): степени совпадают, `max|Δr|` = 5e-14…4e-13 мм
при допуске 1e-6 мм.

## Состав

| Файл | Назначение |
|------|-----------|
| `main.cpp` | CLI: CSV → пайплайн → папка образца (`--self-check`, `--dump-points`) |
| `geometry_pipeline.{h,cpp}` | посекционный расчёт: сортировка, очистка, обучение |
| `patch_approximator.{h,cpp}` | модель: нормированный базис `[-1,1]`, фаза сетки, правило «локтя», фичер ям |
| `linalg.{h,cpp}` | МНК через QR (Хаусхолдер) — как `np.polyfit`/`lstsq` |
| `signal_tools.{h,cpp}` | медиана/перцентили/окна — как numpy (иначе маска очистки сдвинется) |
| `auto_outlier_cleaner.{h,cpp}` | авто-iqr (штатный режим очистки) |
| `json_writer.{h,cpp}` | минимальный писатель JSON (17 значащих цифр, без зависимостей) |
| `sample_writer.{h,cpp}` | запись `sample.json` + `sections/NN.pappa.json` |
| `section_model.h` | описание сечения (данные + модель) |

**Не входят в сборку (история):** `outlier_cleaner.{h,cpp}` — ручной чистильщик
(LEGACY, §13); `debug_csv.cpp`, `debug_patch.cpp` — отладочные утилиты старого
API; `legacy/eval.legacy.cpp` — прежний двойник класса (перенесён в `legacy/`).
