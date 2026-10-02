#include "worker_protocol.hpp"

#include "panda/audio/realtime_stats.hpp"

#include <cmath>

namespace panda::desktop {

namespace {

constexpr int kMinPrefillChunks = 0;
constexpr int kMaxPrefillChunks = 8;
constexpr int kMinBacklogChunks = 2;
constexpr int kMaxBacklogChunks = 32;

int clamp(int value, int low, int high) {
    if (value < low) {
        return low;
    }
    return value > high ? high : value;
}

}  // namespace

LatencySettings clamp_latency(int prefill_chunks, int backlog_chunks) {
    LatencySettings settings;
    settings.prefill_chunks = clamp(
        prefill_chunks,
        kMinPrefillChunks,
        kMaxPrefillChunks
    );
    settings.max_backlog_chunks = clamp(
        backlog_chunks,
        kMinBacklogChunks,
        kMaxBacklogChunks
    );
    if (settings.max_backlog_chunks <= settings.prefill_chunks) {
        settings.max_backlog_chunks = settings.prefill_chunks + 1;
    }
    return settings;
}

double clamp_gate_db(double value) {
    constexpr double kMinGateDb = -90.0;
    constexpr double kMaxGateDb = -10.0;
    if (value < kMinGateDb) {
        return kMinGateDb;
    }
    return value > kMaxGateDb ? kMaxGateDb : value;
}

double clamp_output_gain_db(double value) {
    constexpr double kMinGainDb = -24.0;
    constexpr double kMaxGainDb = 12.0;
    if (value < kMinGainDb) {
        return kMinGainDb;
    }
    return value > kMaxGainDb ? kMaxGainDb : value;
}

double clamp_input_gain_db(double value) {
    constexpr double kMinGainDb = -24.0;
    constexpr double kMaxGainDb = 12.0;
    if (value < kMinGainDb) {
        return kMinGainDb;
    }
    return value > kMaxGainDb ? kMaxGainDb : value;
}

double clamp_monitor_gain_db(double value) {
    constexpr double kMinGainDb = -24.0;
    constexpr double kMaxGainDb = 12.0;
    if (value < kMinGainDb) {
        return kMinGainDb;
    }
    return value > kMaxGainDb ? kMaxGainDb : value;
}

bool should_restart_realtime(
    bool stop_requested,
    int exit_code,
    bool crashed,
    int attempts,
    int max_attempts
) {
    if (stop_requested || attempts >= max_attempts) {
        return false;
    }
    return crashed || exit_code != 0;
}

QString clamp_denoise_level(const QString& value) {
    if (value == QStringLiteral("strong") ||
        value == QStringLiteral("balanced") ||
        value == QStringLiteral("gentle")) {
        return value;
    }
    return QStringLiteral("strong");
}

QStringList build_realtime_arguments(const RealtimeOptions& options) {
    QStringList arguments{
        QStringLiteral("-m"),
        QStringLiteral("panda_infer.realtime_worker"),
        QStringLiteral("--meanvc2-root"),
        options.meanvc2_root,
        QStringLiteral("--voice-pack"),
        options.voice_pack,
        QStringLiteral("--model"),
        options.model,
        QStringLiteral("--device"),
        options.device,
    };

    if (options.input_device >= 0) {
        arguments << QStringLiteral("--input-device")
                  << QString::number(options.input_device);
    }
    if (options.output_disabled) {
        arguments << QStringLiteral("--output-device")
                  << QStringLiteral("-1");
    }
    else if (options.output_device >= 0) {
        arguments << QStringLiteral("--output-device")
                  << QString::number(options.output_device);
    }
    if (options.monitor_device >= 0) {
        arguments << QStringLiteral("--monitor-device")
                  << QString::number(options.monitor_device);
    }
    if (!options.input_device_name.isEmpty()) {
        arguments << QStringLiteral("--input-name-b64")
                  << QString::fromLatin1(
                         options.input_device_name.toUtf8().toBase64()
                     );
    }
    if (!options.output_device_name.isEmpty()) {
        arguments << QStringLiteral("--output-name-b64")
                  << QString::fromLatin1(
                         options.output_device_name.toUtf8().toBase64()
                     );
    }
    if (!options.monitor_device_name.isEmpty()) {
        arguments << QStringLiteral("--monitor-name-b64")
                  << QString::fromLatin1(
                         options.monitor_device_name.toUtf8().toBase64()
                     );
    }
    if (options.prefill_chunks >= 0) {
        arguments << QStringLiteral("--prefill-chunks")
                  << QString::number(options.prefill_chunks);
    }
    if (options.max_backlog_chunks > 0) {
        arguments << QStringLiteral("--max-backlog-chunks")
                  << QString::number(options.max_backlog_chunks);
    }
    if (options.noise_gate_enabled) {
        arguments << QStringLiteral("--noise-gate-db")
                  << QString::number(options.noise_gate_db, 'f', 1);
    }
    if (options.limiter_ceiling > 0.0) {
        arguments << QStringLiteral("--limiter-ceiling")
                  << QString::number(options.limiter_ceiling, 'f', 3);
    }
    if (std::abs(options.input_gain_db) > 1e-6) {
        arguments << QStringLiteral("--input-gain-db")
                  << QString::number(options.input_gain_db, 'f', 1);
    }
    if (std::abs(options.output_gain_db) > 1e-6) {
        arguments << QStringLiteral("--output-gain-db")
                  << QString::number(options.output_gain_db, 'f', 1);
    }
    if (std::abs(options.monitor_gain_db) > 1e-6) {
        arguments << QStringLiteral("--monitor-gain-db")
                  << QString::number(options.monitor_gain_db, 'f', 1);
    }
    if (options.denoise) {
        arguments << QStringLiteral("--denoise")
                  << QStringLiteral("--denoise-level")
                  << clamp_denoise_level(options.denoise_level);
    }

    return arguments;
}

QStringList build_preview_arguments(
    const QString& voice_pack,
    int output_device
) {
    QStringList arguments{
        QStringLiteral("-m"),
        QStringLiteral("panda_cli"),
        QStringLiteral("preview"),
        QStringLiteral("--voice-pack"),
        voice_pack,
    };
    if (output_device >= 0) {
        arguments << QStringLiteral("--output-device")
                  << QString::number(output_device);
    }
    return arguments;
}

QStringList build_mic_test_arguments(
    int input_device,
    int output_device
) {
    QStringList arguments{
        QStringLiteral("-m"),
        QStringLiteral("panda_cli"),
        QStringLiteral("mic-test"),
    };
    if (input_device >= 0) {
        arguments << QStringLiteral("--input-device")
                  << QString::number(input_device);
    }
    if (output_device >= 0) {
        arguments << QStringLiteral("--output-device")
                  << QString::number(output_device);
    }
    return arguments;
}

QStringList build_route_check_arguments() {
    return {
        QStringLiteral("-m"),
        QStringLiteral("panda_cli"),
        QStringLiteral("route-check"),
        QStringLiteral("--json"),
    };
}

bool is_metrics_line(const QString& line) {
    static const QString prefix = QString::fromLatin1(
        panda::audio::kMetricsPrefix.data(),
        static_cast<int>(panda::audio::kMetricsPrefix.size())
    );
    return line.startsWith(prefix);
}

}  // namespace panda::desktop
