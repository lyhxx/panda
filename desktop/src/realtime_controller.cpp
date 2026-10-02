#include "realtime_controller.hpp"

#include "device_list.hpp"
#include "worker_protocol.hpp"

#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QTimer>

RealtimeController::RealtimeController(QObject* parent)
    : QObject(parent) {
    process_.setProcessChannelMode(QProcess::MergedChannels);
    process_.setProgram(qEnvironmentVariable("PANDA_PYTHON", "python"));
    preview_process_.setProcessChannelMode(QProcess::MergedChannels);
    preview_process_.setProgram(qEnvironmentVariable("PANDA_PYTHON", "python"));
    route_process_.setProcessChannelMode(QProcess::SeparateChannels);
    route_process_.setProgram(qEnvironmentVariable("PANDA_PYTHON", "python"));
    device_process_.setProcessChannelMode(QProcess::SeparateChannels);
    device_process_.setProgram(qEnvironmentVariable("PANDA_PYTHON", "python"));
    restart_timer_.setSingleShot(true);
    stability_timer_.setSingleShot(true);
    stability_timer_.setInterval(10000);

    connect(
        &process_,
        &QProcess::readyReadStandardOutput,
        this,
        [this] { append_log(QString::fromUtf8(process_.readAllStandardOutput())); }
    );
    connect(
        &process_,
        &QProcess::started,
        this,
        [this] {
            stability_timer_.start();
            ready_ = false;
            emit readyChanged();
            set_status(QStringLiteral("正在加载模型…"));
            emit runningChanged();
        }
    );
    connect(
        &process_,
        qOverload<int, QProcess::ExitStatus>(&QProcess::finished),
        this,
        [this](int code, QProcess::ExitStatus status) {
            // A trailing line without a newline (for example a final error)
            // would otherwise stay stuck in the partial-line buffer.
            flush_log_buffer();
            if (pending_restart_) {
                pending_restart_ = false;
                if (ready_) {
                    ready_ = false;
                    emit readyChanged();
                }
                startRealtime(
                    last_voice_pack_,
                    last_model_,
                    last_device_,
                    pending_input_device_,
                    pending_output_device_
                );
                emit runningChanged();
                return;
            }
            if (ready_) {
                ready_ = false;
                emit readyChanged();
            }
            const auto clean_exit =
                status == QProcess::NormalExit && code == 0;
            if (stop_requested_ || clean_exit) {
                set_status(
                    clean_exit
                        ? QStringLiteral("实时变声已停止")
                        : QStringLiteral("实时变声已停止")
                );
            }
            else if (panda::desktop::should_restart_realtime(
                         stop_requested_,
                         code,
                         status != QProcess::NormalExit,
                         reconnect_attempts_
                     )) {
                schedule_reconnect();
            }
            else {
                set_status(
                    QStringLiteral(
                        "实时变声多次异常退出，已停止自动重连（退出码 %1）"
                    ).arg(code)
                );
            }
            emit runningChanged();
        }
    );
    connect(
        &process_,
        &QProcess::errorOccurred,
        this,
        [this](QProcess::ProcessError) {
            if (!stop_requested_ && process_.state() == QProcess::NotRunning) {
                schedule_reconnect();
            }
            else {
                set_status(
                    QStringLiteral("实时变声启动失败：%1").arg(
                        process_.errorString()
                    )
                );
            }
            emit runningChanged();
        }
    );

    connect(
        &restart_timer_,
        &QTimer::timeout,
        this,
        [this] {
            if (stop_requested_ || process_.state() != QProcess::NotRunning) {
                return;
            }
            process_.setArguments(last_realtime_arguments_);
            process_.start();
        }
    );
    connect(
        &stability_timer_,
        &QTimer::timeout,
        this,
        [this] {
            if (running() && reconnect_attempts_ != 0) {
                reconnect_attempts_ = 0;
                emit reconnectChanged();
            }
        }
    );
    connect(
        &preview_process_,
        qOverload<int, QProcess::ExitStatus>(&QProcess::finished),
        this,
        [this](int code, QProcess::ExitStatus status) {
            const bool was_mic_test = mic_testing_;
            previewing_ = false;
            mic_testing_ = false;
            emit previewChanged();
            emit micTestingChanged();
            const bool ok =
                status == QProcess::NormalExit && code == 0;
            if (was_mic_test) {
                set_status(
                    ok
                        ? QStringLiteral("麦克风测试完成")
                        : QStringLiteral("麦克风测试失败，退出码 %1").arg(code)
                );
            }
            else {
                set_status(
                    ok
                        ? QStringLiteral("试听完成")
                        : QStringLiteral("试听失败，退出码 %1").arg(code)
                );
            }
        }
    );
    connect(
        &route_process_,
        qOverload<int, QProcess::ExitStatus>(&QProcess::finished),
        this,
        [this](int code, QProcess::ExitStatus status) {
            checking_route_ = false;
            if (status != QProcess::NormalExit || code != 0) {
                route_report_ = QStringLiteral(
                    "没有检测到可写入的虚拟声卡。请安装 VB-CABLE 或 VoiceMeeter，"
                    "然后重新检查。"
                );
            }
            else {
                const auto document = QJsonDocument::fromJson(
                    route_process_.readAllStandardOutput()
                );
                const auto routes = document.object()
                                        .value(QStringLiteral("routes"))
                                        .toArray();
                QStringList lines;
                for (const auto& value : routes) {
                    const auto route = value.toObject();
                    lines.append(
                        QStringLiteral("Panda 输出：%1\n其它软件麦克风：%2")
                            .arg(route.value(QStringLiteral("render")).toString())
                            .arg(route.value(QStringLiteral("capture")).toString())
                    );
                }
                route_report_ = lines.isEmpty()
                    ? QStringLiteral("没有检测到可用路由。")
                    : lines.join(QStringLiteral("\n\n"));
            }
            emit routeReportChanged();
        }
    );
    connect(
        &route_process_,
        &QProcess::errorOccurred,
        this,
        [this](QProcess::ProcessError) {
            checking_route_ = false;
            route_report_ = QStringLiteral("路由检查启动失败：%1").arg(
                route_process_.errorString()
            );
            emit routeReportChanged();
        }
    );
    connect(
        &preview_process_,
        &QProcess::errorOccurred,
        this,
        [this](QProcess::ProcessError) {
            previewing_ = false;
            mic_testing_ = false;
            emit previewChanged();
            emit micTestingChanged();
            set_status(
                QStringLiteral("试听启动失败：%1").arg(
                    preview_process_.errorString()
                )
            );
        }
    );

    connect(
        &device_process_,
        qOverload<int, QProcess::ExitStatus>(&QProcess::finished),
        this,
        [this](int code, QProcess::ExitStatus status) {
            if (status != QProcess::NormalExit || code != 0) {
                const auto detail = QString::fromUtf8(
                    device_process_.readAllStandardError()
                ).trimmed();
                set_device_error(
                    detail.isEmpty()
                        ? QStringLiteral("设备枚举失败，退出码 %1").arg(code)
                        : QStringLiteral("设备枚举失败：%1").arg(detail)
                );
                return;
            }
            parse_devices(device_process_.readAllStandardOutput());
        }
    );
    connect(
        &device_process_,
        &QProcess::errorOccurred,
        this,
        [this](QProcess::ProcessError) {
            set_device_error(
                QStringLiteral("设备枚举启动失败：%1").arg(
                    device_process_.errorString()
                )
            );
        }
    );

    level_process_.setProgram(qEnvironmentVariable("PANDA_PYTHON", "python"));
    level_process_.setProcessChannelMode(QProcess::SeparateChannels);
    connect(
        &level_process_,
        &QProcess::readyReadStandardOutput,
        this,
        [this] { consume_level_buffer(level_process_.readAllStandardOutput()); }
    );
    connect(
        &level_process_,
        &QProcess::finished,
        this,
        [this](int, QProcess::ExitStatus) {
            level_input_device_ = -1;
            if (mic_monitoring_) {
                mic_monitoring_ = false;
                emit micMonitoringChanged();
            }
        }
    );
    connect(
        &level_process_,
        &QProcess::errorOccurred,
        this,
        [this](QProcess::ProcessError) {
            if (mic_monitoring_) {
                mic_monitoring_ = false;
                emit micMonitoringChanged();
            }
        }
    );
}

