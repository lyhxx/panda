import QtQuick

// A slim horizontal level meter with green/yellow/red zones.
Item {
    id: root

    property real value: 0          // 0..1 peak
    property bool clipped: false
    property int barHeight: 8

    implicitHeight: barHeight
    implicitWidth: 140

    Rectangle {
        id: track
        anchors.fill: parent
        radius: height / 2
        color: Theme.dark ? "#26262C" : "#E4E4EA"
        border.width: 1
        border.color: Theme.separator
        clip: true

        Rectangle {
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: Math.max(0, Math.min(1, root.value)) * track.width
            radius: height / 2
            color: root.clipped
                   ? Theme.danger
                   : (root.value > 0.9 ? Theme.warning : Theme.success)
            Behavior on color {
                ColorAnimation { duration: Theme.durFast }
            }
            Behavior on width {
                NumberAnimation { duration: Theme.durFast }
            }
        }
    }
}
