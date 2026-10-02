#include "device_list.hpp"

#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonParseError>
#include <QVariantMap>

namespace panda::desktop {

DeviceList parse_device_payload(const QByteArray& value) {
    DeviceList result;

    QJsonParseError error;
    const auto document = QJsonDocument::fromJson(value, &error);
    if (error.error != QJsonParseError::NoError || !document.isObject()) {
        result.error = QStringLiteral("设备列表不是有效 JSON");
        return result;
    }

    const auto root = document.object();
    const auto devices = root.value(QStringLiteral("devices")).toArray();
    const auto hostapis = root.value(QStringLiteral("hostapis")).toArray();
    const auto defaults = root.value(QStringLiteral("default")).toArray();

    for (int index = 0; index < devices.size(); ++index) {
        const auto device = devices.at(index).toObject();
        const auto id = device.value(QStringLiteral("index")).toInt(index);
        const auto name = device.value(QStringLiteral("name")).toString();
        const auto hostapi = device.value(QStringLiteral("hostapi")).toInt(-1);
        const auto host_name = hostapi >= 0 && hostapi < hostapis.size()
            ? hostapis.at(hostapi).toString()
            : QStringLiteral("unknown");
        const auto label = QStringLiteral("#%1 %2 · %3")
                               .arg(id)
                               .arg(name, host_name);
        const auto entry = QVariantMap{
            {QStringLiteral("id"), id},
            {QStringLiteral("label"), label},
            {QStringLiteral("deviceName"), name},
            {QStringLiteral("hostApi"), host_name},
            {QStringLiteral("isVirtual"),
             device.value(QStringLiteral("is_virtual")).toBool(false)},
        };
        if (device.value(QStringLiteral("max_input_channels")).toInt() > 0) {
            result.inputs.append(entry);
        }
        if (device.value(QStringLiteral("max_output_channels")).toInt() > 0) {
            result.outputs.append(entry);
        }
    }

    result.default_input = defaults.size() > 0 ? defaults.at(0).toInt(-1) : -1;
    result.default_output = defaults.size() > 1 ? defaults.at(1).toInt(-1) : -1;
    result.ok = true;
    return result;
}

}  // namespace panda::desktop
