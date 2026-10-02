#pragma once

#include <string_view>

// Single source of truth for the product identity.
//
// Everything that shows the product name (window title, About, docs, package
// metadata) should reference these constants instead of hard-coding the name,
// so a rename only touches this file.
namespace panda {

inline constexpr std::string_view kProductName = "熊猫变声器";
inline constexpr std::string_view kProductNameEn = "Panda Voice Changer";
// Stable, ASCII, technical identifier used for paths, packages and settings.
inline constexpr std::string_view kProductId = "panda";

}  // namespace panda
