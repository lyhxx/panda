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
    std::error_code probe_error;
    if (!std::filesystem::is_regular_file(tar_path, probe_error)) {
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

    // Generous for a 2 GiB extraction on a cold disk, but bounded: a wedged
    // archiver must never hang the GUI event loop forever.
    constexpr DWORD kTarTimeoutMs = 10 * 60 * 1000;
    if (WaitForSingleObject(process_info.hProcess, kTarTimeoutMs) !=
        WAIT_OBJECT_0) {
        TerminateProcess(process_info.hProcess, 1);
        WaitForSingleObject(process_info.hProcess, 5000);
        CloseHandle(process_info.hThread);
        CloseHandle(process_info.hProcess);
        CloseHandle(output);
        return Status::error(ErrorCode::io_error, "tar.exe timed out");
    }
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
    // A traversal that cannot be completed cannot be certified clean: answer
    // "yes" and let the install refuse, rather than let an uncaught
    // filesystem_error escape into the Qt event loop and terminate the app.
    std::error_code error;
    std::filesystem::recursive_directory_iterator it(root, error);
    if (error) {
        return true;
    }
    const std::filesystem::recursive_directory_iterator finish;
    while (it != finish) {
        std::error_code item_error;
        if (it->is_symlink(item_error) || has_reparse_point(it->path())) {
            return true;
        }
        it.increment(error);
        if (error) {
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

std::uint16_t le16(const char* data) {
    const auto* bytes = reinterpret_cast<const unsigned char*>(data);
    return static_cast<std::uint16_t>(bytes[0]) |
           (static_cast<std::uint16_t>(bytes[1]) << 8U);
}

std::uint32_t le32(const char* data) {
    const auto* bytes = reinterpret_cast<const unsigned char*>(data);
    return static_cast<std::uint32_t>(bytes[0]) |
           (static_cast<std::uint32_t>(bytes[1]) << 8U) |
           (static_cast<std::uint32_t>(bytes[2]) << 16U) |
           (static_cast<std::uint32_t>(bytes[3]) << 24U);
}

// Declared uncompressed size of every entry, read from the zip central
// directory. This is the only way to enforce the expansion limits *before*
// extracting: the archive list (`tar -tf`) carries names but no sizes, and
// checking afterwards means a high-ratio bomb already filled the disk. The
// product contract is a ZIP (every error message and the file dialog say
// so), and the archive size cap keeps us clear of zip64 records.
Status declared_zip_sizes(
    const std::filesystem::path& archive,
    std::vector<std::uintmax_t>& sizes
) {
    sizes.clear();

    std::ifstream input(archive, std::ios::binary);
    if (!input) {
        return Status::error(
            ErrorCode::io_error,
            "failed to open the voice pack archive"
        );
    }
    input.seekg(0, std::ios::end);
    const auto length = static_cast<std::uint64_t>(input.tellg());
    // End-of-central-directory record: fixed 22 bytes plus up to 64 KiB of
    // comment, so it lives within the last 65557 bytes of the file.
    if (length < 22) {
        return Status::error(ErrorCode::invalid_archive, "truncated zip archive");
    }
    const auto tail_length = std::min<std::uint64_t>(length, 65557U);
    input.seekg(static_cast<std::streamoff>(length - tail_length));
    std::string tail(static_cast<std::size_t>(tail_length), '\0');
    input.read(tail.data(), static_cast<std::streamsize>(tail_length));
    if (input.gcount() != static_cast<std::streamsize>(tail_length)) {
        return Status::error(ErrorCode::invalid_archive, "truncated zip archive");
    }

    const std::string eocd_signature("\x50\x4B\x05\x06", 4);
    std::size_t eocd = std::string::npos;
    for (std::size_t at = tail.size() - 22;; --at) {
        if (tail.compare(at, 4, eocd_signature) == 0) {
            const auto comment = le16(tail.data() + at + 20);
            if (at + 22 + comment <= tail.size()) {
                eocd = at;
                break;
            }
        }
        if (at == 0) {
            break;
        }
    }
    if (eocd == std::string::npos) {
        return Status::error(
            ErrorCode::invalid_archive,
            "voice pack is not a zip archive"
        );
    }

    const auto directory_size = le32(tail.data() + eocd + 12);
    const auto directory_offset = le32(tail.data() + eocd + 16);
    if (directory_offset > length ||
        static_cast<std::uint64_t>(directory_size) > length - directory_offset) {
        return Status::error(
            ErrorCode::invalid_archive,
            "zip central directory is out of range"
        );
    }

    std::string directory(directory_size, '\0');
    input.seekg(static_cast<std::streamoff>(directory_offset));
    input.read(directory.data(), static_cast<std::streamsize>(directory_size));
    if (input.gcount() != static_cast<std::streamsize>(directory_size)) {
        return Status::error(ErrorCode::invalid_archive, "truncated zip central directory");
    }

    std::size_t at = 0;
    while (at + 46 <= directory.size()) {
        if (le32(directory.data() + at) != 0x02014B50U) {
            return Status::error(
                ErrorCode::invalid_archive,
                "corrupt zip central directory"
            );
        }
        const auto name_length = le16(directory.data() + at + 28);
        const auto extra_length = le16(directory.data() + at + 30);
        const auto comment_length = le16(directory.data() + at + 32);
        // 0xFFFFFFFF marks a zip64 record: the file exceeds 4 GiB, far past
        // any cap, and is rejected downstream as such.
        sizes.push_back(le32(directory.data() + at + 24));
        at += 46U + name_length + extra_length + comment_length;
    }
    if (at != directory.size()) {
        return Status::error(
            ErrorCode::invalid_archive,
            "corrupt zip central directory"
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

    // Enforce the declared expansion limits before extracting anything: a
    // small high-ratio archive must not get the chance to fill the disk
    // first (InstallOptions::max_file_bytes / max_total_bytes existed but
    // were never actually checked).
    std::vector<std::uintmax_t> declared_sizes;
    status = declared_zip_sizes(archive, declared_sizes);
    if (!status.ok()) {
        return status;
    }
    std::uintmax_t expanded_bytes = 0;
    for (const auto declared : declared_sizes) {
        if (declared > options.max_file_bytes) {
            return Status::error(
                ErrorCode::limit_exceeded,
                "voice pack contains a file that is too large"
            );
        }
        expanded_bytes += declared;
        if (expanded_bytes > options.max_total_bytes) {
            return Status::error(
                ErrorCode::limit_exceeded,
                "voice pack expands beyond the size limit"
            );
        }
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
        // A root that does not exist yet is the normal first-run state. The
        // probe itself failing (permissions, broken link) is not: reporting it
        // as an empty library would wipe the caller's current rows.
        if (error) {
            return Status::error(
                ErrorCode::io_error,
                "failed to read the voice library root"
            );
        }
        return Status::success();
    }

    // The throwing directory_iterator API surfaces I/O failures as uncaught
    // filesystem_error, and the error_code check that used to sit inside the
    // loop was dead code (the range-for increments through the throwing
    // overload, so `error` only ever got set by the constructor -- which on
    // failure simply yielded zero iterations and a false "success"). Iterate
    // explicitly and route every failure into the returned status.
    std::filesystem::directory_iterator it(voices_root, error);
    if (error) {
        return Status::error(ErrorCode::io_error, "failed while scanning voice packs");
    }
    const std::filesystem::directory_iterator finish;
    while (it != finish) {
        std::error_code item_error;
        if (it->is_directory(item_error) && !item_error) {
            const auto manifest_path = it->path() / "manifest.json";
            if (std::filesystem::is_regular_file(manifest_path, item_error) &&
                !item_error) {
                Manifest manifest;
                const auto status = parse_manifest(manifest_path, manifest);
                if (status.ok() &&
                    validate_pack_root(it->path(), manifest).ok()) {
                    manifests.push_back(std::move(manifest));
                }
            }
        }
        it.increment(error);
        if (error) {
            return Status::error(ErrorCode::io_error, "failed while scanning voice packs");
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