bool RealtimeController::running() const {
    return process_.state() != QProcess::NotRunning;
}

bool RealtimeController::ready() const {
    return ready_;
}

QString RealtimeController::status() const {
    return status_;
}

QString RealtimeController::logText() const {
    return log_text_;
}

QVariantList RealtimeController::inputDevices() const {
    return input_devices_;
}

QVariantList RealtimeController::outputDevices() const {
    return output_devices_;
}

int RealtimeController::defaultInputDevice() const {
    return default_input_device_;
}

int RealtimeController::defaultOutputDevice() const {
    return default_output_device_;
}

QString RealtimeController::deviceError() const {
    return device_error_;
}

bool RealtimeController::hasStats() const {
    return has_stats_;
}

double RealtimeController::processingMs() const {
    return stats_.processing_ms;
}

double RealtimeController::chunkMs() const {
    return stats_.chunk_ms;
}

double RealtimeController::bufferMs() const {
    return stats_.buffer_ms;
}

double RealtimeController::realtimeFactor() const {
    return stats_.realtime_factor();
}

double RealtimeController::inputRms() const {
    return stats_.input_rms;
}

double RealtimeController::inputPeak() const {
    return stats_.input_peak;
}

double RealtimeController::outputRms() const {
    return stats_.output_rms;
}

