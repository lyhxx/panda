#include "panda/version.hpp"

#include <string>

namespace panda {

std::string_view version_string() noexcept {
    // Formatted from version() so the number never exists in two places: the
    // header above is the only spot anyone edits when the release bumps.
    static const std::string value =
        std::to_string(version().major) + "." +
        std::to_string(version().minor) + "." +
        std::to_string(version().patch);
    return value;
}

}  // namespace panda
