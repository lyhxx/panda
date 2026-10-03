#pragma once

#include "panda/audio/realtime_stats.hpp"
#include "worker_protocol.hpp"

#include <QObject>
#include <QProcess>
#include <QString>
#include <QStringList>
#include <QTimer>
#include <QVariantList>

class QSoundEffect;

class RealtimeController final : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool running READ running NOTIFY runningChanged)
    Q_PROPERTY(bool ready READ ready NOTIFY readyChanged)
    Q_PROPERTY(int startupProgress READ startupProgress NOTIFY startupProgressChanged)
    Q_PROPERTY(QString status READ status NOTIFY statusChanged)
    Q_PROPERTY(QString logText READ logText NOTIFY logTextChanged)
    Q_PROPERTY(QVariantList inputDevices READ inputDevices NOTIFY devicesChanged)
    Q_PROPERTY(QVariantList outputDevices READ outputDevices NOTIFY devicesChanged)
    Q_PROPERTY(int defaultInputDevice READ defaultInputDevice NOTIFY devicesChanged)
    Q_PROPERTY(int defaultOutputDevice READ defaultOutputDevice NOTIFY devicesChanged)
    Q_PROPERTY(QString deviceError READ deviceError NOTIFY deviceErrorChanged)
    Q_PROPERTY(bool hasStats READ hasStats NOTIFY statsChanged)
    Q_PROPERTY(double processingMs READ processingMs NOTIFY statsChanged)
    Q_PROPERTY(double chunkMs READ chunkMs NOTIFY statsChanged)
    Q_PROPERTY(double bufferMs READ bufferMs NOTIFY statsChanged)
    // Mouth-to-ear: device capture + jitter buffer + conversion + device
    // playback. The UI used to show only the middle two terms, which is why
    // the number on screen always looked better than what the listener heard.
    Q_PROPERTY(double latencyMs READ latencyMs NOTIFY statsChanged)
    Q_PROPERTY(double inputLatencyMs READ inputLatencyMs NOTIFY statsChanged)
    Q_PROPERTY(double outputLatencyMs READ outputLatencyMs NOTIFY statsChanged)
    Q_PROPERTY(double deviceBlockMs READ deviceBlockMs NOTIFY statsChanged)
    Q_PROPERTY(double realtimeFactor READ realtimeFactor NOTIFY statsChanged)
    Q_PROPERTY(double inputRms READ inputRms NOTIFY statsChanged)
    Q_PROPERTY(double inputPeak READ inputPeak NOTIFY statsChanged)
    Q_PROPERTY(double outputRms READ outputRms NOTIFY statsChanged)
    Q_PROPERTY(double outputPeak READ outputPeak NOTIFY statsChanged)
    Q_PROPERTY(bool inputClipped READ inputClipped NOTIFY statsChanged)
    Q_PROPERTY(bool outputClipped READ outputClipped NOTIFY statsChanged)
    Q_PROPERTY(bool overrun READ overrun NOTIFY statsChanged)
    Q_PROPERTY(qulonglong starvedReads READ starvedReads NOTIFY statsChanged)
    Q_PROPERTY(qulonglong underrunFrames READ underrunFrames NOTIFY statsChanged)
    Q_PROPERTY(qulonglong droppedFrames READ droppedFrames NOTIFY statsChanged)
    Q_PROPERTY(qulonglong trimmedFrames READ trimmedFrames NOTIFY statsChanged)
    Q_PROPERTY(int prefillChunks READ prefillChunks WRITE setPrefillChunks NOTIFY settingsChanged)
    Q_PROPERTY(int maxBacklogChunks READ maxBacklogChunks WRITE setMaxBacklogChunks NOTIFY settingsChanged)
    Q_PROPERTY(int monitorDevice READ monitorDevice WRITE setMonitorDevice NOTIFY settingsChanged)
    Q_PROPERTY(bool noiseGateEnabled READ noiseGateEnabled WRITE setNoiseGateEnabled NOTIFY settingsChanged)
    Q_PROPERTY(double noiseGateDb READ noiseGateDb WRITE setNoiseGateDb NOTIFY settingsChanged)
    Q_PROPERTY(double inputGainDb READ inputGainDb WRITE setInputGainDb NOTIFY settingsChanged)
    Q_PROPERTY(double outputGainDb READ outputGainDb WRITE setOutputGainDb NOTIFY settingsChanged)
    Q_PROPERTY(double monitorGainDb READ monitorGainDb WRITE setMonitorGainDb NOTIFY settingsChanged)
    Q_PROPERTY(bool denoise READ denoise WRITE setDenoise NOTIFY settingsChanged)
    Q_PROPERTY(QString denoiseLevel READ denoiseLevel WRITE setDenoiseLevel NOTIFY settingsChanged)
    Q_PROPERTY(int reconnectAttempts READ reconnectAttempts NOTIFY reconnectChanged)
    Q_PROPERTY(bool previewing READ previewing NOTIFY previewChanged)
    Q_PROPERTY(QString previewName READ previewName NOTIFY previewNameChanged)
    Q_PROPERTY(bool micTesting READ micTesting NOTIFY micTestingChanged)
    Q_PROPERTY(bool micMonitoring READ micMonitoring NOTIFY micMonitoringChanged)
    Q_PROPERTY(QString routeReport READ routeReport NOTIFY routeReportChanged)
    Q_PROPERTY(bool checkingRoute READ checkingRoute NOTIFY routeReportChanged)

