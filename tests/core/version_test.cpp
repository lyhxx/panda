#include "panda/version.hpp"
#include "version_test.hpp"

#include <cassert>
#include <string_view>

void run_version_tests() {
    const auto value = panda::version();
    assert(value.major == 0);
    assert(value.minor == 1);
    assert(value.patch == 0);
    assert(panda::version_string() == std::string_view{"0.1.0"});
}

