#include "panda/crypto/sha256.hpp"

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <bcrypt.h>
#endif

#include <array>
#include <fstream>
#include <iomanip>
#include <sstream>

namespace panda::crypto {

namespace {

#ifdef _WIN32

std::string hex_encode(const std::array<unsigned char, 32>& bytes) {
    std::ostringstream stream;
    stream << std::hex << std::setfill('0');
    for (const auto value : bytes) {
        stream << std::setw(2) << static_cast<unsigned int>(value);
    }
    return stream.str();
}

#endif

}  // namespace

Status sha256_file(const std::filesystem::path& path, std::string& digest) {
#ifndef _WIN32
    (void)path;
    (void)digest;
    return Status::error(
        ErrorCode::install_failed,
        "SHA-256 is currently implemented only on Windows"
    );
#else
    digest.clear();

    std::ifstream input(path, std::ios::binary);
    if (!input) {
        return Status::error(ErrorCode::io_error, "failed to open file for SHA-256");
    }

    BCRYPT_ALG_HANDLE algorithm = nullptr;
    BCRYPT_HASH_HANDLE hash = nullptr;
    NTSTATUS status = BCryptOpenAlgorithmProvider(
        &algorithm,
        BCRYPT_SHA256_ALGORITHM,
        nullptr,
        0
    );
    if (status < 0) {
        return Status::error(ErrorCode::install_failed, "BCryptOpenAlgorithmProvider failed");
    }

    DWORD object_size = 0;
    DWORD bytes_written = 0;
    status = BCryptGetProperty(
        algorithm,
        BCRYPT_OBJECT_LENGTH,
        reinterpret_cast<PUCHAR>(&object_size),
        sizeof(object_size),
        &bytes_written,
        0
    );
    if (status < 0) {
        BCryptCloseAlgorithmProvider(algorithm, 0);
        return Status::error(ErrorCode::install_failed, "BCryptGetProperty failed");
    }

    std::vector<unsigned char> object(object_size);
    status = BCryptCreateHash(
        algorithm,
        &hash,
        object.data(),
        object_size,
        nullptr,
        0,
        0
    );
    if (status < 0) {
        BCryptCloseAlgorithmProvider(algorithm, 0);
        return Status::error(ErrorCode::install_failed, "BCryptCreateHash failed");
    }

    std::array<char, 64 * 1024> buffer{};
    while (input) {
        input.read(buffer.data(), static_cast<std::streamsize>(buffer.size()));
        const auto count = input.gcount();
        if (count > 0) {
            status = BCryptHashData(
                hash,
                reinterpret_cast<PUCHAR>(buffer.data()),
                static_cast<ULONG>(count),
                0
            );
            if (status < 0) {
                BCryptDestroyHash(hash);
                BCryptCloseAlgorithmProvider(algorithm, 0);
                return Status::error(ErrorCode::install_failed, "BCryptHashData failed");
            }
        }
    }

    if (!input.eof()) {
        BCryptDestroyHash(hash);
        BCryptCloseAlgorithmProvider(algorithm, 0);
        return Status::error(ErrorCode::io_error, "failed while reading file for SHA-256");
    }

    std::array<unsigned char, 32> hash_bytes{};
    status = BCryptFinishHash(
        hash,
        hash_bytes.data(),
        static_cast<ULONG>(hash_bytes.size()),
        0
    );
    BCryptDestroyHash(hash);
    BCryptCloseAlgorithmProvider(algorithm, 0);

    if (status < 0) {
        return Status::error(ErrorCode::install_failed, "BCryptFinishHash failed");
    }

    digest = hex_encode(hash_bytes);
    return Status::success();
#endif
}

}  // namespace panda::crypto