public:
    explicit RealtimeController(QObject* parent = nullptr);

    [[nodiscard]] bool running() const;
    [[nodiscard]] bool ready() const;
    [[nodiscard]] int startupProgress() const;
    [[nodiscard]] QString status() const;
    [[nodiscard]] QString logText() const;
    [[nodiscard]] QVariantList inputDevices() const;
    [[nodiscard]] QVariantList outputDevices() const;
    [[nodiscard]] int defaultInputDevice() const;
    [[nodiscard]] int defaultOutputDevice() const;
    [[nodiscard]] QString deviceError() const;
    [[nodiscard]] bool hasStats() const;
    [[nodiscard]] double processingMs() const;
    [[nodiscard]] double chunkMs() const;
    [[nodiscard]] double bufferMs() const;
    [[nodiscard]] double latencyMs() const;
    [[nodiscard]] double inputLatencyMs() const;
    [[nodiscard]] double outputLatencyMs() const;
    [[nodiscard]] double deviceBlockMs() const;
    [[nodiscard]] double realtimeFactor() const;
    [[nodiscard]] double inputRms() const;
    [[nodiscard]] double inputPeak() const;
    [[nodiscard]] double outputRms() const;
    [[nodiscard]] double outputPeak() const;
    [[nodiscard]] bool inputClipped() const;
    [[nodiscard]] bool outputClipped() const;
    [[nodiscard]] bool overrun() const;
    [[nodiscard]] qulonglong starvedReads() const;
    [[nodiscard]] qulonglong underrunFrames() const;
    [[nodiscard]] qulonglong droppedFrames() const;
    [[nodiscard]] qulonglong trimmedFrames() const;
    [[nodiscard]] int prefillChunks() const;
    void setPrefillChunks(int value);
    [[nodiscard]] int maxBacklogChunks() const;
    void setMaxBacklogChunks(int value);
    [[nodiscard]] int monitorDevice() const;
    void setMonitorDevice(int value);
    [[nodiscard]] bool noiseGateEnabled() const;
    void setNoiseGateEnabled(bool value);
    [[nodiscard]] double noiseGateDb() const;
    void setNoiseGateDb(double value);
    [[nodiscard]] double inputGainDb() const;
    void setInputGainDb(double value);
    [[nodiscard]] double outputGainDb() const;
    void setOutputGainDb(double value);
    [[nodiscard]] double monitorGainDb() const;
    void setMonitorGainDb(double value);
    [[nodiscard]] bool denoise() const;
    void setDenoise(bool value);
    [[nodiscard]] QString denoiseLevel() const;
    void setDenoiseLevel(const QString& value);
    [[nodiscard]] int reconnectAttempts() const;
    [[nodiscard]] bool previewing() const;
    [[nodiscard]] QString previewName() const;
    [[nodiscard]] bool micTesting() const;
    [[nodiscard]] bool micMonitoring() const;
    [[nodiscard]] QString routeReport() const;
    [[nodiscard]] bool checkingRoute() const;

    Q_INVOKABLE void refreshDevices();
    Q_INVOKABLE void startRealtime(
        const QString& voicePack,
        const QString& model,
        const QString& device,
        int inputDevice,
        int outputDevice
    );
    // Asks the worker to play out everything still in flight and then exits on
    // its own; only terminated as a fallback if that does not happen.
    Q_INVOKABLE void stop();
    // Immediate stop with no drain. For quitting the app, where an orphaned
    // worker still holding the microphone would be worse than a cut-off tail.
    Q_INVOKABLE void stopNow();
    // Sends the current devices so the worker can reopen only the streams.
    Q_INVOKABLE void updateLiveDevices(int inputDevice, int outputDevice);
    // Stops and starts the worker again, keeping the current voice/model.
    // Reserved for changes that genuinely need a reload.
    Q_INVOKABLE void restartRealtime(int inputDevice, int outputDevice);
    // The speaker embedding is the only voice-dependent part of a loaded
    // model, so switching pack asks the live worker to recompute it instead
    // of restarting the process (~1s instead of ~20s).
    Q_INVOKABLE void loadVoicePack(const QString& voicePack);
    Q_INVOKABLE void previewVoicePack(
        const QString& voicePack,
        int outputDevice
    );
    // Play a pack reference WAV in-process so previewing is instant instead of
    // paying Python startup (numpy/scipy imports) on every click. Pass the
    // display name so the UI can show which pack is currently playing, and so
    // clicking another pack swaps the audio instead of being ignored.
    Q_INVOKABLE void previewFile(const QString& path, const QString& displayName);
    Q_INVOKABLE void testMicrophone(int inputDevice, int outputDevice);
    Q_INVOKABLE void checkRoute();
    // Live microphone level for the settings meter, without a conversion
    // session. Safe to call repeatedly: an unchanged device is a no-op.
    Q_INVOKABLE void startMicMonitor(int inputDevice);
    Q_INVOKABLE void stopMicMonitor();

    // Windows endpoint (system mixer) volume for a device, 0..1. Returns -1
    // when the device cannot be mapped, so the UI can fall back gracefully.
    Q_INVOKABLE double deviceVolume(int deviceId, bool output) const;
    Q_INVOKABLE void setDeviceVolume(int deviceId, bool output, double scalar);

