# Go порт PAPPA

Piecewise Adaptive Poly-Patch Approximation (PAPPA) на Go — **полный порт**:
ядро метода (патчи с адаптивной степенью и нормированной координатой,
smoothstep-смешивание = partition of unity, фичер оконных гаусовых ям), детектор
трещин (band), авто-очистка выбросов (iqr) и пайплайн: CSV с сечениями → папка
образца в том же формате, что у референса Python и порта C++.

Числа обязаны совпадать с референсом, поэтому повторены даже тонкости numpy
(медиана как `np.median`, перцентиль с линейной интерполяцией, «банковское»
округление в `window_points`, круговые окна).

## Проверка

**1. Конформанс-векторы** — те же файлы, что читает порт C++
(`spec/conformance/vectors`, их сгенерировал Python):

```bash
cd go
go test ./...                                       # тесты: векторы + документ + round-trip
go run ./cmd/conformance ../spec/conformance/vectors # подробный вывод, коды 0/1/2
```

Результат: **4/4 вектора пройдено** (степени и коэффициенты патчей, зоны ям,
маска очистки совпадают с референсом в пределах допусков).

**2. Числовая сверка с референсом на реальных сечениях** (как у C++):

```bash
# эталон от Python и папка от порта
python python/studies/build_sample.py --name ref
go run ./cmd/pappa -input python/synthetic_data.csv -out-dir samples/body_go --name body

# сверка: степени, число терминов фичера, max|Δr| по сетке, RMSE к эталону
python python/studies/verify_port.py --py-dir samples/ref --cpp-dir samples/body_go
```

Результат на синтетике (10 сечений × 6000 точек): **10/10 сечений в допуске**,
`max|Δr|` = 5.5e-14 … 1.3e-12 мм при допуске 1e-6 мм, степени и число ям совпали,
RMSE к эталону одинаков.

## Запуск пайплайна

```bash
go run ./cmd/pappa -input python/synthetic_data.csv -out-dir samples/body_go -name body
# ключи: -n-patches -phase-deg -deg-min/-deg-max -overlap-train/-overlap-use
#        -deg-elbow-tol -baseline-deg -iqr-k -pits(=true|false) -quiet
```

Обязательны `-input` и `-out-dir`; остальное — по умолчанию как в референсе
(N=7, фаза 24.75°, степени 4…14, авто-iqr, фичер ям включён). CSV читается по
заголовку: нужны колонки `section_id, height_mm, angle_deg, radius_mm`.

Результат — папка образца:

```
samples/body_go/
    sample.json                манифест (format pappa-sample v1.0)
    sections/00.pappa.json     документ описания сечения (format pappa v2.0)
```

## Состав

| Файл | Назначение |
|------|-----------|
| `pappa/model.go` | модель: базис `x/half_train ∈ [-1,1]`, фаза сетки, правило «локоть», фичер ям, метрики патчей |
| `pappa/linalg.go` | МНК через QR (Хаусхолдер) — как `np.polyfit`/`lstsq` |
| `pappa/signal.go` | медиана/перцентили/окна/фильтры — как numpy |
| `pappa/cleaner.go` | детектор трещин (band) и авто-очистка (iqr) |
| `pappa/csv.go` | чтение CSV и посекционный расчёт |
| `pappa/document.go` | документ `.pappa.json` и папка образца (`sample.json` + `sections/`) |
| `pappa/conformance.go` | проверка конформанс-векторов (stdlib `encoding/json`) |
| `cmd/pappa` | пайплайн: CSV → папка образца |
| `cmd/conformance` | проверка порта по векторам |
| тесты | `conformance_test.go` (векторы), `document_test.go` (формат и round-trip) |

## Заметки по совместимости

* `window_points` использует `math.RoundToEven`, а не `math.Round`: Python
  `round(2.5) == 2`, а `math.Round(2.5) == 3`; иначе окна разъехались бы.
* Окна кольца строятся по модулю длины профиля (0° и 360° — одна точка).
* МНК — QR, а не нормальные уравнения: на ямном базисе нормальные уравнения дали
  бы заметно другие коэффициенты, чем numpy (SVD/QR).
* В документе ключ `pit_terms` пишется у КАЖДОГО патча модели с ямами (включая
  пустой список) — это и есть поведение референса; `pit_terms` без `global.pit`
  валидатор считает ошибкой.


