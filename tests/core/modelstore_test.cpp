#include "panda/crypto/sha256.hpp"
#include "panda/modelstore/installer.hpp"
#include "panda/modelstore/manifest.hpp"
#include "realtime_stats_test.hpp"
#include "version_test.hpp"

#include <nlohmann/json.hpp>

#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iomanip>
#include <sstream>
#include <string>
#include <vector>

namespace {

using nlohmann::json;
namespace fs = std::filesystem;
using panda::ErrorCode;

struct Fixture {
    fs::path root;
    fs::path pack;
    fs::path archive;
};

// Each run gets its own scratch directory. Fixtures are intentionally left in
// place: deleting them measured ~31 s per call on the development host, where
// an endpoint-protection filter blocks removal of freshly written archives.
// A unique path means no pre-run cleanup is needed either.
fs::path scratch_root(const std::string& name) {
    const auto nonce = std::chrono::high_resolution_clock::now()
                           .time_since_epoch()
                           .count();
    return fs::path("E:/code/codex-project/.tmp") /
           ("panda-modelstore-" + name + "-" + std::to_string(nonce));
}

void write_text(const fs::path& path, const std::string& value) {
    fs::create_directories(path.parent_path());
    std::ofstream output(path, std::ios::binary);
    output << value;
}

std::uint32_t crc32(const std::string& value) {
    std::uint32_t crc = 0xFFFFFFFFU;
    for (const auto ch : value) {
        crc ^= static_cast<unsigned char>(ch);
        for (int bit = 0; bit < 8; ++bit) {
            const auto mask = static_cast<std::uint32_t>(
                -static_cast<std::int32_t>(crc & 1U)
            );
            crc = (crc >> 1U) ^ (0xEDB88320U & mask);
        }
    }
    return ~crc;
}

void append_u16(std::string& target, std::uint16_t value) {
    target.push_back(static_cast<char>(value & 0xFFU));
    target.push_back(static_cast<char>((value >> 8U) & 0xFFU));
}

void append_u32(std::string& target, std::uint32_t value) {
    for (int shift = 0; shift < 32; shift += 8) {
        target.push_back(static_cast<char>((value >> shift) & 0xFFU));
    }
}

void write_stored_zip(
    const fs::path& archive,
    const std::string& entry_name,
    const std::string& contents
) {
    const auto checksum = crc32(contents);

    std::string local;
    append_u32(local, 0x04034B50U);
    append_u16(local, 20);
    append_u16(local, 0);
    append_u16(local, 0);
    append_u16(local, 0);
    append_u16(local, 0);
    append_u32(local, checksum);
    append_u32(local, static_cast<std::uint32_t>(contents.size()));
    append_u32(local, static_cast<std::uint32_t>(contents.size()));
    append_u16(local, static_cast<std::uint16_t>(entry_name.size()));
    append_u16(local, 0);
    local += entry_name;
    local += contents;

    const auto central_offset = static_cast<std::uint32_t>(local.size());
    std::string central;
    append_u32(central, 0x02014B50U);
    append_u16(central, 20);
    append_u16(central, 20);
    append_u16(central, 0);
    append_u16(central, 0);
    append_u16(central, 0);
    append_u16(central, 0);
    append_u32(central, checksum);
    append_u32(central, static_cast<std::uint32_t>(contents.size()));
    append_u32(central, static_cast<std::uint32_t>(contents.size()));
    append_u16(central, static_cast<std::uint16_t>(entry_name.size()));
    append_u16(central, 0);
    append_u16(central, 0);
    append_u16(central, 0);
    append_u16(central, 0);
    append_u32(central, 0);
    append_u32(central, 0);
    central += entry_name;

    std::string end;
    append_u32(end, 0x06054B50U);
    append_u16(end, 0);
    append_u16(end, 0);
    append_u16(end, 1);
    append_u16(end, 1);
    append_u32(end, static_cast<std::uint32_t>(central.size()));
    append_u32(end, central_offset);
    append_u16(end, 0);

    fs::create_directories(archive.parent_path());
    std::ofstream output(archive, std::ios::binary);
    output << local << central << end;
}

json file_entry(const fs::path& root, const std::string& relative) {
    std::string digest;
    const auto path = root / relative;
    const auto status = panda::crypto::sha256_file(path, digest);
    assert(status.ok());
    return json{
        {"path", relative},
        {"size", fs::file_size(path)},
        {"sha256", digest},
    };
}

bool create_zip(const fs::path& root, const fs::path& archive) {
    std::ostringstream command;
    command << "tar.exe -a -c -f " << std::quoted(archive.string())
            << " -C " << std::quoted(root.string()) << " .";
    return std::system(command.str().c_str()) == 0;
}

Fixture make_fixture(
    const std::string& name,
    bool corrupt_asset,
    int schema_version = 1
) {
    std::cerr << "fixture: " << name << " start\n";
    const auto root = scratch_root(name);
    const auto pack = root / "pack";
    const auto archive = root / "pack.zip";
    fs::create_directories(pack / "assets");
    fs::create_directories(pack / "reference");

    write_text(pack / "mvc2_test_rt.yaml", "engine: meanvc2\n");
    write_text(pack / "assets" / "spk_emb.npy", "speaker-embedding");
    write_text(pack / "assets" / "register.json", "{\"id\":\"test-voice\"}\n");
    write_text(pack / "reference" / "reference.wav", "RIFF-test");
    write_text(pack / "LICENSES.json", "{}\n");

    const std::vector<std::string> paths{
        "LICENSES.json",
        "assets/register.json",
        "assets/spk_emb.npy",
        "mvc2_test_rt.yaml",
        "reference/reference.wav",
    };

    json manifest{
        {"schema_version", schema_version},
        {"format", "panda.voice-pack"},
        {"id", "test-voice"},
        {"name", "Test Voice"},
        {"version", "1.0.0"},
        {"engine", "meanvc2"},
        {"kind", "zero-shot"},
        {"entry", "mvc2_test_rt.yaml"},
        {"assets_dir", "assets"},
        {"created_at", "2026-10-02T00:00:00Z"},
        {"files", json::array()},
    };

    for (const auto& path : paths) {
        manifest["files"].push_back(file_entry(pack, path));
    }
    write_text(pack / "manifest.json", manifest.dump(2));

    if (corrupt_asset) {
        write_text(pack / "assets" / "spk_emb.npy", "corrupted-after-hash");
    }

    assert(create_zip(pack, archive));
    std::cerr << "fixture: " << name << " archive created\n";
    return Fixture{root, pack, archive};
}

void test_path_validation() {
    std::cerr << "test: path validation\n";
    assert(panda::modelstore::validate_manifest_path(
               "assets/spk_emb.npy"
           ).ok());
    assert(panda::modelstore::validate_manifest_path(
               "../escape.txt"
           ).code == ErrorCode::unsafe_path);
    assert(panda::modelstore::validate_manifest_path(
               "C:/escape.txt"
           ).code == ErrorCode::unsafe_path);
    assert(panda::modelstore::validate_manifest_path(
               "assets\\spk_emb.npy"
           ).code == ErrorCode::unsafe_path);
    assert(panda::modelstore::validate_manifest_path(
               "assets/CON.txt"
           ).code == ErrorCode::unsafe_path);
}

void test_install_scan_and_overwrite() {
    std::cerr << "test: install scan overwrite\n";
    const auto step = [](const char* name, const auto& body) {
        const auto started = std::chrono::steady_clock::now();
        body();
        const auto elapsed = std::chrono::duration<double>(
            std::chrono::steady_clock::now() - started
        ).count();
        std::cerr << "  step: " << name << " = " << std::fixed
                  << std::setprecision(3) << elapsed << " s\n";
    };

    Fixture fixture;
    step("make-fixture", [&] { fixture = make_fixture("valid", false); });
    const auto voices = fixture.root / "voices";

    panda::modelstore::InstallOptions options;
    panda::modelstore::InstallResult result;
    panda::Status status;
    step("install", [&] {
        status = panda::modelstore::install_voice_pack(
            fixture.archive,
            voices,
            options,
            result
        );
    });
    std::cerr << "install status: " << static_cast<int>(status.code) << "\n";
    assert(status.ok());
    assert(result.manifest.id == "test-voice");
    assert(fs::is_regular_file(result.installed_path / "manifest.json"));

    step("install-again", [&] {
        status = panda::modelstore::install_voice_pack(
            fixture.archive,
            voices,
            options,
            result
        );
    });
    assert(status.code == ErrorCode::already_exists);

    options.overwrite = true;
    step("overwrite", [&] {
        status = panda::modelstore::install_voice_pack(
            fixture.archive,
            voices,
            options,
            result
        );
    });
    assert(status.ok());

    std::vector<panda::modelstore::Manifest> manifests;
    step("scan", [&] {
        status = panda::modelstore::scan_voice_packs(voices, manifests);
    });
    assert(status.ok());
    assert(manifests.size() == 1);
    assert(manifests.front().name == "Test Voice");

    // Fixtures are left in place; see scratch_root().
}

void test_checksum_failure_is_atomic() {
    std::cerr << "test: checksum atomic\n";
    const auto valid = make_fixture("atomic-valid", false);
    const auto voices = valid.root / "voices";
    panda::modelstore::InstallOptions options;
    panda::modelstore::InstallResult result;
    auto status = panda::modelstore::install_voice_pack(
        valid.archive,
        voices,
        options,
        result
    );
    assert(status.ok());

    const auto original_manifest =
        fs::file_size(result.installed_path / "manifest.json");

    const auto corrupt = make_fixture("atomic-corrupt", true);
    options.overwrite = true;
    status = panda::modelstore::install_voice_pack(
        corrupt.archive,
        voices,
        options,
        result
    );
    assert(status.code == ErrorCode::checksum_mismatch);
    assert(fs::file_size(voices / "test-voice" / "manifest.json") ==
           original_manifest);
}

void test_validation_api() {
    const auto valid = make_fixture("validate-valid", false);
    panda::modelstore::InstallOptions options;
    panda::modelstore::Manifest manifest;
    auto status = panda::modelstore::validate_voice_pack(
        valid.archive,
        options,
        manifest
    );
    assert(status.ok());
    assert(manifest.id == "test-voice");

    const auto corrupt = make_fixture("validate-corrupt", true);
    status = panda::modelstore::validate_voice_pack(
        corrupt.archive,
        options,
        manifest
    );
    assert(status.code == ErrorCode::checksum_mismatch);
}

void test_archive_path_traversal_is_rejected() {
    const auto root = scratch_root("traversal");
    fs::create_directories(root);
    const auto archive = root / "evil.zip";
    write_stored_zip(archive, "../escape.txt", "escape");

    panda::modelstore::InstallOptions options;
    panda::modelstore::InstallResult result;
    const auto status = panda::modelstore::install_voice_pack(
        archive,
        root / "voices",
        options,
        result
    );
    assert(status.code == ErrorCode::unsafe_path);
    assert(!fs::exists(root / "escape.txt"));
}

void test_schema_mismatch_blocks_overwrite() {
    std::cerr << "test: schema mismatch blocks overwrite\n";
    const auto installed = make_fixture("schema-v1", false, 1);
    const auto incoming = make_fixture("schema-v2", false, 2);
    const auto voices = installed.root / "voices";

    panda::modelstore::InstallOptions options;
    panda::modelstore::InstallResult result;
    auto status = panda::modelstore::install_voice_pack(
        installed.archive,
        voices,
        options,
        result
    );
    assert(status.ok());

    options.overwrite = true;
    status = panda::modelstore::install_voice_pack(
        incoming.archive,
        voices,
        options,
        result
    );
    assert(status.code == ErrorCode::unsupported_schema);

    // The original pack must survive a refused overwrite untouched.
    panda::modelstore::Manifest survivor;
    const auto survivor_status = panda::modelstore::parse_manifest(
        voices / "test-voice" / "manifest.json",
        survivor
    );
    assert(survivor_status.ok());
    assert(survivor.schema_version == 1);
}

void test_remove_voice_pack() {
    std::cerr << "test: remove voice pack\n";
    const auto fixture = make_fixture("remove", false);
    const auto voices = fixture.root / "voices";

    panda::modelstore::InstallOptions options;
    panda::modelstore::InstallResult result;
    auto status = panda::modelstore::install_voice_pack(
        fixture.archive,
        voices,
        options,
        result
    );
    assert(status.ok());
    assert(fs::is_directory(voices / "test-voice"));

    status = panda::modelstore::remove_voice_pack(voices, "test-voice");
    assert(status.ok());
    assert(!fs::exists(voices / "test-voice"));
    // Removing a pack must not take the shared store with it.
    assert(fs::is_directory(voices));
}

void test_remove_rejects_unknown_and_unsafe_ids() {
    std::cerr << "test: remove rejects unknown and unsafe ids\n";
    const auto root = scratch_root("remove-safety");
    const auto voices = root / "voices";
    fs::create_directories(voices);

    assert(panda::modelstore::remove_voice_pack(voices, "missing-pack").code ==
           ErrorCode::not_found);
    assert(panda::modelstore::remove_voice_pack(voices, "../escape").code ==
           ErrorCode::invalid_manifest);
    assert(panda::modelstore::remove_voice_pack(voices, "Test-Voice").code ==
           ErrorCode::invalid_manifest);
    assert(panda::modelstore::remove_voice_pack(voices, "a/b").code ==
           ErrorCode::invalid_manifest);
}

void test_remove_refuses_a_mismatched_directory() {
    std::cerr << "test: remove refuses a mismatched directory\n";
    const auto root = scratch_root("remove-mismatch");
    const auto voices = root / "voices";

    // The directory name says "other-pack" but the manifest claims another id;
    // a mismatch must be refused rather than removed.
    json manifest{
        {"schema_version", 1},
        {"format", "panda.voice-pack"},
        {"id", "test-voice"},
        {"name", "Test Voice"},
        {"version", "1.0.0"},
        {"engine", "meanvc2"},
        {"kind", "zero-shot"},
        {"entry", "mvc2_test_rt.yaml"},
        {"assets_dir", "assets"},
        {"created_at", "2026-10-02T00:00:00Z"},
        {"files", json::array()},
    };
    write_text(voices / "other-pack" / "manifest.json", manifest.dump(2));

    const auto status =
        panda::modelstore::remove_voice_pack(voices, "other-pack");
    assert(status.code == ErrorCode::invalid_manifest);
    assert(fs::exists(voices / "other-pack"));
}

void test_expansion_limits_are_enforced() {
    std::cerr << "test: expansion limits\n";
    const auto fixture = make_fixture("limits", false);
    const auto voices = fixture.root / "voices";
    panda::modelstore::InstallOptions options;
    panda::modelstore::InstallResult result;

    // A declared file larger than the per-file cap is refused before the
    // voice root is even created -- nothing is extracted, nothing is staged.
    options.max_file_bytes = 4;
    auto status = panda::modelstore::install_voice_pack(
        fixture.archive,
        voices,
        options,
        result
    );
    assert(status.code == ErrorCode::limit_exceeded);
    assert(!fs::exists(voices));

    // And so is the sum of the declared sizes over the total cap.
    options.max_file_bytes = 1024ULL * 1024ULL;
    options.max_total_bytes = 8;
    status = panda::modelstore::install_voice_pack(
        fixture.archive,
        voices,
        options,
        result
    );
    assert(status.code == ErrorCode::limit_exceeded);
    assert(!fs::exists(voices));

    // The default limits still accept the real pack.
    options = panda::modelstore::InstallOptions{};
    status = panda::modelstore::install_voice_pack(
        fixture.archive,
        voices,
        options,
        result
    );
    assert(status.ok());
}

}  // namespace

