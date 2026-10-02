import QtQuick

// Volume slider shown as 0-100 (or a dB value for thresholds). Internally it
// maps to the decibel range the engine expects, so the volume controls never
// display negative numbers.
Item {
    id: root

    property real gainDb: 0
    property real minDb: -24
    property real maxDb: 12
    property bool percentage: true
    // When true, gainDb already carries the 0..100 percentage (used for the
    // Windows system volume) instead of a dB gain.
    property bool systemVolume: false
    property string unit: " dB"
    signal gainMoved(real db)

    readonly property real percent: systemVolume
        ? Math.max(0, Math.min(100, Math.round(gainDb)))
        : Math.max(0, Math.min(100,
            Math.round((gainDb - minDb) / (maxDb - minDb) * 100)))

    implicitHeight: 54
    implicitWidth: 240

    AppSlider {
        id: slider
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        from: root.percentage ? 0 : root.minDb
        to: root.percentage ? 100 : root.maxDb
        value: root.percentage ? root.percent : root.gainDb
        onMoved: root.gainMoved(
            root.percentage
                ? (root.systemVolume
                   ? value
                   : root.minDb + value / 100 * (root.maxDb - root.minDb))
                : value
        )
    }

    Rectangle {
        id: bubble
        y: slider.height - 4
        width: bubbleText.implicitWidth + 14
        height: 18
        radius: 5
        color: Theme.glassStrong
        border.width: 1
        border.color: Theme.glassBorder
        x: Math.max(0, Math.min(root.width - width,
               slider.visualPosition * (root.width - 20) + 10 - width / 2))
        Behavior on x {
            NumberAnimation { duration: Theme.durFast }
        }

        Text {
            id: bubbleText
            anchors.centerIn: parent
            text: root.percentage
                  ? Math.round(slider.value).toString()
                  : Math.round(slider.value) + root.unit
            color: Theme.textPrimary
            font.pixelSize: Theme.fontCaption
            font.family: Theme.fontFamily
        }
    }
}
