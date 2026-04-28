cmake_minimum_required(VERSION 3.24)

project(jolt_material_memory LANGUAGES CXX)
if(APPLE)
  enable_language(OBJCXX)
endif()

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

include(FetchContent)

# Force Jolt options through cache because this project includes Jolt as a subdirectory.
set(ENABLE_ALL_WARNINGS OFF CACHE BOOL "" FORCE)
set(CPP_EXCEPTIONS_ENABLED OFF CACHE BOOL "" FORCE)
set(CPP_RTTI_ENABLED ON CACHE BOOL "" FORCE)
set(TARGET_UNIT_TESTS OFF CACHE BOOL "" FORCE)
set(TARGET_HELLO_WORLD OFF CACHE BOOL "" FORCE)
set(TARGET_PERFORMANCE_TEST OFF CACHE BOOL "" FORCE)
set(TARGET_SAMPLES OFF CACHE BOOL "" FORCE)
set(TARGET_VIEWER OFF CACHE BOOL "" FORCE)
set(JPH_USE_DX12 OFF CACHE BOOL "" FORCE)
set(JPH_USE_DXC OFF CACHE BOOL "" FORCE)
set(JPH_USE_VK OFF CACHE BOOL "" FORCE)
set(JPH_USE_MTL OFF CACHE BOOL "" FORCE)
set(JPH_USE_CPU_COMPUTE OFF CACHE BOOL "" FORCE)

FetchContent_Declare(
  joltphysics
  GIT_REPOSITORY https://github.com/jrouwe/JoltPhysics.git
  GIT_TAG v5.5.0
  GIT_SHALLOW TRUE
  SOURCE_SUBDIR Build
)
FetchContent_MakeAvailable(joltphysics)

add_executable(
  jolt_memory_lab
  src/main.cpp
  src/material_memory.cpp
  src/scenarios.cpp
)

if(APPLE)
  target_sources(jolt_memory_lab PRIVATE src/material_memory_metal.mm)
  find_library(METAL_FRAMEWORK Metal REQUIRED)
  find_library(FOUNDATION_FRAMEWORK Foundation REQUIRED)
  target_link_libraries(jolt_memory_lab PRIVATE ${METAL_FRAMEWORK} ${FOUNDATION_FRAMEWORK})
  target_compile_options(jolt_memory_lab PRIVATE "$<$<COMPILE_LANGUAGE:OBJCXX>:-fobjc-arc>")
endif()

target_link_libraries(jolt_memory_lab PRIVATE Jolt::Jolt)
target_include_directories(jolt_memory_lab PRIVATE src)

if(APPLE)
  set(PHYSICS_REPO_ROOT "${joltphysics_SOURCE_DIR}")
  include("${joltphysics_SOURCE_DIR}/TestFramework/TestFramework.cmake")

  add_executable(
    JoltRecordingViewer
    MACOSX_BUNDLE
    src/recording_viewer.mm
    ${TEST_FRAMEWORK_ASSETS}
  )
  target_link_libraries(JoltRecordingViewer PRIVATE TestFramework)
  target_include_directories(JoltRecordingViewer PRIVATE src)
  set_property(TARGET JoltRecordingViewer PROPERTY XCODE_ATTRIBUTE_PRODUCT_BUNDLE_IDENTIFIER "com.specterlabs.joltrecordingviewer")
endif()
