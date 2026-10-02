#pragma once

#include "panda/modelstore/manifest.hpp"

#include <cstdint>
#include <filesystem>
#include <vector>

namespace panda::modelstore {

struct InstallOptions {
    bool overwrite{false};
    std::uintmax_t max_archive_bytes{2ULL * 1024ULL * 1024ULL * 1024ULL};
    std::uintmax_t max_file_bytes{1ULL * 1024ULL * 1024ULL * 1024ULL};
    std::uintmax_t max_total_bytes{4ULL * 1024ULL * 1024ULL * 1024ULL};
    std::size_t max_file_count{256};
};

struct InstallResult {
    Manifest manifest;
    std::filesystem::path installed_path;
};

[[nodiscard]] Status list_archive_entries(
    const std::filesystem::path& archive,
    std::vector<std::string>& entries
);

[[nodiscard]] Status install_voice_pack(
    const std::filesystem::path& archive,
    const std::filesystem::path& voices_root,
    const InstallOptions& options,
    InstallResult& result
);

[[nodiscard]] Status validate_voice_pack(
    const std::filesystem::path& archive,
    const InstallOptions& options,
    Manifest& manifest
);

[[nodiscard]] Status scan_voice_packs(
    const std::filesystem::path& voices_root,
    std::vector<Manifest>& manifests
);

// Removes exactly one voice pack directory. Public models live outside the
// voices root and are never touched. The directory must hold a readable
// manifest whose id matches the requested one; anything else is refused.
[[nodiscard]] Status remove_voice_pack(
    const std::filesystem::path& voices_root,
    const std::string& id
);

}  // namespace panda::modelstore