double RealtimeController::outputPeak() const {
    return stats_.output_peak;
}

bool RealtimeController::inputClipped() const {
    return stats_.input_clipped;
}

bool RealtimeController::outputClipped() const {
    return stats_.output_clipped;
}

bool RealtimeController::overrun() const {
    return stats_.overrun;
}

qulonglong RealtimeController::starvedReads() const {
    return stats_.starved_reads;
}

qulonglong RealtimeController::underrunFrames() const {
    return stats_.underrun_frames;
}

qulonglong RealtimeController::droppedFrames() const {
    return stats_.dropped_frames;
}

qulonglong RealtimeController::trimmedFrames() const {
    return stats_.trimmed_frames;
}

int RealtimeController::prefillChunks() const {
    return prefill_chunks_;
}

void RealtimeController::setPrefillChunks(int value) {
    const auto settings = panda::desktop::clamp_latency(
        value,
        max_backlog_chunks_
    );
    if (settings.prefill_chunks == prefill_chunks_ &&
        settings.max_backlog_chunks == max_backlog_chunks_) {
        return;
    }
    prefill_chunks_ = settings.prefill_chunks;
    max_backlog_chunks_ = settings.max_backlog_chunks;
    emit settingsChanged();
    push_live_controls();
}

int RealtimeController::maxBacklogChunks() const {
    return max_backlog_chunks_;
}

void RealtimeController::setMaxBacklogChunks(int value) {
    const auto settings = panda::desktop::clamp_latency(
        prefill_chunks_,
        value
    );
    if (settings.prefill_chunks == prefill_chunks_ &&
        settings.max_backlog_chunks == max_backlog_chunks_) {
        return;
    }
    prefill_chunks_ = settings.prefill_chunks;
    max_backlog_chunks_ = settings.max_backlog_chunks;
    emit settingsChanged();
    push_live_controls();
}

int RealtimeController::monitorDevice() const {
    return monitor_device_;
}

void RealtimeController::setMonitorDevice(int value) {
    if (monitor_device_ == value) {
        return;
    }
    monitor_device_ = value;
    emit settingsChanged();
    push_live_controls();
}

bool RealtimeController::noiseGateEnabled() const {
    return noise_gate_enabled_;
}

