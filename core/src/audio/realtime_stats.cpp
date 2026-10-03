#include "panda/audio/realtime_stats.hpp"

#include <nlohmann/json.hpp>

#include <regex>
#include <string>
#include <string_view>

namespace panda::audio {

namespace {

using Json = nlohmann::json;

const std::regex& stats_pattern() {
    static const std::regex pattern(
        R"(\[([0-9]+)\]\s+([0-9]+(?:\.[0-9]+)?)ms\s*/\s*([0-9]+(?:\.[0-9]+)?)ms\s+(?:[^\s]+\s+)?(OVERRUN|OK)\s+buf=([0-9]+(?:\.[0-9]+)?)ms)",
        std::regex::optimize
    );
    return pattern;
}

std::optional<double> parse_number(const std::ssub_match& value) {
    try {
        return std::stod(value.str());
    } catch (...) {
        return std::nullopt;
    }
}

std::optional<double> json_number(const Json& object, const char* key) {
    const auto found = object.find(key);
    if (found == object.end() || !found->is_number()) {
        return std::nullopt;
    }
    return found->get<double>();
}

std::uint64_t json_counter(const Json& object, const char* key) {
    const auto found = object.find(key);
    if (found == object.end() || !found->is_number_unsigned()) {
        return 0;
    }
    return found->get<std::uint64_t>();
}

std::string_view trim_left(std::string_view value) {
    while (!value.empty()) {
        const auto ch = value.front();
        if (ch != ' ' && ch != '\t') {
            break;
        }
        value.remove_prefix(1);
    }
    return value;
}

std::optional<RealtimeStats> parse_metrics_line(std::string_view line) {
    if (!line.starts_with(kMetricsPrefix)) {
        return std::nullopt;
    }

    const auto payload = trim_left(line.substr(kMetricsPrefix.size()));
    const auto parsed = Json::parse(
        payload.begin(),
        payload.end(),
        nullptr,
        false
    );
    if (parsed.is_discarded() || !parsed.is_object()) {
        return std::nullopt;
    }

    const auto processing = json_number(parsed, "processing_ms");
    const auto chunk = json_number(parsed, "chunk_ms");
    const auto buffer = json_number(parsed, "buffer_ms");
    if (!processing || !chunk || !buffer) {
        return std::nullopt;
    }

    bool overrun = false;
    const auto overrun_field = parsed.find("overrun");
    if (overrun_field != parsed.end() && overrun_field->is_boolean()) {
        overrun = overrun_field->get<bool>();
    }

    // nlohmann's value() throws type_error when the field exists with the
    // wrong type; a malformed metrics line must never take the app down.
    const auto clipped = [&parsed](const char* key) {
        const auto found = parsed.find(key);
        return found != parsed.end() && found->is_boolean() &&
               found->get<bool>();
    };

    return RealtimeStats{
        .chunk_index = json_counter(parsed, "chunk"),
        .processing_ms = *processing,
        .chunk_ms = *chunk,
        .buffer_ms = *buffer,
        .overrun = overrun,
        .mean_ms = json_number(parsed, "mean_ms").value_or(0.0),
        .max_ms = json_number(parsed, "max_ms").value_or(0.0),
        .input_rms = json_number(parsed, "input_rms").value_or(0.0),
        .input_peak = json_number(parsed, "input_peak").value_or(0.0),
        .output_rms = json_number(parsed, "output_rms").value_or(0.0),
        .output_peak = json_number(parsed, "output_peak").value_or(0.0),
        .input_clipped = clipped("input_clipped"),
        .output_clipped = clipped("output_clipped"),
        .starved_reads = json_counter(parsed, "starved_reads"),
        .underrun_frames = json_counter(parsed, "underrun_frames"),
        .dropped_frames = json_counter(parsed, "dropped_frames"),
        .trimmed_frames = json_counter(parsed, "trimmed_frames"),
        .input_latency_ms = json_number(parsed, "input_latency_ms").value_or(0.0),
        .output_latency_ms = json_number(parsed, "output_latency_ms").value_or(0.0),
        .device_block_ms = json_number(parsed, "device_block_ms").value_or(0.0),
    };
}

std::optional<RealtimeStats> parse_legacy_line(std::string_view line) {
    const std::string text(line);
    std::smatch match;
    if (!std::regex_match(text, match, stats_pattern())) {
        return std::nullopt;
    }

    const auto processing = parse_number(match[2]);
    const auto chunk = parse_number(match[3]);
    const auto buffer = parse_number(match[5]);
    if (!processing || !chunk || !buffer) {
        return std::nullopt;
    }

    std::uint64_t chunk_index = 0;
    try {
        chunk_index = std::stoull(match[1].str());
    } catch (...) {
        return std::nullopt;
    }

    return RealtimeStats{
        .chunk_index = chunk_index,
        .processing_ms = *processing,
        .chunk_ms = *chunk,
        .buffer_ms = *buffer,
        .overrun = match[4].str() == "OVERRUN",
    };
}

}  // namespace

double RealtimeStats::realtime_factor() const noexcept {
    if (chunk_ms <= 0.0) {
        return 0.0;
    }
    return processing_ms / chunk_ms;
}

double RealtimeStats::total_latency_ms() const noexcept {
    return input_latency_ms + buffer_ms + processing_ms + output_latency_ms;
}

std::optional<RealtimeStats> parse_realtime_stats(std::string_view line) {
    if (auto metrics = parse_metrics_line(line)) {
        return metrics;
    }
    return parse_legacy_line(line);
}

}  // namespace panda::audio
