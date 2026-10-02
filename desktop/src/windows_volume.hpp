#pragma once

#include <QString>

#include <optional>

namespace panda::desktop {

// Windows endpoint master volume, so the app's sliders show the same values as
// the system mixer instead of an app-private gain. Matching is by endpoint
// friendly name, which is what sounddevice/PortAudio reports as the device
// name. On non-Windows builds these are no-ops.

// Master volume as 0..1, or nullopt when the endpoint cannot be found.
[[nodiscard]] std::optional<double> endpoint_volume(
    const QString& deviceName,
    bool render
);

// Sets the master volume (clamped to 0..1). Returns false when not found.
bool set_endpoint_volume(
    const QString& deviceName,
    bool render,
    double scalar
);

}  // namespace panda::desktop
