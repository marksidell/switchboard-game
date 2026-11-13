# sbaudio - the 551 switchboard simulator's audio program.
# Specified by docs/audio.md; see README.md beside this file.
#
#   cmake -S audio -B audio/build -DCMAKE_BUILD_TYPE=Release
#   cmake --build audio/build
#   ctest --test-dir audio/build --output-on-failure

cmake_minimum_required(VERSION 3.16)
project(sbaudio LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "" FORCE)
endif()

add_compile_options(-Wall -Wextra)

find_package(PkgConfig REQUIRED)
find_package(Threads REQUIRED)
pkg_check_modules(ALSA     REQUIRED IMPORTED_TARGET alsa)
pkg_check_modules(FFTW3F   REQUIRED IMPORTED_TARGET fftw3f)
pkg_check_modules(SNDFILE  REQUIRED IMPORTED_TARGET sndfile)
pkg_check_modules(MOSQ     REQUIRED IMPORTED_TARGET libmosquitto)

# The commit stamp --version prints and the log starts with, refreshed on every
# build (version.cmake).
add_custom_target(sbaudio_version
  COMMAND ${CMAKE_COMMAND} -DSRC=${CMAKE_CURRENT_SOURCE_DIR}
          -DOUT=${CMAKE_CURRENT_BINARY_DIR}/sbaudio_version.h
          -P ${CMAKE_CURRENT_SOURCE_DIR}/version.cmake
  BYPRODUCTS ${CMAKE_CURRENT_BINARY_DIR}/sbaudio_version.h)

# Everything but main.cpp and net.cpp, so the test can link the same objects
# the program runs rather than a second copy of them.
add_library(sbaudio_core STATIC
  src/util.cpp
  src/options.cpp
  src/dsp.cpp
  src/alsa.cpp
  src/wav.cpp
  src/engine.cpp
  src/monitor.cpp
  src/fbx.cpp
  src/ringdet.cpp
  src/tones.cpp
  src/detector.cpp
  src/vad.cpp
  src/aec.cpp
  src/rec.cpp
)
target_link_libraries(sbaudio_core PUBLIC
  PkgConfig::ALSA PkgConfig::FFTW3F PkgConfig::SNDFILE Threads::Threads)
target_include_directories(sbaudio_core PRIVATE ${CMAKE_CURRENT_BINARY_DIR})
add_dependencies(sbaudio_core sbaudio_version)

add_executable(sbaudio src/main.cpp src/net.cpp)
target_link_libraries(sbaudio PRIVATE sbaudio_core PkgConfig::MOSQ)

enable_testing()
add_executable(sbaudio_test test/test_sbaudio.cpp)
target_link_libraries(sbaudio_test PRIVATE sbaudio_core)
add_test(NAME sbaudio_test COMMAND sbaudio_test)

# Every prompt through the loudspeaker's chain, looking for the gate shutting
# on speech (audio.md 10.5). A tool, not a ctest: it reads the wav directory.
add_executable(monitor_check test/monitor_check.cpp)
target_link_libraries(monitor_check PRIVATE sbaudio_core)

install(TARGETS sbaudio RUNTIME DESTINATION bin)

# The echo canceller over a --record-line recording (audio.md 9.4). A tool.
add_executable(aec_check test/aec_check.cpp)
target_link_libraries(aec_check PRIVATE sbaudio_core)
