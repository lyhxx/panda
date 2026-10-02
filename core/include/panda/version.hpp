#pragma once

#include <string_view>

namespace panda {

struct Version {
    int major;
    int minor;
    int patch;
};

[[nodiscard]] constexpr Version version() noexcept {
    return Version{0, 1, 0};
}

[[nodiscard]] std::string_view version_string() noexcept;

}  // namespace panda

