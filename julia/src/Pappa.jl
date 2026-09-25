"""
    Pappa

Порт PAPPA (Piecewise Adaptive Poly-Patch Approximation) на Julia — полный порт
референса Python: ядро метода (патчи с адаптивной степенью и нормированной
координатой, smoothstep-смешивание = partition of unity, фичер оконных гауссовых ям),
детектор трещин (band), авто-очистка выбросов (iqr) и пайплайн CSV -> папка образца
в том же формате, что у остальных портов.

Зависимостей нет: JSON, CSV, статистика и ISO-дата написаны своими силами, поэтому
пакет работает с `julia --project=julia` без установки пакетов.
"""
module Pappa

export Signal, Linalg, Cleaner, Detector, Model, Json, Csv, Document, Conformance

include("signal.jl")
include("linalg.jl")
include("cleaner.jl")
include("detector.jl")
include("model.jl")
include("json.jl")
include("csv.jl")
include("document.jl")
include("conformance.jl")

const PORT_VERSION = "0.1.0"
const PORT_LANGUAGE = "julia"

end # module Pappa
