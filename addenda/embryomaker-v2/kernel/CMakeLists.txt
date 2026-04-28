cmake_minimum_required(VERSION 3.25)

project(em2_kernel LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(
  em2_kernel
  src/contact_graph.cpp
  src/gfortran_rng.cpp
  src/layout.cpp
  src/legacy_cell_sorting.cpp
  src/legacy_invagination.cpp
  src/legacy_cell_sorting_noise.cpp
  src/legacy_cell_sorting_run.cpp
  src/legacy_neighbor_list.cpp
  src/legacy_cell_sorting_stepper.cpp
  src/mesenchymal_forces.cpp
  src/runner.cpp
)

target_include_directories(
  em2_kernel
  PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_compile_features(em2_kernel PUBLIC cxx_std_23)

enable_testing()

add_executable(
  em2_layout_smoke
  tests/layout_smoke.cpp
)

target_link_libraries(em2_layout_smoke PRIVATE em2_kernel)

add_test(NAME em2_layout_smoke COMMAND em2_layout_smoke)

add_executable(
  em2_gfortran_rng_smoke
  tests/gfortran_rng_smoke.cpp
)

target_link_libraries(em2_gfortran_rng_smoke PRIVATE em2_kernel)

add_test(NAME em2_gfortran_rng_smoke COMMAND em2_gfortran_rng_smoke)

add_executable(
  em2_cell_sorting_parity_smoke
  tests/cell_sorting_parity_smoke.cpp
)

target_link_libraries(em2_cell_sorting_parity_smoke PRIVATE em2_kernel)

add_test(NAME em2_cell_sorting_parity_smoke COMMAND em2_cell_sorting_parity_smoke)

add_executable(
  em2_cell_sorting_noise_smoke
  tests/cell_sorting_noise_smoke.cpp
)

target_link_libraries(em2_cell_sorting_noise_smoke PRIVATE em2_kernel)

add_test(NAME em2_cell_sorting_noise_smoke COMMAND em2_cell_sorting_noise_smoke)

add_executable(
  em2_cell_sorting_iteration_smoke
  tests/cell_sorting_iteration_smoke.cpp
)

target_link_libraries(em2_cell_sorting_iteration_smoke PRIVATE em2_kernel)

add_test(NAME em2_cell_sorting_iteration_smoke COMMAND em2_cell_sorting_iteration_smoke)

add_executable(
  em2_invagination_bootstrap_smoke
  tests/invagination_bootstrap_smoke.cpp
)

target_link_libraries(em2_invagination_bootstrap_smoke PRIVATE em2_kernel)

add_test(NAME em2_invagination_bootstrap_smoke COMMAND em2_invagination_bootstrap_smoke)

add_executable(
  em2_invagination_run_smoke
  tests/invagination_run_smoke.cpp
)

target_link_libraries(em2_invagination_run_smoke PRIVATE em2_kernel)

add_test(NAME em2_invagination_run_smoke COMMAND em2_invagination_run_smoke)

add_executable(
  em2_legacy_cell_sorting_summary
  tools/legacy_cell_sorting_summary.cpp
)

target_link_libraries(em2_legacy_cell_sorting_summary PRIVATE em2_kernel)

add_executable(
  em2_legacy_invagination_summary
  tools/legacy_invagination_summary.cpp
)

target_link_libraries(em2_legacy_invagination_summary PRIVATE em2_kernel)
