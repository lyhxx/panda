// Headless tests for the persisted session settings.

#include "session_store.hpp"

#include <QDir>
#include <QStringList>
#include <QTemporaryDir>
#include <QTest>
#include <QVariantMap>

using panda::desktop::SessionStore;

namespace {

QString settings_file(const QTemporaryDir& dir) {
    return QDir(dir.path()).filePath(QStringLiteral("session.ini"));
}

}  // namespace

class SessionStoreTest : public QObject {
    Q_OBJECT

private slots:
    void defaults_when_nothing_was_saved();
    void round_trips_values();
    void rejects_unknown_model_and_compute();
    void clamps_latency_and_device_ids();
    void clear_removes_everything();
};

void SessionStoreTest::defaults_when_nothing_was_saved() {
    QTemporaryDir dir;
    QVERIFY(dir.isValid());
    const SessionStore store(settings_file(dir));

    const auto values = store.load();

    QVERIFY(values.value(QStringLiteral("voicePack")).toString().isEmpty());
    QCOMPARE(values.value(QStringLiteral("model")).toString(), QStringLiteral("120ms"));
    QCOMPARE(values.value(QStringLiteral("compute")).toString(), QStringLiteral("cpu"));
    QCOMPARE(values.value(QStringLiteral("inputDevice")).toInt(), -1);
    QVERIFY(values.value(QStringLiteral("inputDeviceKey")).toString().isEmpty());
    QCOMPARE(values.value(QStringLiteral("outputDevice")).toInt(), -1);
    QVERIFY(values.value(QStringLiteral("outputDeviceKey")).toString().isEmpty());
    QCOMPARE(values.value(QStringLiteral("monitorDevice")).toInt(), -1);
    QVERIFY(values.value(QStringLiteral("monitorDeviceKey")).toString().isEmpty());
    QCOMPARE(values.value(QStringLiteral("prefillChunks")).toInt(), 1);
    QCOMPARE(values.value(QStringLiteral("maxBacklogChunks")).toInt(), 6);
    QVERIFY(!values.value(QStringLiteral("noiseGateEnabled")).toBool());
    QCOMPARE(values.value(QStringLiteral("noiseGateDb")).toDouble(), -45.0);
    QCOMPARE(values.value(QStringLiteral("outputGainDb")).toDouble(), 0.0);
    QCOMPARE(values.value(QStringLiteral("inputGainDb")).toDouble(), 0.0);
    QCOMPARE(values.value(QStringLiteral("monitorGainDb")).toDouble(), 0.0);
    QVERIFY(!values.value(QStringLiteral("denoise")).toBool());
    QCOMPARE(
        values.value(QStringLiteral("denoiseLevel")).toString(),
        QStringLiteral("strong")
    );
    QVERIFY(values.value(QStringLiteral("favoritePacks")).toStringList().isEmpty());
    QCOMPARE(
        values.value(QStringLiteral("sortMode")).toString(),
        QStringLiteral("favorites")
    );
}

void SessionStoreTest::round_trips_values() {
    QTemporaryDir dir;
    QVERIFY(dir.isValid());
    const SessionStore store(settings_file(dir));

    const QVariantMap input{
        {QStringLiteral("voicePack"), QStringLiteral("D:/voices/manbo")},
        {QStringLiteral("model"), QStringLiteral("120ms")},
        {QStringLiteral("compute"), QStringLiteral("cuda")},
        {QStringLiteral("inputDevice"), 1},
        {QStringLiteral("inputDeviceKey"), QStringLiteral("WASAPI|Mic")},
        {QStringLiteral("outputDevice"), 4},
        {QStringLiteral("outputDeviceKey"), QStringLiteral("WASAPI|Speakers")},
        {QStringLiteral("monitorDevice"), 10},
        {QStringLiteral("monitorDeviceKey"), QStringLiteral("WASAPI|Headphones")},
        {QStringLiteral("prefillChunks"), 1},
        {QStringLiteral("maxBacklogChunks"), 4},
        {QStringLiteral("noiseGateEnabled"), true},
        {QStringLiteral("noiseGateDb"), -52.0},
        {QStringLiteral("outputGainDb"), 3.0},
        {QStringLiteral("inputGainDb"), -2.0},
        {QStringLiteral("monitorGainDb"), -4.0},
        {QStringLiteral("denoise"), true},
        {QStringLiteral("denoiseLevel"), QStringLiteral("gentle")},
        {
            QStringLiteral("favoritePacks"),
            QStringList{QStringLiteral("manbo"), QStringLiteral("nai-long")},
        },
        {QStringLiteral("sortMode"), QStringLiteral("name")},
    };
    store.save(input);

    const auto values = store.load();

    QCOMPARE(
        values.value(QStringLiteral("voicePack")).toString(),
        QStringLiteral("D:/voices/manbo")
    );
    QCOMPARE(values.value(QStringLiteral("model")).toString(), QStringLiteral("120ms"));
    QCOMPARE(values.value(QStringLiteral("compute")).toString(), QStringLiteral("cuda"));
    QCOMPARE(values.value(QStringLiteral("inputDevice")).toInt(), 1);
    QCOMPARE(
        values.value(QStringLiteral("inputDeviceKey")).toString(),
        QStringLiteral("WASAPI|Mic")
    );
    QCOMPARE(values.value(QStringLiteral("outputDevice")).toInt(), 4);
    QCOMPARE(
        values.value(QStringLiteral("outputDeviceKey")).toString(),
        QStringLiteral("WASAPI|Speakers")
    );
    QCOMPARE(values.value(QStringLiteral("monitorDevice")).toInt(), 10);
    QCOMPARE(
        values.value(QStringLiteral("monitorDeviceKey")).toString(),
        QStringLiteral("WASAPI|Headphones")
    );
    QCOMPARE(values.value(QStringLiteral("prefillChunks")).toInt(), 1);
    QCOMPARE(values.value(QStringLiteral("maxBacklogChunks")).toInt(), 4);
    QVERIFY(values.value(QStringLiteral("noiseGateEnabled")).toBool());
    QCOMPARE(values.value(QStringLiteral("noiseGateDb")).toDouble(), -52.0);
    QCOMPARE(values.value(QStringLiteral("outputGainDb")).toDouble(), 3.0);
    QCOMPARE(values.value(QStringLiteral("inputGainDb")).toDouble(), -2.0);
    QCOMPARE(values.value(QStringLiteral("monitorGainDb")).toDouble(), -4.0);
    QVERIFY(values.value(QStringLiteral("denoise")).toBool());
    QCOMPARE(
        values.value(QStringLiteral("denoiseLevel")).toString(),
        QStringLiteral("gentle")
    );
    QCOMPARE(
        values.value(QStringLiteral("favoritePacks")).toStringList(),
        QStringList({QStringLiteral("manbo"), QStringLiteral("nai-long")})
    );
    QCOMPARE(
        values.value(QStringLiteral("sortMode")).toString(),
        QStringLiteral("name")
    );
}