void RealtimeController::setNoiseGateEnabled(bool value) {
    if (noise_gate_enabled_ == value) {
        return;
    }
    noise_gate_enabled_ = value;
    emit settingsChanged();
    push_live_controls();
}

double RealtimeController::noiseGateDb() const {
    return noise_gate_db_;
}

void RealtimeController::setNoiseGateDb(double value) {
    const auto clamped = panda::desktop::clamp_gate_db(value);
    if (qFuzzyCompare(noise_gate_db_, clamped)) {
        return;
    }
    noise_gate_db_ = clamped;
    emit settingsChanged();
    push_live_controls();
}

double RealtimeController::inputGainDb() const {
    return input_gain_db_;
}

void RealtimeController::setInputGainDb(double value) {
    const auto clamped = panda::desktop::clamp_input_gain_db(value);
    if (qFuzzyCompare(input_gain_db_, clamped)) {
        return;
    }
    input_gain_db_ = clamped;
    emit settingsChanged();
    push_live_controls();
}

double RealtimeController::outputGainDb() const {
    return output_gain_db_;
}

void RealtimeController::setOutputGainDb(double value) {
    const auto clamped = panda::desktop::clamp_output_gain_db(value);
    if (qFuzzyCompare(output_gain_db_, clamped)) {
        return;
    }
    output_gain_db_ = clamped;
    emit settingsChanged();
    push_live_controls();
}

double RealtimeController::monitorGainDb() const {
    return monitor_gain_db_;
}

void RealtimeController::setMonitorGainDb(double value) {
    const auto clamped = panda::desktop::clamp_monitor_gain_db(value);
    if (qFuzzyCompare(monitor_gain_db_, clamped)) {
        return;
    }
    monitor_gain_db_ = clamped;
    emit settingsChanged();
    push_live_controls();
}

bool RealtimeController::denoise() const {
    return denoise_;
}

void RealtimeController::setDenoise(bool value) {
    if (denoise_ == value) {
        return;
    }
    denoise_ = value;
    emit settingsChanged();
    push_live_controls();
}

QString RealtimeController::denoiseLevel() const {
    return denoise_level_;
}

void RealtimeController::setDenoiseLevel(const QString& value) {
    const auto clamped = panda::desktop::clamp_denoise_level(value);
    if (denoise_level_ == clamped) {
        return;
    }
    denoise_level_ = clamped;
    emit settingsChanged();
    push_live_controls();
}

int RealtimeController::reconnectAttempts() const {
    return reconnect_attempts_;
}

bool RealtimeController::previewing() const {
    return previewing_;
}

bool RealtimeController::micTesting() const {
    return mic_testing_;
}

bool RealtimeController::micMonitoring() const {
    return mic_monitoring_;
}

QString RealtimeController::routeReport() const {
    return route_report_;
}

bool RealtimeController::checkingRoute() const {
    return checking_route_;
}

void RealtimeController::refreshDevices() {
    if (device_process_.state() != QProcess::NotRunning) {
        return;
    }

    set_device_error(QString());
    device_process_.setArguments(
        QStringList{
            QStringLiteral("-m"),
            QStringLiteral("panda_cli"),
            QStringLiteral("devices"),
            QStringLiteral("--json"),
        }
    );
    device_process_.start();
}

