#include "panda/modelstore/installer.hpp"
#include "panda/version.hpp"

#include <filesystem>
#include <iostream>
#include <string>
#include <string_view>

namespace {

namespace fs = std::filesystem;
using panda::Status;

void print_usage() {
    std::cout
        << "Panda " << panda::version_string() << "\n\n"
        << "Usage:\n"
        << "  panda_cli version\n"
        << "  panda_cli install <pack.zip> <voices-root> [--overwrite]\n"
        << "  panda_cli validate <pack.zip>\n"
        << "  panda_cli list <voices-root>\n"
        << "  panda_cli remove <voices-root> <pack-id>\n";
}

int fail(const Status& status) {
    std::cerr << "error: "
              << static_cast<int>(status.code)
              << ": "
              << status.message
              << '\n';
    return 1;
}

int command_install(int argc, char** argv) {
    if (argc < 4 || argc > 5) {
        print_usage();
        return 2;
    }

    panda::modelstore::InstallOptions options;
    if (argc == 5) {
        if (std::string_view(argv[4]) != "--overwrite") {
            std::cerr << "unknown option: " << argv[4] << '\n';
            return 2;
        }
        options.overwrite = true;
    }

    panda::modelstore::InstallResult result;
    const auto status = panda::modelstore::install_voice_pack(
        fs::path(argv[2]),
        fs::path(argv[3]),
        options,
        result
    );
    if (!status.ok()) {
        return fail(status);
    }

    std::cout << "installed: " << result.manifest.name
              << " (" << result.manifest.id << ")\n"
              << "path: " << result.installed_path << '\n';
    return 0;
}

int command_validate(int argc, char** argv) {
    if (argc != 3) {
        print_usage();
        return 2;
    }

    panda::modelstore::InstallOptions options;
    panda::modelstore::Manifest manifest;
    const auto status = panda::modelstore::validate_voice_pack(
        fs::path(argv[2]),
        options,
        manifest
    );
    if (!status.ok()) {
        return fail(status);
    }

    std::cout << "valid: " << manifest.name
              << " (" << manifest.id << ")"
              << " version " << manifest.version
              << '\n';
    return 0;
}

int command_list(int argc, char** argv) {
    if (argc != 3) {
        print_usage();
        return 2;
    }

    std::vector<panda::modelstore::Manifest> manifests;
    const auto status = panda::modelstore::scan_voice_packs(
        fs::path(argv[2]),
        manifests
    );
    if (!status.ok()) {
        return fail(status);
    }

    for (const auto& manifest : manifests) {
        std::cout << manifest.id << "\t" << manifest.name << "\n";
    }
    return 0;
}

int command_remove(int argc, char** argv) {
    if (argc != 4) {
        print_usage();
        return 2;
    }

    const auto status = panda::modelstore::remove_voice_pack(
        fs::path(argv[2]),
        std::string(argv[3])
    );
    if (!status.ok()) {
        return fail(status);
    }

    std::cout << "removed: " << argv[3] << '\n';
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) {
        print_usage();
        return 0;
    }

    const std::string_view command(argv[1]);
    if (command == "version" || command == "--version") {
        std::cout << "Panda " << panda::version_string() << '\n';
        return 0;
    }
    if (command == "install") {
        return command_install(argc, argv);
    }
    if (command == "validate") {
        return command_validate(argc, argv);
    }
    if (command == "list") {
        return command_list(argc, argv);
    }
    if (command == "remove") {
        return command_remove(argc, argv);
    }

    std::cerr << "unknown command: " << command << '\n';
    print_usage();
    return 2;
}

