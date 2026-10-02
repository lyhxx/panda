// Headless tests for the realtime launch command line and the metrics/log
// split of the worker output.

#include "worker_protocol.hpp"

#include <QTest>

using panda::desktop::RealtimeOptions;
using panda::desktop::build_realtime_arguments;
using panda::desktop::build_preview_arguments;
using panda::desktop::build_mic_test_arguments;
using panda::desktop::build_route_check_arguments;
using panda::desktop::clamp_denoise_level;
using panda::desktop::clamp_gate_db;
using panda::desktop::clamp_latency;
using panda::desktop::clamp_output_gain_db;
using panda::desktop::clamp_input_gain_db;
using panda::desktop::clamp_monitor_gain_db;
using panda::desktop::should_restart_realtime;
using panda::desktop::is_metrics_line;

namespace {

int index_of(const QStringList& arguments, const QString& flag) {
    return arguments.indexOf(flag);
}

QString value_of(const QStringList& arguments, const QString& flag) {
    const auto index = index_of(arguments, flag);
    return index >= 0 && index + 1 < arguments.size()
        ? arguments.at(index + 1)
        : QString();
}

}  // namespace

class WorkerProtocolTest : public QObject {
    Q_OBJECT

private slots:
    void builds_the_module_invocation();
    void passes_model_and_device();
    void omits_devices_that_are_not_selected();
    void disables_output_when_requested();
    void includes_latency_controls();
    void includes_the_monitor_device();
    void recognises_metrics_lines();
    void keeps_ordinary_output_out_of_the_metrics_bucket();
    void accepts_reasonable_latency_settings();
    void clamps_out_of_range_latency_settings();
    void keeps_the_backlog_above_the_prefill();
    void includes_the_noise_gate_only_when_enabled();
    void clamps_the_gate_threshold();
    void clamps_the_output_gain();
    void clamps_the_input_gain();
    void clamps_the_monitor_gain();
    void decides_when_to_restart_a_crashed_worker();
    void builds_the_preview_invocation();
    void builds_the_microphone_test_invocation();
    void builds_the_route_check_invocation();
    void includes_denoise_only_when_enabled();
    void clamps_the_denoise_level();
};

void WorkerProtocolTest::builds_the_module_invocation() {
    RealtimeOptions options;
    options.meanvc2_root = QStringLiteral("D:/MeanVC2");
    options.voice_pack = QStringLiteral("D:/voices/manbo");

    const auto arguments = build_realtime_arguments(options);

    QCOMPARE(arguments.at(0), QStringLiteral("-m"));
    // The worker is launched directly (single process) so stopping the job
    // actually kills it instead of leaving a child holding the microphone.
    QCOMPARE(arguments.at(1), QStringLiteral("panda_infer.realtime_worker"));
    QCOMPARE(
        value_of(arguments, QStringLiteral("--meanvc2-root")),
        QStringLiteral("D:/MeanVC2")
    );
    QCOMPARE(
        value_of(arguments, QStringLiteral("--voice-pack")),
        QStringLiteral("D:/voices/manbo")
    );
}

void WorkerProtocolTest::passes_model_and_device() {
    RealtimeOptions options;
    options.model = QStringLiteral("120ms");
    options.device = QStringLiteral("cuda");

    const auto arguments = build_realtime_arguments(options);

    QCOMPARE(
        value_of(arguments, QStringLiteral("--model")),
        QStringLiteral("120ms")
    );
    QCOMPARE(
        value_of(arguments, QStringLiteral("--device")),
        QStringLiteral("cuda")
    );
}

void WorkerProtocolTest::omits_devices_that_are_not_selected() {
    RealtimeOptions options;

    const auto arguments = build_realtime_arguments(options);

    QCOMPARE(index_of(arguments, QStringLiteral("--input-device")), -1);
    QCOMPARE(index_of(arguments, QStringLiteral("--output-device")), -1);
    // No monitor device means no monitoring stream, not device 0.
    QCOMPARE(index_of(arguments, QStringLiteral("--monitor-device")), -1);
}

void WorkerProtocolTest::disables_output_when_requested() {
    RealtimeOptions options;
    options.input_device = 3;
    options.output_device = -1;
    options.output_disabled = true;
    options.monitor_device = 5;

    const auto arguments = build_realtime_arguments(options);

    // "不输出" is passed as device -1 so the worker captures but renders
    // nothing to an output device.
    QCOMPARE(
        value_of(arguments, QStringLiteral("--output-device")),
        QStringLiteral("-1")
    );
    QCOMPARE(
        value_of(arguments, QStringLiteral("--monitor-device")),
        QStringLiteral("5")
    );
}

