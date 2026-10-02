#pragma once

#include <string>
#include <utility>

namespace panda {

enum class ErrorCode {
    none,
    invalid_argument,
    io_error,
    invalid_archive,
    unsafe_path,
    invalid_manifest,
    unsupported_schema,
    unsupported_engine,
    checksum_mismatch,
    already_exists,
    limit_exceeded,
    install_failed,
    not_found,
};

struct Status {
    ErrorCode code{ErrorCode::none};
    std::string message;

    [[nodiscard]] bool ok() const noexcept {
        return code == ErrorCode::none;
    }

    static Status success() {
        return {};
    }

    static Status error(ErrorCode code_value, std::string message_value) {
        return Status{code_value, std::move(message_value)};
    }
};

}  // namespace panda

