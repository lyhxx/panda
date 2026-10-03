#include "panda/audio/realtime_stats.hpp"
#include "realtime_stats_test.hpp"

#include <cassert>
#include <cmath>

namespace {

bool near(double left, double right) {
    return std::abs(left - right) < 0.0001;
}

}  // namespace

void run_realtime_stats_tests() {
    // Panda metrics line, as emitted by panda_infer.realtime_worker.
    const auto metrics = panda::audio::parse_realtime_stats(
        R"([panda.metrics] {"chunk":123,"processing_ms":115.3,"chunk_ms":160.0,)"
        R"("buffer_ms":200.0,"overrun":false,"mean_ms":118.9,"max_ms":133.1,)"
        R"("input_rms":0.021,"input_peak":0.18,"output_rms":0.04,)"
        R"("output_peak":0.72,"input_clipped":false,"output_clipped":false,)"
        R"("starved_reads":0,"underrun_frames":0,"dropped_frames":12,)"
        R"("trimmed_frames":4160,"input_latency_ms":40.0,)"
        R"("output_latency_ms":40.0,"device_block_ms":20.0})"
    );
    assert(metrics.has_value());
    assert(metrics->chunk_index == 123);
    assert(near(metrics->processing_ms, 115.3));
    assert(near(metrics->chunk_ms, 160.0));
    assert(near(metrics->buffer_ms, 200.0));
    assert(!metrics->overrun);
    assert(near(metrics->mean_ms, 118.9));
    assert(near(metrics->max_ms, 133.1));
    assert(near(metrics->input_rms, 0.021));
    assert(near(metrics->input_peak, 0.18));
    assert(near(metrics->output_rms, 0.04));
    assert(near(metrics->output_peak, 0.72));
    assert(!metrics->input_clipped);
    assert(!metrics->output_clipped);
    assert(metrics->starved_reads == 0);
    assert(metrics->underrun_frames == 0);
    assert(metrics->dropped_frames == 12);
    assert(metrics->trimmed_frames == 4160);
    assert(near(metrics->input_latency_ms, 40.0));
    assert(near(metrics->output_latency_ms, 40.0));
    assert(near(metrics->device_block_ms, 20.0));
    // Device capture + our buffer + conversion + device playback. The device
    // terms are charged on top of our queue, so leaving them out made the
    // readout systematically better than the delay the listener heard.
    assert(near(metrics->total_latency_ms(), 40.0 + 200.0 + 115.3 + 40.0));

    const auto metrics_overrun = panda::audio::parse_realtime_stats(
        R"([panda.metrics] {"chunk":7,"processing_ms":190.5,"chunk_ms":160.0,)"
        R"("buffer_ms":0.0,"overrun":true})"
    );
    assert(metrics_overrun.has_value());
    assert(metrics_overrun->chunk_index == 7);
    assert(metrics_overrun->overrun);
    assert(near(metrics_overrun->realtime_factor(), 1.190625));
    // Optional context fields are absent here, so they stay zero.
    assert(near(metrics_overrun->mean_ms, 0.0));
    // Without device terms the total still degrades to our own two terms
    // instead of pretending there is no device in the path.
    assert(near(metrics_overrun->input_latency_ms, 0.0));
    assert(near(metrics_overrun->total_latency_ms(), 190.5));

    // Legacy upstream console format must keep working.
    const auto ok = panda::audio::parse_realtime_stats(
        "[10] 3.2ms / 160ms OK  buf=0ms"
    );
    assert(ok.has_value());
    assert(ok->chunk_index == 10);
    assert(near(ok->processing_ms, 3.2));
    assert(near(ok->chunk_ms, 160.0));
    assert(near(ok->buffer_ms, 0.0));
    assert(!ok->overrun);
    assert(near(ok->realtime_factor(), 0.02));

    const auto overrun = panda::audio::parse_realtime_stats(
        "[42] 180.5ms / 160ms warning OVERRUN  buf=12.5ms"
    );
    assert(overrun.has_value());
    assert(overrun->chunk_index == 42);
    assert(overrun->overrun);
    assert(near(overrun->realtime_factor(), 1.128125));

    assert(!panda::audio::parse_realtime_stats(
        "[Init] Loading VC model..."
    ).has_value());
    // A truncated metrics payload must be rejected, not guessed at.
    assert(!panda::audio::parse_realtime_stats(
        R"([panda.metrics] {"chunk":1,)"
    ).has_value());
    assert(!panda::audio::parse_realtime_stats(
        R"([panda.metrics] {"chunk":1})"
    ).has_value());
}