void RealtimeController::startRealtime(
    const QString& voicePack,
    const QString& model,
    const QString& device,
    int inputDevice,
    int outputDevice
) {
    if (running()) {
        set_status(QStringLiteral("实时变声已经在运行"));
        return;
    }

    const auto meanvc2_root = qEnvironmentVariable("PANDA_MEANVC2_ROOT");
    if (meanvc2_root.isEmpty()) {
        set_status(QStringLiteral("未配置 PANDA_MEANVC2_ROOT"));
        return;
    }
    if (voicePack.isEmpty()) {
        set_status(QStringLiteral("请先选择音色包"));
        return;
    }
    if (!QFileInfo::exists(voicePack + QStringLiteral("/manifest.json"))) {
        set_status(QStringLiteral("音色包缺少 manifest.json"));
        return;
    }
    if (outputDevice < 0 && monitor_device_ < 0) {
        set_status(QStringLiteral("已选择「不输出」，且没有开启监听，变声无处输出"));
        return;
    }

    last_voice_pack_ = voicePack;
    last_model_ = model;
    last_device_ = device;
    last_input_device_ = inputDevice;
    last_output_device_ = outputDevice;

    // The level monitor and the conversion session both open the microphone;
    // hand the device over cleanly.
    stopMicMonitor();

    log_text_.clear();
    metric_line_buffer_.clear();
    has_stats_ = false;
    emit logTextChanged();
    emit statsChanged();

    panda::desktop::RealtimeOptions options;
    options.meanvc2_root = meanvc2_root;
    options.voice_pack = voicePack;
    options.model = model;
    options.device = device;
    options.input_device = inputDevice;
    options.output_device = outputDevice;
    options.output_disabled = outputDevice < 0;
    options.prefill_chunks = prefill_chunks_;
    options.max_backlog_chunks = max_backlog_chunks_;
    options.monitor_device = monitor_device_;
    options.noise_gate_enabled = noise_gate_enabled_;
    options.noise_gate_db = noise_gate_db_;
    options.input_gain_db = input_gain_db_;
    options.output_gain_db = output_gain_db_;
    options.monitor_gain_db = monitor_gain_db_;
    options.denoise = denoise_;
    options.denoise_level = denoise_level_;

    set_status(QStringLiteral("正在启动实时变声"));
    last_realtime_arguments_ =
        panda::desktop::build_realtime_arguments(options);
    stop_requested_ = false;
    restart_timer_.stop();
    stability_timer_.stop();
    reconnect_attempts_ = 0;
    emit reconnectChanged();
    process_.setArguments(last_realtime_arguments_);
    process_.start();
}

void RealtimeController::stop() {
    if (!running()) {
        return;
    }
    stop_requested_ = true;
    restart_timer_.stop();
    stability_timer_.stop();
    set_status(QStringLiteral("正在停止实时变声"));
    process_.terminate();
    QTimer::singleShot(1500, this, [this] {
        if (running()) {
            process_.kill();
        }
    });
}

void RealtimeController::restartRealtime(int inputDevice, int outputDevice) {
    if (last_voice_pack_.isEmpty()) {
        return;
    }
    if (running()) {
        pending_restart_ = true;
        pending_input_device_ = inputDevice;
        pending_output_device_ = outputDevice;
        stop();
        return;
    }
    startRealtime(
        last_voice_pack_,
        last_model_,
        last_device_,
        inputDevice,
        outputDevice
    );
}

void RealtimeController::push_live_controls() {
    if (!running()) {
        return;
    }
    const QJsonObject payload{
        {QStringLiteral("output_gain_db"), output_gain_db_},
        {QStringLiteral("input_gain_db"), input_gain_db_},
        {QStringLiteral("monitor_gain_db"), monitor_gain_db_},
        {QStringLiteral("gate_enabled"), noise_gate_enabled_},
        {QStringLiteral("gate_db"), noise_gate_db_},
        {QStringLiteral("output_muted"), last_output_device_ < 0},
        {QStringLiteral("input_device"), last_input_device_},
        {QStringLiteral("output_device"), last_output_device_},
        {QStringLiteral("monitor_device"), monitor_device_},
        {QStringLiteral("denoise"), denoise_},
        {QStringLiteral("denoise_level"), denoise_level_},
        {QStringLiteral("prefill_chunks"), prefill_chunks_},
        {QStringLiteral("max_backlog_chunks"), max_backlog_chunks_},
    };
    const auto line =
        QJsonDocument(payload).toJson(QJsonDocument::Compact) + QByteArrayLiteral("\n");
    process_.write(line);
}

void RealtimeController::updateLiveDevices(int inputDevice, int outputDevice) {
    last_input_device_ = inputDevice;
    last_output_device_ = outputDevice;
    push_live_controls();
}