int main() {
    const auto report = [](const char* name, const auto& body) {
        const auto started = std::chrono::steady_clock::now();
        body();
        const auto elapsed = std::chrono::duration<double>(
            std::chrono::steady_clock::now() - started
        ).count();
        std::cout << "timing: " << name << " = " << std::fixed
                  << std::setprecision(3) << elapsed << " s" << std::endl;
    };

    report("realtime-stats", run_realtime_stats_tests);
#ifdef _WIN32
    report("version", run_version_tests);
    report("path-validation", test_path_validation);
    report("install-scan-overwrite", test_install_scan_and_overwrite);
    report("checksum-atomic", test_checksum_failure_is_atomic);
    report("validation-api", test_validation_api);
    report("archive-traversal", test_archive_path_traversal_is_rejected);
    report("schema-mismatch", test_schema_mismatch_blocks_overwrite);
    report("remove-pack", test_remove_voice_pack);
    report("remove-safety", test_remove_rejects_unknown_and_unsafe_ids);
    report("remove-mismatch", test_remove_refuses_a_mismatched_directory);
    report("expansion-limits", test_expansion_limits_are_enforced);
#endif
    // CTest matches this marker. Without it a run that dies early could still
    // be reported as a pass, because that failure mode exits with status 0.
    std::cout << "PANDA_CORE_TESTS_COMPLETE" << std::endl;
    return 0;
}

