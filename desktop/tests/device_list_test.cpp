// Headless tests for the device payload parser behind the output-device
// picker. The virtual-device flag marks the endpoints other applications can
// hear: it labels them in the picker and keeps them from being filtered out.

#include "device_list.hpp"

#include <QByteArray>
#include <QTest>
#include <QVariantMap>

using panda::desktop::parse_device_payload;

class DeviceListTest : public QObject {
    Q_OBJECT

private slots:
    void splits_inputs_and_outputs();
    void marks_virtual_devices();
    void rejects_invalid_json();
    void reads_defaults();
};

void DeviceListTest::splits_inputs_and_outputs() {
    const auto parsed = parse_device_payload(QByteArrayLiteral(R"({
        "default": [1, 4],
        "hostapis": ["MME", "Windows WASAPI"],
        "devices": [
            {"index": 1, "name": "Mic", "hostapi": 0,
             "max_input_channels": 2, "max_output_channels": 0},
            {"index": 4, "name": "Speakers", "hostapi": 1,
             "max_input_channels": 0, "max_output_channels": 2}
        ]
    })"));

    QVERIFY(parsed.ok);
    QCOMPARE(parsed.inputs.size(), 1);
    QCOMPARE(parsed.outputs.size(), 1);
    QCOMPARE(parsed.inputs.at(0).toMap().value("id").toInt(), 1);
    QCOMPARE(parsed.outputs.at(0).toMap().value("id").toInt(), 4);
    QVERIFY(
        parsed.inputs.at(0).toMap().value("label").toString().contains("MME")
    );
    QVERIFY(
        parsed.outputs.at(0).toMap().value("label").toString().contains(
            "WASAPI"
        )
    );
    QCOMPARE(
        parsed.inputs.at(0).toMap().value("hostApi").toString(),
        QStringLiteral("MME")
    );
    QCOMPARE(
        parsed.inputs.at(0).toMap().value("deviceName").toString(),
        QStringLiteral("Mic")
    );
    QCOMPARE(
        parsed.outputs.at(0).toMap().value("hostApi").toString(),
        QStringLiteral("Windows WASAPI")
    );
}

void DeviceListTest::marks_virtual_devices() {
    const auto parsed = parse_device_payload(QByteArrayLiteral(R"({
        "default": [-1, -1],
        "hostapis": ["MME"],
        "devices": [
            {"index": 1, "name": "CABLE Input", "hostapi": 0,
             "max_output_channels": 2, "is_virtual": true},
            {"index": 2, "name": "Speakers", "hostapi": 0,
             "max_output_channels": 2, "is_virtual": false},
            {"index": 3, "name": "Legacy", "hostapi": 0,
             "max_output_channels": 2}
        ]
    })"));

    QVERIFY(parsed.ok);
    QCOMPARE(parsed.outputs.size(), 3);
    QVERIFY(parsed.outputs.at(0).toMap().value("isVirtual").toBool());
    QVERIFY(!parsed.outputs.at(1).toMap().value("isVirtual").toBool());
    // A device without the flag must not be assumed virtual.
    QVERIFY(!parsed.outputs.at(2).toMap().value("isVirtual").toBool());
    // The marker is what the user reads in the picker: a virtual endpoint has
    // to be recognisable there, since nothing warns them afterwards.
    QVERIFY(
        parsed.outputs.at(0).toMap().value("label").toString().contains(
            QStringLiteral("虚拟声卡")
        )
    );
    QVERIFY(
        !parsed.outputs.at(1).toMap().value("label").toString().contains(
            QStringLiteral("虚拟声卡")
        )
    );
}

void DeviceListTest::rejects_invalid_json() {
    const auto parsed = parse_device_payload(QByteArrayLiteral("not json"));

    QVERIFY(!parsed.ok);
    QVERIFY(!parsed.error.isEmpty());
    QVERIFY(parsed.inputs.isEmpty());
    QVERIFY(parsed.outputs.isEmpty());
    QCOMPARE(parsed.default_input, -1);
    QCOMPARE(parsed.default_output, -1);
}

void DeviceListTest::reads_defaults() {
    const auto parsed = parse_device_payload(
        QByteArrayLiteral(R"({"default": [3, 7], "hostapis": [], "devices": []})")
    );

    QVERIFY(parsed.ok);
    QCOMPARE(parsed.default_input, 3);
    QCOMPARE(parsed.default_output, 7);

    const auto missing = parse_device_payload(
        QByteArrayLiteral(R"({"devices": []})")
    );
    QVERIFY(missing.ok);
    QCOMPARE(missing.default_input, -1);
    QCOMPARE(missing.default_output, -1);
}

QTEST_GUILESS_MAIN(DeviceListTest)

#include "device_list_test.moc"