void RealtimeController::previewVoicePack(
    const QString& voicePack,
    int outputDevice
) {
    if (running() || previewing_ || mic_testing_) {
        return;
    }
    if (voicePack.isEmpty()) {
        set_status(QStringLiteral("请先选择音色包"));
        return;
    }

    previewing_ = true;
    emit previewChanged();
    set_status(QStringLiteral("正在试听音色"));
    preview_process_.setArguments(
        panda::desktop::build_preview_arguments(voicePack, outputDevice)
    );
    preview_process_.start();
}

void RealtimeController::testMicrophone(
    int inputDevice,
    int outputDevice
) {
    if (running() || previewing_ || mic_testing_) {
        return;
    }
    if (inputDevice < 0 || outputDevice < 0) {
        set_status(QStringLiteral("请先选择输入和输出设备"));
        return;
    }

    mic_testing_ = true;
    emit micTestingChanged();
    set_status(QStringLiteral("正在测试麦克风：请说话 3 秒"));
    preview_process_.setArguments(
        panda::desktop::build_mic_test_arguments(
            inputDevice,
            outputDevice
        )
    );
    preview_process_.start();
}

void RealtimeController::checkRoute() {
    if (checking_route_ || route_process_.state() != QProcess::NotRunning) {
        return;
    }
    checking_route_ = true;
    route_report_ = QStringLiteral("正在检查虚拟声卡路由…");
    emit routeReportChanged();
    route_process_.setArguments(
        panda::desktop::build_route_check_arguments()
    );
    route_process_.start();
}

void RealtimeController::startMicMonitor(int inputDevice) {
    if (inputDevice < 0 || running()) {
        stopMicMonitor();
        return;
    }

    if (level_process_.state() != QProcess::NotRunning) {
        if (level_input_device_ == inputDevice) {
            return;
        }
        level_process_.kill();
        level_process_.waitForFinished(500);
    }

    level_input_device_ = inputDevice;
    level_process_.setArguments(QStringList{
        QStringLiteral("-m"),
        QStringLiteral("panda_cli"),
        QStringLiteral("mic-level"),
        QStringLiteral("--input-device"),
        QString::number(inputDevice),
    });
    level_process_.start();
}

void RealtimeController::stopMicMonitor() {
    if (level_process_.state() != QProcess::NotRunning) {
        level_process_.kill();
        level_process_.waitForFinished(500);
    }
    level_input_device_ = -1;

    if (mic_monitoring_) {
        mic_monitoring_ = false;
        emit micMonitoringChanged();
    }

    // Only clear the meter when no conversion session owns it.
    if (!running()) {
        stats_.input_rms = 0.0;
        stats_.input_peak = 0.0;
        stats_.input_clipped = false;
        emit statsChanged();
    }
}

void RealtimeController::consume_level_buffer(const QByteArray& value) {
    level_buffer_ += QString::fromUtf8(value);

    qsizetype start = 0;
    while (true) {
        const auto end = level_buffer_.indexOf(QLatin1Char('\n'), start);
        if (end < 0) {
            break;
        }
        parse_level_line(level_buffer_.mid(start, end - start));
        start = end + 1;
    }
    level_buffer_ = level_buffer_.mid(start);
    if (level_buffer_.size() > 4096) {
        level_buffer_ = level_buffer_.right(4096);
    }
}

void RealtimeController::parse_level_line(const QString& value) {
    static const QString prefix = QStringLiteral("[panda.level]");
    const auto line = value.trimmed();
    if (!line.startsWith(prefix)) {
        return;
    }

    const auto document = QJsonDocument::fromJson(
        line.mid(prefix.size()).trimmed().toUtf8()
    );
    if (!document.isObject()) {
        return;
    }

    const auto object = document.object();
    stats_.input_rms = object.value(QStringLiteral("rms")).toDouble();
    stats_.input_peak = object.value(QStringLiteral("peak")).toDouble();
    stats_.input_clipped =
        object.value(QStringLiteral("clipped")).toBool(false);
    emit statsChanged();

    if (!mic_monitoring_) {
        mic_monitoring_ = true;
        emit micMonitoringChanged();
    }
}

