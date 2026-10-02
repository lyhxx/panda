#pragma once

#include <QString>
#include <QStringList>

namespace panda::desktop {

struct RealtimeOptions {
    QString meanvc2_root;
    QString voice_pack;
    QString model{"120ms"};
    QString device{"cpu"};
    int input_device{-1};
    int output_device{-1};
    // Friendly names, resolved to the current index by the worker. PortAudio
    // renumbers devices between processes, so these are what actually select
    // the right device.
    QString input_device_name;
    QString output_device_name;
    QString monitor_device_name;
    // When set, the worker captures but renders nothing to an output device;
    // monitoring can still play the converted voice.
    bool output_disabled{false};
    int monitor_device{-1};
    int prefill_chunks{1};
    int max_backlog_chunks{6};
    bool noise_gate_enabled{false};
    double noise_gate_db{-45.0};
    double limiter_ceiling{0.891};
    double input_gain_db{0.0};
    double output_gain_db{0.0};
    double monitor_gain_db{0.0};
    bool denoise{false};
    QString denoise_level{"strong"};
};

struct LatencySettings {
    int prefill_chunks{2};
    int max_backlog_chunks{6};
};

// Bounds user-entered latency settings. A pre-roll is added startup latency,
// so keep it small; the backlog bound must stay strictly above the pre-roll or
// the buffer would discard the very audio it just primed with.
[[nodiscard]] LatencySettings clamp_latency(int prefill_chunks, int backlog_chunks);

// Bounds the noise-gate threshold to a range that is useful for speech: above
// -10 dBFS it would gate normal talking, below -90 dBFS it would never open.
[[nodiscard]] double clamp_gate_db(double value);

// Bounds the output gain to a range that is useful without allowing a
// configuration mistake to create an extremely loud signal.
[[nodiscard]] double clamp_output_gain_db(double value);

[[nodiscard]] double clamp_input_gain_db(double value);

[[nodiscard]] double clamp_monitor_gain_db(double value);

// Decides whether an unexpectedly ended realtime worker should be restarted.
// A deliberate stop and a normal exit are never restarted.
[[nodiscard]] bool should_restart_realtime(
    bool stop_requested,
    int exit_code,
    bool crashed,
    int attempts,
    int max_attempts = 3
);

// Keeps the denoise selector within the levels understood by the Python
// worker. Unknown values fall back to the strongest setting.
[[nodiscard]] QString clamp_denoise_level(const QString& value);

// Builds the argv for `python -m panda_cli realtime ...`.
//
// Kept separate from the controller so the exact command line is covered by
// tests instead of only being observable by starting a real stream.
[[nodiscard]] QStringList build_realtime_arguments(const RealtimeOptions& options);

// Builds the argv for `python -m panda_cli preview ...`.
[[nodiscard]] QStringList build_preview_arguments(
    const QString& voice_pack,
    int output_device
);

[[nodiscard]] QStringList build_mic_test_arguments(
    int input_device,
    int output_device
);

[[nodiscard]] QStringList build_route_check_arguments();

// True when a line from the worker carries `[panda.metrics]` JSON. Those
// lines feed the numeric display and must stay out of the log pane, otherwise
// the pane is flooded at two lines per second.
[[nodiscard]] bool is_metrics_line(const QString& line);

}  // namespace panda::desktop
