cmake_minimum_required(VERSION 3.24)

project(
    Panda
    VERSION 0.1.0
    DESCRIPTION "Open-source real-time voice changer"
    LANGUAGES CXX
)

option(PANDA_BUILD_TESTS "Build Panda tests" ON)
option(PANDA_BUILD_DESKTOP "Build the Qt/QML desktop application" OFF)

add_library(panda_core STATIC
    core/src/audio/realtime_stats.cpp
    core/src/crypto/sha256_windows.cpp
    core/src/modelstore/installer.cpp
    core/src/modelstore/manifest.cpp
    core/src/version.cpp
)

target_include_directories(panda_core
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/core/include
)

target_compile_features(panda_core PUBLIC cxx_std_20)

target_include_directories(panda_core
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/third_party/nlohmann
)

if(WIN32)
    target_link_libraries(panda_core PRIVATE bcrypt)
endif()

if(MSVC)
    target_compile_options(panda_core PRIVATE /W4 /permissive-)
else()
    target_compile_options(panda_core PRIVATE -Wall -Wextra -Wpedantic)
endif()

add_executable(panda_cli
    cli/src/main.cpp
)

target_link_libraries(panda_cli PRIVATE panda_core)

if(PANDA_BUILD_TESTS)
    include(CTest)
endif()

# Subdirectories register their own tests, so testing must be enabled first.
if(PANDA_BUILD_DESKTOP)
    add_subdirectory(desktop)
endif()

if(PANDA_BUILD_TESTS)
    if(BUILD_TESTING)
        add_executable(panda_core_tests
            tests/core/modelstore_test.cpp
            tests/core/realtime_stats_test.cpp
            tests/core/version_test.cpp
        )
        target_link_libraries(panda_core_tests PRIVATE panda_core)
        target_include_directories(panda_core_tests PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/third_party/nlohmann
        )
        if(MSVC)
            target_compile_options(panda_core_tests PRIVATE /UNDEBUG)
        else()
            target_compile_options(panda_core_tests PRIVATE -UNDEBUG)
        endif()
        add_test(NAME panda_core_tests COMMAND panda_core_tests)
        # The suite normally runs in ~1 s, but endpoint protection can block
        # file access to freshly written fixtures for ~30 s. Allow for that
        # while still failing a real hang instead of blocking forever.
        #
        # PASS_REGULAR_EXPRESSION is required because an early exit was observed
        # to report status 0; matching the completion marker turns that into a
        # failure instead of a silent pass.
        set_tests_properties(panda_core_tests PROPERTIES
            TIMEOUT 120
            PASS_REGULAR_EXPRESSION "PANDA_CORE_TESTS_COMPLETE"
        )
    endif()
endif()