void SessionStoreTest::rejects_unknown_model_and_compute() {
    QTemporaryDir dir;
    QVERIFY(dir.isValid());
    const SessionStore store(settings_file(dir));

    store.save(
        QVariantMap{
            {QStringLiteral("model"), QStringLiteral("banana")},
            {QStringLiteral("compute"), QStringLiteral("quantum")},
        }
    );

    const auto values = store.load();

    QCOMPARE(values.value(QStringLiteral("model")).toString(), QStringLiteral("120ms"));
    QCOMPARE(values.value(QStringLiteral("compute")).toString(), QStringLiteral("cpu"));
}

void SessionStoreTest::clamps_latency_and_device_ids() {
    QTemporaryDir dir;
    QVERIFY(dir.isValid());
    const SessionStore store(settings_file(dir));

    store.save(
        QVariantMap{
            {QStringLiteral("inputDevice"), -5},
            {QStringLiteral("monitorDevice"), 3},
            {QStringLiteral("prefillChunks"), 99},
            {QStringLiteral("maxBacklogChunks"), 1},
            {QStringLiteral("noiseGateDb"), 40.0},
            {QStringLiteral("outputGainDb"), 100.0},
            {QStringLiteral("inputGainDb"), -100.0},
            {QStringLiteral("monitorGainDb"), 100.0},
            {QStringLiteral("denoiseLevel"), QStringLiteral("unknown")},
            {QStringLiteral("sortMode"), QStringLiteral("unsupported")},
        }
    );

    const auto values = store.load();

    QCOMPARE(values.value(QStringLiteral("inputDevice")).toInt(), -1);
    QCOMPARE(values.value(QStringLiteral("monitorDevice")).toInt(), 3);
    QCOMPARE(values.value(QStringLiteral("prefillChunks")).toInt(), 8);
    // The backlog has to stay above the clamped pre-roll.
    QCOMPARE(values.value(QStringLiteral("maxBacklogChunks")).toInt(), 9);
    // A gate threshold above -10 dB would gate normal speech.
    QCOMPARE(values.value(QStringLiteral("noiseGateDb")).toDouble(), -10.0);
    QCOMPARE(values.value(QStringLiteral("outputGainDb")).toDouble(), 12.0);
    QCOMPARE(values.value(QStringLiteral("inputGainDb")).toDouble(), -24.0);
    QCOMPARE(values.value(QStringLiteral("monitorGainDb")).toDouble(), 12.0);
    QCOMPARE(
        values.value(QStringLiteral("denoiseLevel")).toString(),
        QStringLiteral("strong")
    );
    QCOMPARE(
        values.value(QStringLiteral("sortMode")).toString(),
        QStringLiteral("favorites")
    );
}

void SessionStoreTest::clear_removes_everything() {
    QTemporaryDir dir;
    QVERIFY(dir.isValid());
    const SessionStore store(settings_file(dir));
    store.save(
        QVariantMap{
            {QStringLiteral("voicePack"), QStringLiteral("D:/voices/manbo")},
            {QStringLiteral("model"), QStringLiteral("120ms")},
        }
    );

    store.clear();

    const auto values = store.load();
    QVERIFY(values.value(QStringLiteral("voicePack")).toString().isEmpty());
    QCOMPARE(values.value(QStringLiteral("model")).toString(), QStringLiteral("120ms"));
}

QTEST_GUILESS_MAIN(SessionStoreTest)

#include "session_store_test.moc"
