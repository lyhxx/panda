#include "panda/modelstore/manifest.hpp"

#include "panda/crypto/sha256.hpp"

#include <nlohmann/json.hpp>

#include <algorithm>
#include <cctype>
#include <fstream>
#include <set>
#include <string_view>

namespace panda::modelstore {

namespace {

using Json = nlohmann::json;

constexpr std::string_view kPackFormat = "panda.voice-pack";

bool starts_with_drive(const std::string& value) {
    return value.size() >= 2 &&
           std::isalpha(static_cast<unsigned char>(value[0])) != 0 &&
           value[1] == ':';
}

std::string lower_ascii(std::string value) {
    std::transform(
        value.begin(),
        value.end(),
        value.begin(),
        [](unsigned char ch) { return static_cast<char>(std::tolower(ch)); }
    );
    return value;
}

bool is_reserved_windows_name(const std::string& segment) {
    auto base = lower_ascii(segment);
    const auto dot = base.find('.');
    if (dot != std::string::npos) {
        base.resize(dot);
    }

    static const std::set<std::string> reserved{
        "con", "prn", "aux", "nul",
        "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
        "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9"
    };
    return reserved.contains(base);
}

std::filesystem::path utf8_path(const std::string& value) {
    const auto* begin = reinterpret_cast<const char8_t*>(value.data());
    return std::filesystem::path(std::u8string(begin, begin + value.size()));
}

Status require_string(
    const Json& object,
    const char* key,
    std::string& value
) {
    const auto iterator = object.find(key);
    if (iterator == object.end() || !iterator->is_string()) {
        return Status::error(
            ErrorCode::invalid_manifest,
            std::string("manifest field is missing or not a string: ") + key
        );
    }
    value = iterator->get<std::string>();
    return Status::success();
}

Status verify_required_asset(
    const std::filesystem::path& root,
    const std::string& relative,
    const char* description
) {
    const auto status = validate_manifest_path(relative);
    if (!status.ok()) {
        return Status::error(
            ErrorCode::invalid_manifest,
            std::string(description) + " has an unsafe path"
        );
    }
    std::error_code file_error;
    if (!std::filesystem::is_regular_file(
            root / utf8_path(relative),
            file_error
        )) {
        return Status::error(
            ErrorCode::invalid_manifest,
            std::string("required asset is missing: ") + description
        );
    }
    return Status::success();
}

}  // namespace

Status validate_manifest_path(const std::string& path) {
    if (path.empty()) {
        return Status::error(ErrorCode::unsafe_path, "empty path");
    }
    if (path.size() > 1024) {
        return Status::error(ErrorCode::unsafe_path, "path is too long");
    }
    if (path.front() == '/' || path.front() == '\\' || starts_with_drive(path)) {
        return Status::error(ErrorCode::unsafe_path, "absolute path is not allowed");
    }
    if (path.find('\\') != std::string::npos) {
        return Status::error(ErrorCode::unsafe_path, "backslash separators are not allowed");
    }
    if (path.find('\0') != std::string::npos) {
        return Status::error(ErrorCode::unsafe_path, "NUL byte is not allowed");
    }

    std::size_t start = 0;
    while (start <= path.size()) {
        const auto end = path.find('/', start);
        const auto segment = path.substr(
            start,
            end == std::string::npos ? std::string::npos : end - start
        );
        if (segment.empty() || segment == "." || segment == "..") {
            return Status::error(
                ErrorCode::unsafe_path,
                "empty, current-directory, or parent-directory segment is not allowed"
            );
        }
        if (segment.back() == '.' || segment.back() == ' ') {
            return Status::error(
                ErrorCode::unsafe_path,
                "path segment may not end with a dot or space"
            );
        }
        if (is_reserved_windows_name(segment)) {
            return Status::error(
                ErrorCode::unsafe_path,
                "reserved Windows path segment is not allowed"
            );
        }
        if (std::any_of(
                segment.begin(),
                segment.end(),
                [](unsigned char ch) { return ch < 32; }
            )) {
            return Status::error(
                ErrorCode::unsafe_path,
                "control character is not allowed in path"
            );
        }
        if (end == std::string::npos) {
            break;
        }
        start = end + 1;
    }

    return Status::success();
}

Status validate_manifest_id(const std::string& id) {
    if (id.empty() || id.size() > 64) {
        return Status::error(ErrorCode::invalid_manifest, "invalid manifest id");
    }
    for (const auto ch : id) {
        const auto value = static_cast<unsigned char>(ch);
        if (std::islower(value) == 0 && std::isdigit(value) == 0 && ch != '-') {
            return Status::error(
                ErrorCode::invalid_manifest,
                "manifest id may contain only lowercase ASCII letters, digits, and hyphens"
            );
        }
    }
    if (id.front() == '-' || id.back() == '-') {
        return Status::error(
            ErrorCode::invalid_manifest,
            "manifest id may not begin or end with a hyphen"
        );
    }
    return Status::success();
}

Status parse_manifest(const std::filesystem::path& path, Manifest& manifest) {
    try {
        std::ifstream input(path, std::ios::binary);
        if (!input) {
            return Status::error(ErrorCode::io_error, "failed to open manifest.json");
        }

        Json root;
        input >> root;
        if (!root.is_object()) {
            return Status::error(ErrorCode::invalid_manifest, "manifest root must be an object");
        }

        manifest = Manifest{};
        if (!root.contains("schema_version") ||
            !root["schema_version"].is_number_integer()) {
            return Status::error(
                ErrorCode::invalid_manifest,
                "schema_version is missing or not an integer"
            );
        }
        manifest.schema_version = root["schema_version"].get<int>();

        for (auto [key, target] : {
                 std::pair{"format", &manifest.format},
                 std::pair{"id", &manifest.id},
                 std::pair{"name", &manifest.name},
                 std::pair{"version", &manifest.version},
                 std::pair{"engine", &manifest.engine},
                 std::pair{"kind", &manifest.kind},
                 std::pair{"entry", &manifest.entry},
                 std::pair{"assets_dir", &manifest.assets_dir},
             }) {
            const auto status = require_string(root, key, *target);
            if (!status.ok()) {
                return status;
            }
        }

        if (root.contains("created_at") && root["created_at"].is_string()) {
            manifest.created_at = root["created_at"].get<std::string>();
        }
        if (root.contains("icon") && root["icon"].is_string()) {
            manifest.icon = root["icon"].get<std::string>();
        }

        if (!root.contains("files") || !root["files"].is_array()) {
            return Status::error(ErrorCode::invalid_manifest, "files must be an array");
        }

        std::set<std::string> paths;
        for (const auto& item : root["files"]) {
            if (!item.is_object()) {
                return Status::error(ErrorCode::invalid_manifest, "file entry must be an object");
            }
            ManifestFile file;
            const auto path_status = require_string(item, "path", file.path);
            if (!path_status.ok()) {
                return path_status;
            }
            const auto hash_status = require_string(item, "sha256", file.sha256);
            if (!hash_status.ok()) {
                return hash_status;
            }
            if (!item.contains("size") || !item["size"].is_number_unsigned()) {
                return Status::error(
                    ErrorCode::invalid_manifest,
                    "file size must be an unsigned integer"
                );
            }
            file.size = item["size"].get<std::uintmax_t>();

            if (!paths.insert(file.path).second) {
                return Status::error(ErrorCode::invalid_manifest, "duplicate file path");
            }
            if (file.sha256.size() != 64 ||
                !std::all_of(
                    file.sha256.begin(),
                    file.sha256.end(),
                    [](unsigned char ch) { return std::isxdigit(ch) != 0; }
                )) {
                return Status::error(
                    ErrorCode::invalid_manifest,
                    "SHA-256 must be 64 hexadecimal characters"
                );
            }
            file.sha256 = lower_ascii(std::move(file.sha256));
            manifest.files.push_back(std::move(file));
        }

        return Status::success();
    } catch (const std::exception& exception) {
        return Status::error(
            ErrorCode::invalid_manifest,
            std::string("failed to parse manifest.json: ") + exception.what()
        );
    }
}

Status validate_pack_root(
    const std::filesystem::path& root,
    const Manifest& manifest
) {
    if (manifest.schema_version != 1) {
        return Status::error(ErrorCode::unsupported_schema, "unsupported schema_version");
    }
    if (manifest.format != kPackFormat) {
        return Status::error(ErrorCode::invalid_manifest, "invalid pack format");
    }
    if (manifest.engine != "meanvc2") {
        return Status::error(ErrorCode::unsupported_engine, "unsupported engine");
    }

    auto status = validate_manifest_id(manifest.id);
    if (!status.ok()) {
        return status;
    }
    for (const auto& value : {manifest.entry, manifest.assets_dir}) {
        status = validate_manifest_path(value);
        if (!status.ok()) {
            return status;
        }
    }
    if (!manifest.icon.empty()) {
        status = validate_manifest_path(manifest.icon);
        if (!status.ok()) {
            return status;
        }
    }

    std::set<std::string> expected;
    for (const auto& file : manifest.files) {
        status = validate_manifest_path(file.path);
        if (!status.ok()) {
            return status;
        }
        if (file.path == "manifest.json") {
            return Status::error(
                ErrorCode::invalid_manifest,
                "manifest.json must not be listed in manifest files"
            );
        }
        expected.insert(file.path);

        const auto full_path = root / utf8_path(file.path);
        if (!std::filesystem::is_regular_file(full_path)) {
            return Status::error(
                ErrorCode::invalid_manifest,
                "manifest file is missing: " + file.path
            );
        }
        if (std::filesystem::file_size(full_path) != file.size) {
            return Status::error(
                ErrorCode::checksum_mismatch,
                "file size mismatch: " + file.path
            );
        }

        std::string digest;
        status = crypto::sha256_file(full_path, digest);
        if (!status.ok()) {
            return status;
        }
        if (digest != file.sha256) {
            return Status::error(
                ErrorCode::checksum_mismatch,
                "SHA-256 mismatch: " + file.path
            );
        }
    }

    if (!expected.contains(manifest.entry)) {
        return Status::error(
            ErrorCode::invalid_manifest,
            "entry is not present in the manifest file list"
        );
    }

    std::set<std::string> actual;
    for (const auto& item : std::filesystem::recursive_directory_iterator(root)) {
        if (!item.is_regular_file()) {
            continue;
        }
        const auto relative = std::filesystem::relative(item.path(), root);
        const auto path = relative.generic_u8string();
        const std::string text(
            reinterpret_cast<const char*>(path.data()),
            path.size()
        );
        if (text != "manifest.json") {
            actual.insert(text);
        }
    }
    if (actual != expected) {
        return Status::error(
            ErrorCode::invalid_manifest,
            "manifest file list does not match archive contents"
        );
    }

    if (manifest.kind == "zero-shot") {
        status = verify_required_asset(
            root,
            manifest.assets_dir + "/spk_emb.npy",
            "zero-shot speaker embedding"
        );
        if (!status.ok()) {
            return status;
        }
        return verify_required_asset(
            root,
            manifest.assets_dir + "/register.json",
            "zero-shot registration"
        );
    }

    if (manifest.kind == "fine-tuned") {
        return verify_required_asset(
            root,
            manifest.assets_dir + "/dit.safetensors",
            "fine-tuned DiT"
        );
    }

    if (manifest.kind != "dsp") {
        return Status::error(ErrorCode::invalid_manifest, "unsupported pack kind");
    }

    return Status::success();
}

}  // namespace panda::modelstore

