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
    pit_detector.cpp
    geometry_pipeline.cpp
    json_writer.cpp
    sample_writer.cpp
)

# --- утилита проверки порта по конформанс-векторам (без Python и без образцов) ---
add_executable(pappa_conformance
    conformance.cpp
    json_reader.cpp
    linalg.cpp
    signal_tools.cpp
    auto_outlier_cleaner.cpp
    patch_approximator.cpp
    pit_detector.cpp
)

# --- предупреждения компилятора (для обоих компиляторов, которые мы собираем:
#     MSVC в VS Code/CMake и g++ из msys64) ---
option(PAPPA_WARNINGS "Включить предупреждения компилятора" ON)
if (PAPPA_WARNINGS)
    if (MSVC)
        target_compile_options(pappa_pipeline PRIVATE /W4 /permissive-)
        target_compile_options(pappa_conformance PRIVATE /W4 /permissive-)
    else()
        target_compile_options(pappa_pipeline PRIVATE -Wall -Wextra)
        target_compile_options(pappa_conformance PRIVATE -Wall -Wextra)
    endif()
endif()

# --- проверка паритета порта с референсом Python как тест CTest ---
# Запуск: cmake --build --preset msvc-release && ctest --preset msvc-release
# Тест собирает две папки образца (Python и порт) и сравнивает их числами;
# пропускается, если Python не найден.
option(PAPPA_ENABLE_PARITY_TEST "Зарегистрировать ctest-проверку паритета" ON)
if (PAPPA_ENABLE_PARITY_TEST)
    enable_testing()
    # 1) сверка порта по конформанс-векторам: не требует Python и папок образцов
    add_test(NAME conformance_vectors
             COMMAND pappa_conformance
                     "${CMAKE_CURRENT_SOURCE_DIR}/../spec/conformance/vectors")
    # 2) сверка порта с референсом Python на реальном наборе сечений
    find_package(Python3 COMPONENTS Interpreter QUIET)
    if (Python3_Interpreter_FOUND)
        add_test(NAME port_parity_python
                 COMMAND powershell -NoProfile -ExecutionPolicy Bypass
                         -File "${CMAKE_CURRENT_SOURCE_DIR}/parity_check.ps1"
                         -Exe "$<TARGET_FILE:pappa_pipeline>"
                         -Python "${Python3_EXECUTABLE}")
    else()
        message(STATUS "Python не найден: ctest-проверка паритета не зарегистрирована")
    endif()
endif()