void RealtimeController::schedule_reconnect() {
    if (restart_timer_.isActive()) {
        return;
    }
    if (!panda::desktop::should_restart_realtime(
            stop_requested_,
            1,
            true,
            reconnect_attempts_
        )) {
        set_status(QStringLiteral("实时变声多次异常退出，已停止自动重连"));
        return;
    }

    reconnect_attempts_ += 1;
    emit reconnectChanged();
    const auto delay_ms = 1000 * reconnect_attempts_;
    set_status(
        QStringLiteral("实时变声异常退出，%1 秒后自动重连（第 %2/%3 次）")
            .arg(delay_ms / 1000)
            .arg(reconnect_attempts_)
            .arg(3)
    );
    restart_timer_.start(delay_ms);
}

void RealtimeController::append_log(const QString& value) {
    metric_line_buffer_ += value;

    bool log_changed = false;
    qsizetype line_start = 0;
    while (true) {
        const auto line_end = metric_line_buffer_.indexOf(
            QLatin1Char('\n'),
            line_start
        );
        if (line_end < 0) {
            break;
        }
        consume_log_line(
            metric_line_buffer_.mid(line_start, line_end - line_start),
            log_changed
        );
        line_start = line_end + 1;
    }
    metric_line_buffer_ = metric_line_buffer_.mid(line_start);
    if (metric_line_buffer_.size() > 4096) {
        metric_line_buffer_ = metric_line_buffer_.right(4096);
    }

    if (log_changed) {
        trim_log();
        emit logTextChanged();
    }
}

void RealtimeController::consume_log_line(
    const QString& line,
    bool& log_changed
) {
    if (panda::desktop::is_metrics_line(line)) {
        // Metrics are surfaced as numbers; keep them out of the log pane.
        parse_metric_line(line);
        return;
    }

    if (line.trimmed() == QStringLiteral("[panda.ready]")) {
        // The worker prints this once the model and audio stream are open.
        if (!ready_) {
            ready_ = true;
            emit readyChanged();
        }
        set_status(QStringLiteral("实时变声运行中"));
        return;
    }

    log_text_ += line;
    log_text_ += QLatin1Char('\n');
    log_changed = true;
}

void RealtimeController::flush_log_buffer() {
    if (metric_line_buffer_.isEmpty()) {
        return;
    }

    bool log_changed = false;
    consume_log_line(metric_line_buffer_, log_changed);
    metric_line_buffer_.clear();
    if (log_changed) {
        trim_log();
        emit logTextChanged();
    }
}

void RealtimeController::trim_log() {
    constexpr qsizetype max_log_size = 64 * 1024;
    if (log_text_.size() > max_log_size) {
        log_text_ = log_text_.right(max_log_size);
    }
}

void RealtimeController::parse_metric_line(const QString& value) {
    const auto parsed = panda::audio::parse_realtime_stats(
        value.trimmed().toStdString()
    );
    if (!parsed) {
        return;
    }

    stats_ = *parsed;
    has_stats_ = true;
    emit statsChanged();
}

void RealtimeController::parse_devices(const QByteArray& value) {
    const auto parsed = panda::desktop::parse_device_payload(value);
    if (!parsed.ok) {
        set_device_error(parsed.error);
        return;
    }

    input_devices_ = parsed.inputs;
    output_devices_ = parsed.outputs;
    default_input_device_ = parsed.default_input;
    default_output_device_ = parsed.default_output;
    set_device_error(QString());
    emit devicesChanged();
}

void RealtimeController::set_status(const QString& value) {
    if (status_ == value) {
        return;
    }
    status_ = value;
    emit statusChanged();
}

void RealtimeController::set_device_error(const QString& value) {
    if (device_error_ == value) {
        return;
    }
    device_error_ = value;
    emit deviceErrorChanged();
}

