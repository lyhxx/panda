#include "panda/version.hpp"
#include "version_test.hpp"

#include <cassert>
#include <cctype>
#include <string>
#include <string_view>

namespace {

// A release version is exactly three dot-separated numbers.
[[nodiscard]] bool is_release_triple(std::string_view value) {
    int separators = 0;
    bool saw_digit_after_last_separator = false;
    for (const char symbol : value) {
        if (symbol == '.') {
            if (!saw_digit_after_last_separator) {
                return false;
            }
            separators += 1;
            saw_digit_after_last_separator = false;
            continue;
        }
        if (std::isdigit(static_cast<unsigned char>(symbol)) == 0) {
            return false;
        }
        saw_digit_after_last_separator = true;
    }
    return separators == 2 && saw_digit_after_last_separator;
}

}  // namespace

void run_version_tests() {
    const auto value = panda::version();
    assert(value.major >= 0);
    assert(value.minor >= 0);
    assert(value.patch >= 0);

    // The string has to be formatted from version() rather than written down
    // again: a second literal would drift the moment someone bumps one and
    // forgets the other, which is exactly what happened at 0.1.0.
    const auto expected =
        std::to_string(value.major) + "." + std::to_string(value.minor) +
        "." + std::to_string(value.patch);
    assert(panda::version_string() == expected);
    assert(is_release_triple(panda::version_string()));
}
