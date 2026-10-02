#include "session_store.hpp"

#include "worker_protocol.hpp"

#include <QSettings>
#include <QStringList>
#include <QVariant>

namespace panda::desktop {

namespace {

const QStringList kModels{QStringLiteral("40ms"), QStringLiteral("120ms")};
const QStringList kCompute{QStringLiteral("cpu"), QStringLiteral("cuda")};

QString sanitized_choice(
    const QVariant& value,
    const QStringList& allowed,
    const QString& fallback
) {
    const auto text = value.toString();
    return allowed.contains(text) ? text : fallback;
}

int sanitized_device(const QVariant& value) {
    if (!value.isValid()) {
        return -1;
    }
    const auto id = value.toInt();
    return id < 0 ? -1 : id;
}

}  // namespace

SessionStore::SessionStore(QObject* parent)
    : QObject(parent) {}

SessionStore::SessionStore(const QString& file_path, QObject* parent)
    : QObject(parent),
      override_path_(file_path) {}

QSettings SessionStore::make_settings() const {
    if (!override_path_.isEmpty()) {
        return QSettings(override_path_, QSettings::IniFormat);
    }
    return QSettings();
}

QVariantMap SessionStore::load() const {
    auto settings = make_settings();

    QVariantMap values;
    values[QStringLiteral("voicePack")] =
        settings.value(QStringLiteral("session/voice_pack"));
    values[QStringLiteral("model")] =
        settings.value(QStringLiteral("session/model"));
    values[QStringLiteral("compute")] =
        settings.value(QStringLiteral("session/compute"));
    values[QStringLiteral("inputDevice")] =
        settings.value(QStringLiteral("session/input_device"), -1);
    values[QStringLiteral("inputDeviceKey")] =
        settings.value(QStringLiteral("session/input_device_key"));
    values[QStringLiteral("outputDevice")] =
        settings.value(QStringLiteral("session/output_device"), -1);
    values[QStringLiteral("outputDeviceKey")] =
        settings.value(QStringLiteral("session/output_device_key"));
    values[QStringLiteral("monitorDevice")] =
        settings.value(QStringLiteral("session/monitor_device"), -1);
    values[QStringLiteral("monitorDeviceKey")] =
        settings.value(QStringLiteral("session/monitor_device_key"));
    values[QStringLiteral("prefillChunks")] =
        settings.value(QStringLiteral("session/prefill_chunks"), 1);
    values[QStringLiteral("maxBacklogChunks")] =
        settings.value(QStringLiteral("session/max_backlog_chunks"), 6);
    values[QStringLiteral("noiseGateEnabled")] =
        settings.value(QStringLiteral("session/noise_gate_enabled"), false);
    values[QStringLiteral("noiseGateDb")] =
        settings.value(QStringLiteral("session/noise_gate_db"), -45.0);
    values[QStringLiteral("outputGainDb")] =
        settings.value(QStringLiteral("session/output_gain_db"), 0.0);
    values[QStringLiteral("inputGainDb")] =
        settings.value(QStringLiteral("session/input_gain_db"), 0.0);
    values[QStringLiteral("monitorGainDb")] =
        settings.value(QStringLiteral("session/monitor_gain_db"), 0.0);
    values[QStringLiteral("denoise")] =
        settings.value(QStringLiteral("session/denoise"), false);
    values[QStringLiteral("denoiseLevel")] =
        settings.value(QStringLiteral("session/denoise_level"), "strong");

    return sanitize(values);
}

void SessionStore::save(const QVariantMap& values) const {
    const auto clean = sanitize(values);
    auto settings = make_settings();

    settings.setValue(
        QStringLiteral("session/voice_pack"),
        clean.value(QStringLiteral("voicePack"))
    );
    settings.setValue(
        QStringLiteral("session/model"),
        clean.value(QStringLiteral("model"))
    );
    settings.setValue(
        QStringLiteral("session/compute"),
        clean.value(QStringLiteral("compute"))
    );
    settings.setValue(
        QStringLiteral("session/input_device"),
        clean.value(QStringLiteral("inputDevice"))
    );
    settings.setValue(
        QStringLiteral("session/input_device_key"),
        clean.value(QStringLiteral("inputDeviceKey"))
    );
    settings.setValue(
        QStringLiteral("session/output_device"),
        clean.value(QStringLiteral("outputDevice"))
    );
    settings.setValue(
        QStringLiteral("session/output_device_key"),
        clean.value(QStringLiteral("outputDeviceKey"))
    );
    settings.setValue(
        QStringLiteral("session/monitor_device"),
        clean.value(QStringLiteral("monitorDevice"))
    );
    settings.setValue(
        QStringLiteral("session/monitor_device_key"),
        clean.value(QStringLiteral("monitorDeviceKey"))
    );
    settings.setValue(
        QStringLiteral("session/prefill_chunks"),
        clean.value(QStringLiteral("prefillChunks"))
    );
    settings.setValue(
        QStringLiteral("session/max_backlog_chunks"),
        clean.value(QStringLiteral("maxBacklogChunks"))
    );
    settings.setValue(
        QStringLiteral("session/noise_gate_enabled"),
        clean.value(QStringLiteral("noiseGateEnabled"))
    );
    settings.setValue(
        QStringLiteral("session/noise_gate_db"),
        clean.value(QStringLiteral("noiseGateDb"))
    );
    settings.setValue(
        QStringLiteral("session/output_gain_db"),
        clean.value(QStringLiteral("outputGainDb"))
    );
    settings.setValue(
        QStringLiteral("session/input_gain_db"),
        clean.value(QStringLiteral("inputGainDb"))
    );
    settings.setValue(
        QStringLiteral("session/monitor_gain_db"),
        clean.value(QStringLiteral("monitorGainDb"))
    );
    settings.setValue(
        QStringLiteral("session/denoise"),
        clean.value(QStringLiteral("denoise"))
    );
    settings.setValue(
        QStringLiteral("session/denoise_level"),
        clean.value(QStringLiteral("denoiseLevel"))
    );
    settings.sync();
}

void SessionStore::clear() const {
    auto settings = make_settings();
    settings.remove(QStringLiteral("session"));
    settings.sync();
}

QVariantMap SessionStore::sanitize(const QVariantMap& values) {
    QVariantMap clean;
    clean[QStringLiteral("voicePack")] =
        values.value(QStringLiteral("voicePack")).toString();
    clean[QStringLiteral("model")] = sanitized_choice(
        values.value(QStringLiteral("model")),
        kModels,
        QStringLiteral("120ms")
    );
    clean[QStringLiteral("compute")] = sanitized_choice(
        values.value(QStringLiteral("compute")),
        kCompute,
        QStringLiteral("cpu")
    );
    clean[QStringLiteral("inputDevice")] =
        sanitized_device(values.value(QStringLiteral("inputDevice")));
    clean[QStringLiteral("inputDeviceKey")] =
        values.value(QStringLiteral("inputDeviceKey")).toString();
    clean[QStringLiteral("outputDevice")] =
        sanitized_device(values.value(QStringLiteral("outputDevice")));
    clean[QStringLiteral("outputDeviceKey")] =
        values.value(QStringLiteral("outputDeviceKey")).toString();
    clean[QStringLiteral("monitorDevice")] =
        sanitized_device(values.value(QStringLiteral("monitorDevice")));
    clean[QStringLiteral("monitorDeviceKey")] =
        values.value(QStringLiteral("monitorDeviceKey")).toString();

    const auto latency = clamp_latency(
        values.value(QStringLiteral("prefillChunks"), 1).toInt(),
        values.value(QStringLiteral("maxBacklogChunks"), 6).toInt()
    );
    clean[QStringLiteral("prefillChunks")] = latency.prefill_chunks;
    clean[QStringLiteral("maxBacklogChunks")] = latency.max_backlog_chunks;
    clean[QStringLiteral("noiseGateEnabled")] =
        values.value(QStringLiteral("noiseGateEnabled")).toBool();
    clean[QStringLiteral("noiseGateDb")] = clamp_gate_db(
        values.value(QStringLiteral("noiseGateDb"), -45.0).toDouble()
    );
    clean[QStringLiteral("outputGainDb")] = clamp_output_gain_db(
        values.value(QStringLiteral("outputGainDb"), 0.0).toDouble()
    );
    clean[QStringLiteral("inputGainDb")] = clamp_input_gain_db(
        values.value(QStringLiteral("inputGainDb"), 0.0).toDouble()
    );
    clean[QStringLiteral("monitorGainDb")] = clamp_monitor_gain_db(
        values.value(QStringLiteral("monitorGainDb"), 0.0).toDouble()
    );
    clean[QStringLiteral("denoise")] =
        values.value(QStringLiteral("denoise")).toBool();
    clean[QStringLiteral("denoiseLevel")] = clamp_denoise_level(
        values.value(QStringLiteral("denoiseLevel"), "strong").toString()
    );
    return clean;
}

}  // namespace panda::desktop
