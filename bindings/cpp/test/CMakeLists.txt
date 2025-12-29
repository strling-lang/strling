# Test suite CMakeLists.txt for STRling C++ binding

# Fetch Google Test
include(FetchContent)
FetchContent_Declare(
    googletest
    GIT_REPOSITORY https://github.com/google/googletest.git
    GIT_TAG v1.14.0
)

# For Windows: Prevent overriding the parent project's compiler/linker settings
set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(googletest)

# Fetch nlohmann/json for JSON processing in CLI and tests
FetchContent_Declare(
    json
    GIT_REPOSITORY https://github.com/nlohmann/json.git
    GIT_TAG v3.11.3
)
FetchContent_MakeAvailable(json)

# Enable testing
enable_testing()
include(GoogleTest)

# Collect all unit test files
file(GLOB UNIT_TEST_SOURCES
    ${CMAKE_CURRENT_SOURCE_DIR}/unit/*.cpp
)

# Exclude interaction_test.cpp as it requires the full DSL pipeline (parser/compiler/emitter)
# which is not yet implemented - the C++ binding currently only has the Simply API
list(FILTER UNIT_TEST_SOURCES EXCLUDE REGEX ".*interaction_test\\.cpp$")

# Collect all e2e test files
file(GLOB E2E_TEST_SOURCES
    ${CMAKE_CURRENT_SOURCE_DIR}/e2e/*.cpp
)

# Create test executable
add_executable(strling_tests
    ${UNIT_TEST_SOURCES}
    ${E2E_TEST_SOURCES}
)

# Link against strling library, gtest, and json
target_link_libraries(strling_tests
    PRIVATE
        strling
        gtest
        gtest_main
        nlohmann_json::nlohmann_json
)

# Add include directories
target_include_directories(strling_tests
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/../include
)

# Set C++20 standard for tests
set_target_properties(strling_tests PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
)

# Discover tests for CTest
gtest_discover_tests(strling_tests)

# Add a custom target to run tests with verbose output
add_custom_target(run_tests
    COMMAND ${CMAKE_CTEST_COMMAND} --verbose
    DEPENDS strling_tests
    WORKING_DIRECTORY ${CMAKE_BINARY_DIR}
)
