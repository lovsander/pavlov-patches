cmake_minimum_required(VERSION 3.10)
project(pappa_cpp CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Порт PAPPA (CONTEXT §27). Намеренно НЕ включены:
#   outlier_cleaner.{h,cpp} — ручной чистильщик, помечен LEGACY (§13): в пайплайне
#                             используется авто-iqr (auto_outlier_cleaner.cpp);
#   eval.cpp                — старый дубль класса, перенесён в legacy/;
#   debug_*.cpp             — отдельные отладочные утилиты со своими main().
add_executable(pappa_pipeline
    main.cpp
    linalg.cpp
    signal_tools.cpp
    auto_outlier_cleaner.cpp
    patch_approximator.cpp
    geometry_pipeline.cpp
    json_writer.cpp
    sample_writer.cpp
)