void WorkerProtocolTest::includes_latency_controls() {
    RealtimeOptions options;
    options.input_device = 1;
    options.output_device = 4;
    options.prefill_chunks = 1;
    options.max_backlog_chunks = 4;
    options.input_gain_db = -2.0;
    options.output_gain_db = 3.0;
    options.monitor_gain_db = -4.0;

    const auto arguments = build_realtime_arguments(options);

    QCOMPARE(
        value_of(arguments, QStringLiteral("--input-device")),
        QStringLiteral("1")
    );
    QCOMPARE(
        value_of(arguments, QStringLiteral("--output-device")),
        QStringLiteral("4")
    );
    QCOMPARE(
        value_of(arguments, QStringLiteral("--prefill-chunks")),
        QStringLiteral("1")
    );
    QCOMPARE(
        value_of(arguments, QStringLiteral("--max-backlog-chunks")),
        QStringLiteral("4")
    );
    QCOMPARE(
        value_of(arguments, QStringLiteral("--output-gain-db")),
        QStringLiteral("3.0")
    );
    QCOMPARE(
        value_of(arguments, QStringLiteral("--input-gain-db")),
        QStringLiteral("-2.0")
    );
    QCOMPARE(
        value_of(arguments, QStringLiteral("--monitor-gain-db")),
        QStringLiteral("-4.0")
    );
}

void WorkerProtocolTest::includes_the_monitor_device() {
    RealtimeOptions options;
    options.output_device = 4;
    options.monitor_device = 9;

    const auto arguments = build_realtime_arguments(options);

    QCOMPARE(
        value_of(arguments, QStringLiteral("--output-device")),
        QStringLiteral("4")
    );
    QCOMPARE(
        value_of(arguments, QStringLiteral("--monitor-device")),
        QStringLiteral("9")
    );
}

void WorkerProtocolTest::recognises_metrics_lines() {
    QVERIFY(is_metrics_line(QStringLiteral(
        "[panda.metrics] {\"chunk\":24,\"processing_ms\":120.276}"
    )));
    // The exact payload does not matter; the prefix does.
    QVERIFY(is_metrics_line(QStringLiteral("[panda.metrics] {}")));
}

void WorkerProtocolTest::keeps_ordinary_output_out_of_the_metrics_bucket() {
    QVERIFY(!is_metrics_line(QStringLiteral("[Init] Loading VC model...")));
    QVERIFY(!is_metrics_line(QStringLiteral("error: 没有找到官方 MeanVC2 runtime")));
    QVERIFY(!is_metrics_line(QString()));
    // A near miss must not be mistaken for the metrics channel.
    QVERIFY(!is_metrics_line(QStringLiteral("[panda.metric] {}")));
}

void WorkerProtocolTest::accepts_reasonable_latency_settings() {
    const auto settings = clamp_latency(2, 6);

    QCOMPARE(settings.prefill_chunks, 2);
    QCOMPARE(settings.max_backlog_chunks, 6);
}

void WorkerProtocolTest::clamps_out_of_range_latency_settings() {
    const auto negative = clamp_latency(-5, 100);
    QCOMPARE(negative.prefill_chunks, 0);
    QCOMPARE(negative.max_backlog_chunks, 32);

    const auto huge = clamp_latency(999, 6);
    QCOMPARE(huge.prefill_chunks, 8);
    // The backlog has to stay above the clamped pre-roll.
    QCOMPARE(huge.max_backlog_chunks, 9);
}

void WorkerProtocolTest::keeps_the_backlog_above_the_prefill() {
    const auto tight = clamp_latency(2, 2);
    QCOMPARE(tight.prefill_chunks, 2);
    QCOMPARE(tight.max_backlog_chunks, 3);

    const auto zero = clamp_latency(0, 0);
    QCOMPARE(zero.prefill_chunks, 0);
    QCOMPARE(zero.max_backlog_chunks, 2);
}

void WorkerProtocolTest::includes_the_noise_gate_only_when_enabled() {
    const auto off = build_realtime_arguments(RealtimeOptions{});
    QCOMPARE(index_of(off, QStringLiteral("--noise-gate-db")), -1);

    RealtimeOptions options;
    options.noise_gate_enabled = true;
    options.noise_gate_db = -45.0;
    const auto on = build_realtime_arguments(options);

    QCOMPARE(
        value_of(on, QStringLiteral("--noise-gate-db")),
        QStringLiteral("-45.0")
    );
    // The limiter is on by default, so it is always reported.
    QCOMPARE(
        value_of(on, QStringLiteral("--limiter-ceiling")),
        QStringLiteral("0.891")
    );
}

