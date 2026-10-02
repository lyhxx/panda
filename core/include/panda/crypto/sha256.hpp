#pragma once

#include "panda/status.hpp"

#include <filesystem>
#include <string>

namespace panda::crypto {

[[nodiscard]] Status sha256_file(
    const std::filesystem::path& path,
    std::string& digest
);

}  // namespace panda::crypto

