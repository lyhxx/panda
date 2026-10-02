#include "panda/modelstore/installer.hpp"

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <random>
#include <sstream>
#include <system_error>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#endif

namespace panda::modelstore {

namespace {

class StagingGuard {
public:
    explicit StagingGuard(std::filesystem::path path_value)
        : path(std::move(path_value)) {}

    ~StagingGuard() {
        if (!released) {
            std::error_code ignored;
            std::filesystem::remove_all(path, ignored);
        }
    }

    void release() noexcept {
        released = true;
    }

private:
    std::filesystem::path path;
    bool released{false};
};

std::string random_suffix() {
    const auto now = std::chrono::high_resolution_clock::now().time_since_epoch().count();
    std::random_device device;
    std::ostringstream stream;
    stream << std::hex << now << '-' << device();
    return stream.str();
}

std::filesystem::path utf8_path(const std::string& value) {
    const auto* begin = reinterpret_cast<const char8_t*>(value.data());
    return std::filesystem::path(std::u8string(begin, begin + value.size()));
}

std::string normalize_archive_entry(std::string value) {
    while (value.size() >= 2 && value[0] == '.' && value[1] == '/') {
        value.erase(0, 2);
    }
    while (!value.empty() && value.back() == '/') {
        value.pop_back();
    }
    return value;
}

#ifdef _WIN32

std::wstring quote_argument(const std::wstring& value) {
    std::wstring result = L"\"";
    for (const auto ch : value) {
        if (ch == L'"') {
            result += L"\\\"";
        } else {
            result.push_back(ch);
        }
    }
    result += L"\"";
    return result;
}

Status run_tar(
    const std::vector<std::wstring>& arguments,
    const std::filesystem::path& output_path
) {
    wchar_t system_directory[MAX_PATH]{};
    const auto length = GetSystemDirectoryW(system_directory, MAX_PATH);
    if (length == 0 || length >= MAX_PATH) {
        return Status::error(ErrorCode::install_failed, "failed to locate System32");
    }

    const std::filesystem::path tar_path =
        std::filesystem::path(system_directory) / L"tar.exe";
    if (!std::filesystem::is_regular_file(tar_path)) {
        return Status::error(ErrorCode::install_failed, "tar.exe is not available");
    }

    SECURITY_ATTRIBUTES security_attributes{};
    security_attributes.nLength = sizeof(security_attributes);
    security_attributes.bInheritHandle = TRUE;

    const HANDLE output = CreateFileW(
        output_path.wstring().c_str(),
        GENERIC_WRITE,
        FILE_SHARE_READ,
        &security_attributes,
        CREATE_ALWAYS,
        FILE_ATTRIBUTE_NORMAL,
        nullptr
    );
    if (output == INVALID_HANDLE_VALUE) {
        return Status::error(ErrorCode::io_error, "failed to create process output file");
    }

    std::wstring command_line = quote_argument(tar_path.wstring());
    for (const auto& argument : arguments) {
        command_line.push_back(L' ');
        command_line += quote_argument(argument);
    }

    STARTUPINFOW startup_info{};
    startup_info.cb = sizeof(startup_info);
    startup_info.dwFlags = STARTF_USESTDHANDLES;
    startup_info.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
    startup_info.hStdOutput = output;
    startup_info.hStdError = output;

    PROCESS_INFORMATION process_info{};
    const BOOL created = CreateProcessW(
        nullptr,
        command_line.data(),
        nullptr,
        nullptr,
        TRUE,
        CREATE_NO_WINDOW,
        nullptr,
        nullptr,
        &startup_info,
        &process_info
    );

    if (!created) {
        CloseHandle(output);
        return Status::error(ErrorCode::install_failed, "failed to start tar.exe");
    }

    WaitForSingleObject(process_info.hProcess, INFINITE);
    DWORD exit_code = 1;
    GetExitCodeProcess(process_info.hProcess, &exit_code);
    CloseHandle(process_info.hThread);
    CloseHandle(process_info.hProcess);
    CloseHandle(output);

    if (exit_code != 0) {
        return Status::error(
            ErrorCode::invalid_archive,
            "tar.exe failed while processing the archive"
        );
    }
    return Status::success();
}

#else

Status run_tar(
    const std::vector<std::wstring>&,
    const std::filesystem::path&
) {
    return Status::error(
        ErrorCode::install_failed,
        "archive backend is currently implemented only on Windows"
    );
}

#endif

Status read_lines(
    const std::filesystem::path& path,
    std::vector<std::string>& lines
) {
    std::ifstream input(path, std::ios::binary);
    if (!input) {
        return Status::error(ErrorCode::io_error, "failed to read archive listing");
    }
    std::string line;
    while (std::getline(input, line)) {
        if (!line.empty() && line.back() == '\r') {
            line.pop_back();
        }
        lines.push_back(std::move(line));
    }
    return Status::success();
}

bool has_reparse_point(const std::filesystem::path& path) {
#ifdef _WIN32
    const auto attributes = GetFileAttributesW(path.wstring().c_str());
    return attributes != INVALID_FILE_ATTRIBUTES &&
           (attributes & FILE_ATTRIBUTE_REPARSE_POINT) != 0;
#else
    return std::filesystem::is_symlink(path);
#endif
}

bool has_symlink_in_tree(const std::filesystem::path& root) {
    for (const auto& item : std::filesystem::recursive_directory_iterator(root)) {
        if (item.is_symlink() || has_reparse_point(item.path())) {
            return true;
        }
    }
    return false;
}

Status validate_extracted_tree(
    const std::filesystem::path& root
) {
    if (has_symlink_in_tree(root)) {
        return Status::error(
            ErrorCode::unsafe_path,
            "archive contains a symbolic link or reparse point"
        );
    }
    return Status::success();
}

Status move_directory(
    const std::filesystem::path& from,
    const std::filesystem::path& to
) {
    std::error_code error;
    std::filesystem::rename(from, to, error);
    if (!error) {
        return Status::success();
    }

    error.clear();
    std::filesystem::copy(
        from,
        to,
        std::filesystem::copy_options::recursive,
        error
    );
    if (error) {
        return Status::error(ErrorCode::install_failed, "failed to move staged voice pack");
    }

    std::filesystem::remove_all(from, error);
    if (error) {
        return Status::error(
            ErrorCode::install_failed,
            "voice pack installed but staging cleanup failed"
        );
    }
    return Status::success();
}

}  // namespace

Status list_archive_entries(
    const std::filesystem::path& archive,
    std::vector<std::string>& entries
) {
    entries.clear();
    std::error_code error;
    if (!std::filesystem::is_regular_file(archive, error)) {
        return Status::error(ErrorCode::io_error, "archive does not exist");
    }

    const auto temp_name =
        archive.parent_path() /
        (".panda-tar-list-" + random_suffix() + ".txt");
    StagingGuard cleanup(temp_name);

    const auto status = run_tar(
        {L"-tf", archive.wstring()},
        temp_name
    );
    if (!status.ok()) {
        return status;
    }

    std::vector<std::string> lines;
    const auto read_status = read_lines(temp_name, lines);
    if (!read_status.ok()) {
        return read_status;
    }

    for (auto line : lines) {
        line = normalize_archive_entry(std::move(line));
        if (line.empty() || line == ".") {
            continue;
        }
        const auto path_status = validate_manifest_path(line);
        if (!path_status.ok()) {
            return Status::error(
                ErrorCode::unsafe_path,
                "unsafe archive path: " + line
            );
        }
        entries.push_back(std::move(line));
    }
    return Status::success();
}

Status install_voice_pack(
    const std::filesystem::path& archive,
    const std::filesystem::path& voices_root,
    const InstallOptions& options,
    InstallResult& result
) {
    std::error_code error;
    if (!std::filesystem::is_regular_file(archive, error)) {
        return Status::error(ErrorCode::io_error, "voice pack archive does not exist");
    }
    if (std::filesystem::file_size(archive, error) > options.max_archive_bytes) {
        return Status::error(ErrorCode::limit_exceeded, "voice pack archive is too large");
    }

    std::vector<std::string> entries;
    auto status = list_archive_entries(archive, entries);
    if (!status.ok()) {
        return status;
    }
    if (entries.size() > options.max_file_count) {
        return Status::error(ErrorCode::limit_exceeded, "voice pack contains too many entries");
    }

    std::filesystem::create_directories(voices_root, error);
    if (error) {
        return Status::error(ErrorCode::io_error, "failed to create voice pack root");
    }

    const auto staging_root =
        voices_root / ".staging" / ("pack-" + random_suffix());
    std::filesystem::create_directories(staging_root, error);
    if (error) {
        return Status::error(ErrorCode::io_error, "failed to create staging directory");
    }
    StagingGuard staging_guard(staging_root);

    const auto extract_log =
        staging_root.parent_path() / ("extract-" + random_suffix() + ".log");
    StagingGuard extract_log_guard(extract_log);
    status = run_tar(
        {L"-xf", archive.wstring(), L"-C", staging_root.wstring()},
        extract_log
    );
    if (!status.ok()) {
        return status;
    }

    status = validate_extracted_tree(staging_root);
    if (!status.ok()) {
        return status;
    }

    Manifest manifest;
    status = parse_manifest(staging_root / "manifest.json", manifest);
    if (!status.ok()) {
        return status;
    }
    status = validate_pack_root(staging_root, manifest);
    if (!status.ok()) {
        return status;
    }

    const auto final_path = voices_root / utf8_path(manifest.id);
    std::filesystem::path backup_path;

    if (std::filesystem::exists(final_path, error)) {
        if (!options.overwrite) {
            return Status::error(
                ErrorCode::already_exists,
                "voice pack is already installed; use overwrite to replace it"
            );
        }

        // Spec: same id may be upgraded, but a pack whose schema_version
        // differs from the installed one must not silently replace it.
        // Incompatible upgrades go through a migration path instead.
        Manifest installed;
        status = parse_manifest(final_path / "manifest.json", installed);
        if (!status.ok()) {
            return Status::error(
                ErrorCode::invalid_manifest,
                "installed voice pack has no readable manifest; refusing to overwrite"
            );
        }
        if (installed.id != manifest.id) {
            return Status::error(
                ErrorCode::invalid_manifest,
                "installed directory holds a different voice pack id"
            );
        }
        if (installed.schema_version != manifest.schema_version) {
            return Status::error(
                ErrorCode::unsupported_schema,
                "schema_version differs from the installed pack; migrate instead of overwriting"
            );
        }

        backup_path =
            voices_root / ".backup" /
            (manifest.id + "-" + random_suffix());
        std::filesystem::create_directories(backup_path.parent_path(), error);
        if (error) {
            return Status::error(ErrorCode::io_error, "failed to create backup directory");
        }
        std::filesystem::rename(final_path, backup_path, error);
        if (error) {
            return Status::error(ErrorCode::install_failed, "failed to back up existing pack");
        }
    }

    status = move_directory(staging_root, final_path);
    if (!status.ok()) {
        if (!backup_path.empty()) {
            std::error_code ignored;
            std::filesystem::rename(backup_path, final_path, ignored);
        }
        return status;
    }

    staging_guard.release();
    if (!backup_path.empty()) {
        std::filesystem::remove_all(backup_path, error);
    }

    result.manifest = std::move(manifest);
    result.installed_path = final_path;
    return Status::success();
}

Status validate_voice_pack(
    const std::filesystem::path& archive,
    const InstallOptions& options,
    Manifest& manifest
) {
    const auto validation_root =
        std::filesystem::temp_directory_path() /
        ("panda-validate-" + random_suffix());
    StagingGuard cleanup(validation_root);

    InstallResult result;
    const auto status = install_voice_pack(
        archive,
        validation_root,
        options,
        result
    );
    if (!status.ok()) {
        return status;
    }
    manifest = std::move(result.manifest);
    return Status::success();
}

Status scan_voice_packs(
    const std::filesystem::path& voices_root,
    std::vector<Manifest>& manifests
) {
    manifests.clear();
    std::error_code error;
    if (!std::filesystem::is_directory(voices_root, error)) {
        return Status::success();
    }

    for (const auto& item : std::filesystem::directory_iterator(voices_root, error)) {
        if (error) {
            return Status::error(ErrorCode::io_error, "failed while scanning voice packs");
        }
        if (!item.is_directory()) {
            continue;
        }
        const auto manifest_path = item.path() / "manifest.json";
        if (!std::filesystem::is_regular_file(manifest_path)) {
            continue;
        }

        Manifest manifest;
        const auto status = parse_manifest(manifest_path, manifest);
        if (!status.ok()) {
            continue;
        }
        if (validate_pack_root(item.path(), manifest).ok()) {
            manifests.push_back(std::move(manifest));
        }
    }

    std::sort(
        manifests.begin(),
        manifests.end(),
        [](const Manifest& left, const Manifest& right) {
            return left.name < right.name;
        }
    );
    return Status::success();
}

Status remove_voice_pack(
    const std::filesystem::path& voices_root,
    const std::string& id
) {
    const auto id_status = validate_manifest_id(id);
    if (!id_status.ok()) {
        return id_status;
    }

    std::error_code error;
    const auto target = voices_root / utf8_path(id);
    if (!std::filesystem::exists(target, error)) {
        return Status::error(ErrorCode::not_found, "voice pack is not installed");
    }
    if (!std::filesystem::is_directory(target, error)) {
        return Status::error(
            ErrorCode::invalid_argument,
            "voice pack path is not a directory"
        );
    }

    Manifest installed;
    const auto manifest_status = parse_manifest(
        target / "manifest.json",
        installed
    );
    if (!manifest_status.ok()) {
        return Status::error(
            ErrorCode::invalid_manifest,
            "refusing to remove a directory without a readable manifest.json"
        );
    }
    if (installed.id != id) {
        return Status::error(
            ErrorCode::invalid_manifest,
            "directory holds a different voice pack id; refusing to remove"
        );
    }

    // Defensive containment check: the resolved target must sit directly
    // under the resolved voice root.
    const auto root = std::filesystem::weakly_canonical(voices_root, error);
    if (error) {
        return Status::error(
            ErrorCode::io_error,
            "failed to resolve the voice pack root"
        );
    }
    const auto resolved = std::filesystem::weakly_canonical(target, error);
    if (error) {
        return Status::error(
            ErrorCode::io_error,
            "failed to resolve the voice pack path"
        );
    }
    if (resolved.parent_path() != root) {
        return Status::error(
            ErrorCode::unsafe_path,
            "voice pack path escapes the voice root"
        );
    }

    std::filesystem::remove_all(target, error);
    if (error) {
        return Status::error(ErrorCode::io_error, "failed to remove the voice pack");
    }
    return Status::success();
}

}  // namespace panda::modelstore