void WorkerProtocolTest::clamps_the_gate_threshold() {
    QCOMPARE(clamp_gate_db(-200.0), -90.0);
    QCOMPARE(clamp_gate_db(0.0), -10.0);
    QCOMPARE(clamp_gate_db(-45.0), -45.0);
}

void WorkerProtocolTest::clamps_the_output_gain() {
    QCOMPARE(clamp_output_gain_db(-100.0), -24.0);
    QCOMPARE(clamp_output_gain_db(100.0), 12.0);
    QCOMPARE(clamp_output_gain_db(3.0), 3.0);
}

void WorkerProtocolTest::clamps_the_input_gain() {
    QCOMPARE(clamp_input_gain_db(-100.0), -24.0);
    QCOMPARE(clamp_input_gain_db(100.0), 12.0);
    QCOMPARE(clamp_input_gain_db(-2.0), -2.0);
}

void WorkerProtocolTest::clamps_the_monitor_gain() {
    QCOMPARE(clamp_monitor_gain_db(-100.0), -24.0);
    QCOMPARE(clamp_monitor_gain_db(100.0), 12.0);
    QCOMPARE(clamp_monitor_gain_db(-4.0), -4.0);
}

void WorkerProtocolTest::decides_when_to_restart_a_crashed_worker() {
    QVERIFY(should_restart_realtime(false, 1, true, 0));
    QVERIFY(should_restart_realtime(false, 2, false, 1));
    QVERIFY(!should_restart_realtime(true, 1, true, 0));
    QVERIFY(!should_restart_realtime(false, 0, false, 0));
    QVERIFY(!should_restart_realtime(false, 1, true, 3));
}

void WorkerProtocolTest::builds_the_preview_invocation() {
    const auto arguments = build_preview_arguments(
        QStringLiteral("D:/voices/manbo"),
        7
    );

    QCOMPARE(arguments.at(0), QStringLiteral("-m"));
    QCOMPARE(arguments.at(1), QStringLiteral("panda_cli"));
    QCOMPARE(arguments.at(2), QStringLiteral("preview"));
    QCOMPARE(
        value_of(arguments, QStringLiteral("--voice-pack")),
        QStringLiteral("D:/voices/manbo")
    );
    QCOMPARE(
        value_of(arguments, QStringLiteral("--output-device")),
        QStringLiteral("7")
    );
}

void WorkerProtocolTest::builds_the_microphone_test_invocation() {
    const auto arguments = build_mic_test_arguments(3, 8);

    QCOMPARE(arguments.at(0), QStringLiteral("-m"));
    QCOMPARE(arguments.at(1), QStringLiteral("panda_cli"));
    QCOMPARE(arguments.at(2), QStringLiteral("mic-test"));
    QCOMPARE(
        value_of(arguments, QStringLiteral("--input-device")),
        QStringLiteral("3")
    );
    QCOMPARE(
        value_of(arguments, QStringLiteral("--output-device")),
        QStringLiteral("8")
    );
}

void WorkerProtocolTest::builds_the_route_check_invocation() {
    const auto arguments = build_route_check_arguments();

    QCOMPARE(arguments.at(0), QStringLiteral("-m"));
    QCOMPARE(arguments.at(1), QStringLiteral("panda_cli"));
    QCOMPARE(arguments.at(2), QStringLiteral("route-check"));
    QVERIFY(arguments.contains(QStringLiteral("--json")));
}

void WorkerProtocolTest::includes_denoise_only_when_enabled() {
    const auto off = build_realtime_arguments(RealtimeOptions{});
    QCOMPARE(index_of(off, QStringLiteral("--denoise")), -1);

    RealtimeOptions options;
    options.denoise = true;
    const auto on = build_realtime_arguments(options);

    QVERIFY(index_of(on, QStringLiteral("--denoise")) >= 0);
    QCOMPARE(
        value_of(on, QStringLiteral("--denoise-level")),
        QStringLiteral("strong")
    );

    options.denoise_level = QStringLiteral("gentle");
    const auto gentle = build_realtime_arguments(options);
    QCOMPARE(
        value_of(gentle, QStringLiteral("--denoise-level")),
        QStringLiteral("gentle")
    );
}

void WorkerProtocolTest::clamps_the_denoise_level() {
    QCOMPARE(
        clamp_denoise_level(QStringLiteral("balanced")),
        QStringLiteral("balanced")
    );
    QCOMPARE(
        clamp_denoise_level(QStringLiteral("unknown")),
        QStringLiteral("strong")
    );
}

QTEST_GUILESS_MAIN(WorkerProtocolTest)

#include "worker_protocol_test.moc"
