#pragma once

#include "panda/status.hpp"

#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

namespace panda::modelstore {

struct ManifestFile {
    std::string path;
    std::uintmax_t size{0};
    std::string sha256;
};

struct Manifest {
    int schema_version{0};
    std::string format;
    std::string id;
    std::string name;
    std::string version;
    std::string engine;
    std::string kind;
    std::string entry;
    std::string assets_dir;
    std::string icon;
    std::string created_at;
    std::vector<ManifestFile> files;
};

[[nodiscard]] Status parse_manifest(
    const std::filesystem::path& path,
    Manifest& manifest
);

[[nodiscard]] Status validate_pack_root(
    const std::filesystem::path& root,
    const Manifest& manifest
);

[[nodiscard]] Status validate_manifest_path(const std::string& path);

[[nodiscard]] Status validate_manifest_id(const std::string& id);

}  // namespace panda::modelstore