signals:
    void runningChanged();
    void readyChanged();
    void startupProgressChanged();
    void statusChanged();
    void logTextChanged();
    void devicesChanged();
    void deviceErrorChanged();
    void statsChanged();
    void settingsChanged();
    void engineConfigChanged();
    void reconnectChanged();
    void previewChanged();
    void previewNameChanged();
    void micTestingChanged();
    void micMonitoringChanged();
    void routeReportChanged();

private:
    void append_log(const QString& value);
    void consume_log_line(const QString& line, bool& log_changed);
    void flush_log_buffer();
    void trim_log();
    void parse_devices(const QByteArray& value);
    void parse_metric_line(const QString& value);
    void parse_level_line(const QString& value);
    void consume_level_buffer(const QByteArray& value);
    void push_live_controls();
    void set_status(const QString& value);
    void set_device_error(const QString& value);
    void schedule_reconnect();
    void stop_impl(bool drain);

    QProcess process_;
    QProcess preview_process_;
    QSoundEffect* preview_effect_{nullptr};
    QProcess route_process_;
    QProcess device_process_;
    QTimer restart_timer_;
    QTimer stability_timer_;
    // Fallbacks armed by stop_impl; restarting one cancels the previous stop's
    // timers, so a late fallback can never terminate a freshly started worker.
    QTimer stop_terminate_timer_;
    QTimer stop_kill_timer_;
    QString status_;
    QString log_text_;
    QVariantList input_devices_;
    QVariantList output_devices_;
    int default_input_device_{-1};
    int default_output_device_{-1};
    QString device_error_;
    QString metric_line_buffer_;
    panda::audio::RealtimeStats stats_;
    bool has_stats_{false};
    int prefill_chunks_{1};
    int max_backlog_chunks_{6};
    int monitor_device_{-1};
    bool noise_gate_enabled_{false};
    double noise_gate_db_{-45.0};
    double input_gain_db_{0.0};
    double output_gain_db_{0.0};
    double monitor_gain_db_{0.0};
    bool denoise_{false};
    QString denoise_level_{QStringLiteral("strong")};
    QStringList last_realtime_arguments_;
    panda::desktop::RealtimeOptions last_options_;
    QString last_voice_pack_;
    QString last_model_;
    QString last_device_;
    int last_input_device_{-1};
    int last_output_device_{-1};
    bool pending_restart_{false};
    int pending_input_device_{-1};
    int pending_output_device_{-1};
    bool stop_requested_{false};
    int reconnect_attempts_{0};
    bool previewing_{false};
    bool suppress_preview_finish_{false};
    QString preview_name_;
    bool mic_testing_{false};
    bool mic_monitoring_{false};
    bool ready_{false};
    int startup_progress_{0};
    QProcess level_process_;
    QString level_buffer_;
    int level_input_device_{-1};
    QString route_report_;
    bool checking_route_{false};
};

