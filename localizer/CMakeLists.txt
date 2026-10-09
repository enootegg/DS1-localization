cmake_minimum_required(VERSION 3.20)
project(ds1_localizer)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(GAME_ROOT_DIRECTORY "" CACHE STRING "Path to the game's root directory")

add_definitions(-D_CRT_SECURE_NO_WARNINGS -DWIN32_LEAN_AND_MEAN -DWIN32_EXTRA_LEAN -DNOMINMAX)
add_subdirectory(libs)

add_library(ds1_localizer SHARED
        source/Injector/Injector.cpp
        source/Util/XUtil.cpp
        source/dllmain.cpp
)

target_include_directories(ds1_localizer PRIVATE source)
target_link_libraries(ds1_localizer PRIVATE detours quickdllproxy)
set_target_properties(ds1_localizer PROPERTIES MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")

IF (NOT ${GAME_ROOT_DIRECTORY} STREQUAL "")
    add_custom_command(TARGET ds1_localizer POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy
            $<TARGET_FILE:ds1_localizer>
            "\"${GAME_ROOT_DIRECTORY}\\winhttp.dll\""
    )
ENDIF ()
