#pragma once

#include <cstdint>
#include <optional>
#include <string_view>

namespace panda::audio {

// Prefix of the metrics line emitted by panda_infer.realtime_worker.
inline constexpr std::string_view kMetricsPrefix = "[panda.metrics]";

struct RealtimeStats {
    std::uint64_t chunk_index{0};
    double processing_ms{0.0};
    double chunk_ms{0.0};
    double buffer_ms{0.0};
    bool overrun{false};

    // Session context. Only the Panda metrics line carries these; they stay
    // zero when parsing the legacy upstream console format.
    double mean_ms{0.0};
    double max_ms{0.0};
    double input_rms{0.0};
    double input_peak{0.0};
    double output_rms{0.0};
    double output_peak{0.0};
    bool input_clipped{false};
    bool output_clipped{false};
    std::uint64_t starved_reads{0};
    std::uint64_t underrun_frames{0};
    std::uint64_t dropped_frames{0};
    std::uint64_t trimmed_frames{0};

    [[nodiscard]] double realtime_factor() const noexcept;
};

[[nodiscard]] std::optional<RealtimeStats> parse_realtime_stats(
    std::string_view line
);

}  // namespace panda::audio
