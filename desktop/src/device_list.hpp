#pragma once

#include <QByteArray>
#include <QString>
#include <QVariantList>

namespace panda::desktop {

struct DeviceList {
    bool ok{false};
    QString error;
    QVariantList inputs;
    QVariantList outputs;
    int default_input{-1};
    int default_output{-1};
};

// Parses the JSON produced by `panda devices --json`.
//
// Each entry carries an `isVirtual` flag so the UI can warn when the chosen
// output is a plain speaker: audio played there never reaches other
// applications, which is the most common "why can nobody hear me" mistake.
[[nodiscard]] DeviceList parse_device_payload(const QByteArray& value);

}  // namespace panda::desktop
