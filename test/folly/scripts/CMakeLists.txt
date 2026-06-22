cmake_minimum_required(VERSION 3.10)
project(folly_benchmark LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(folly REQUIRED)

add_executable(benchmark_containers benchmark_containers.cpp)
target_link_libraries(benchmark_containers folly::folly)

add_executable(benchmark_concurrency benchmark_concurrency.cpp)
target_link_libraries(benchmark_concurrency folly::folly)

add_executable(benchmark_codec benchmark_codec.cpp)
target_link_libraries(benchmark_codec folly::folly)

add_executable(benchmark_scaling benchmark_scaling.cpp)
target_link_libraries(benchmark_scaling folly::folly)
