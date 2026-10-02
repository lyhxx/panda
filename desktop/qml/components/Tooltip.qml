import QtQuick
import QtQuick.Controls

// Minimal tooltip anchored under a control, shown after a short hover delay.
Popup {
    id: root

    property Item anchorItem: null
    property string text: ""
    property int showDelay: 400
    property bool above: false

    padding: 0
    background: null
    focus: false
    modal: false
    closePolicy: Popup.NoAutoClose

    x: anchorItem ? Math.round((anchorItem.width - width) / 2) : 0
    y: anchorItem ? (above ? -height - 7 : anchorItem.height + 7) : 0

    contentItem: Rectangle {
        color: Theme.tooltip
        radius: 6
        implicitWidth: label.implicitWidth + 16
        implicitHeight: label.implicitHeight + 9

        Text {
            id: label
            anchors.centerIn: parent
            text: root.text
            color: "#F2F2F7"
            font.pixelSize: Theme.fontSmall
            font.family: Theme.fontFamily
        }
    }

    Timer {
        id: showTimer
        interval: root.showDelay
        onTriggered: {
            if (root.anchorItem && root.anchorItem.hovered && root.text.length > 0) {
                root.open()
            }
        }
    }

    Connections {
        target: root.anchorItem
        enabled: root.anchorItem !== null
        function onHoveredChanged() {
            if (root.anchorItem.hovered) {
                showTimer.restart()
            } else {
                showTimer.stop()
                root.close()
            }
        }
    }
}
