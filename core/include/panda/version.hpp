#pragma once

#include <string_view>

namespace panda {

struct Version {
    int major;
    int minor;
    int patch;
};

// The product version, and the only place it is written down. version.cpp
// formats this triple into version_string(), the root CMakeLists parses it for
// project(VERSION), and scripts/package_windows.ps1 reads it for the package
// manifest — bump it here and nowhere else.
[[nodiscard]] constexpr Version version() noexcept {
    return Version{1, 0, 0};
}

[[nodiscard]] std::string_view version_string() noexcept;

}  // namespace panda

