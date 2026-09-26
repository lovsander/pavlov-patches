#!/usr/bin/env bash
# Сборка F#-порта PAPPA без PowerShell: Linux / macOS / Git Bash.
# Нужен только .NET SDK (проект без NuGet-пакетов, сборка офлайн).
#
#   ./fsharp/build_fsharp.sh              собрать (Release)
#   ./fsharp/build_fsharp.sh --test       собрать и прогнать SelfTest
#   ./fsharp/build_fsharp.sh --vectors    собрать и проверить конформанс-векторы
#   ./fsharp/build_fsharp.sh --pipeline   собрать и записать samples/synthetic_sphere_fsharp
#   ./fsharp/build_fsharp.sh --clean      пересобрать с нуля (bin/obj долой)
#
# Запуск собранного: dotnet fsharp/bin/Release/net10.0/pappa.dll <команда> [ключи]
# (на Linux/macOS apphost тоже появляется, но dll надёжнее — не зависит от +x и rpath).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/.." && pwd)"
proj="$here/Pappa.fsproj"

mode="build"
for arg in "$@"; do
    case "$arg" in
        --test) mode="test" ;;
        --vectors) mode="vectors" ;;
        --pipeline) mode="pipeline" ;;
        --clean) mode="clean" ;;
        -h|--help)
            sed -n '2,12p' "$0"
            exit 0
            ;;
        *)
            echo "неизвестный ключ: $arg" >&2
            exit 2
            ;;
    esac
done

if ! command -v dotnet >/dev/null 2>&1; then
    echo "dotnet не найден в PATH. Установите .NET SDK 8+ (проверено на 10.0)." >&2
    exit 2
fi

if [ "$mode" = "clean" ]; then
    rm -rf "$here/bin" "$here/obj"
fi

dotnet build "$proj" -c Release --nologo

dll="$here/bin/Release/net10.0/pappa.dll"
if [ ! -f "$dll" ]; then
    echo "не найден собранный $dll" >&2
    exit 1
fi

vec_dir="$repo/spec/conformance/vectors"

case "$mode" in
    test)
        dotnet "$dll" selftest "$vec_dir"
        ;;
    vectors)
        dotnet "$dll" conformance "$vec_dir"
        ;;
    pipeline)
        dotnet "$dll" pipeline \
            --input "$repo/python/synthetic_data.csv" \
            --out-dir "$repo/samples/synthetic_sphere_fsharp" \
            --name synthetic_sphere --quiet
        ;;
    *)
        echo "векторы:  dotnet $dll conformance spec/conformance/vectors"
        echo "тесты:    dotnet $dll selftest spec/conformance/vectors"
        echo "пайплайн: dotnet $dll pipeline --input python/synthetic_data.csv --out-dir samples/synthetic_sphere_fsharp --name synthetic_sphere"
        echo "сверка:   python3 python/studies/verify_port.py --py-dir samples/synthetic_sphere --cpp-dir samples/synthetic_sphere_fsharp"
        ;;
esac
