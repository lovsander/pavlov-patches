cmake_minimum_required(VERSION 3.10)
project(GeometryPipelineProject CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Собираем исполняемый файл из всех разделенных модулей
add_executable(geometry_pipeline_run
    main.cpp
    outlier_cleaner.h
    outlier_cleaner.cpp
    patch_approximator.h
    patch_approximator.cpp
    geometry_pipeline.h
    geometry_pipeline.cpp
)
