import QtQuick

// Sidebar navigation entry with hover/selected states.
Item {
    id: root

    property string icon: ""
    property string text: ""
    property bool selected: false
    signal clicked()

    implicitHeight: 38
    implicitWidth: 200

    Rectangle {
        anchors.fill: parent
        anchors.leftMargin: 8
        anchors.rightMargin: 8
        radius: Theme.radiusSmall
        color: root.selected
               ? Theme.selectedOverlay
               : (mouseArea.containsMouse ? Theme.hoverOverlay : "transparent")
        Behavior on color {
            ColorAnimation { duration: Theme.durFast }
        }
    }

    Icon {
        id: glyph
        anchors.left: parent.left
        anchors.leftMargin: 20
        anchors.verticalCenter: parent.verticalCenter
        name: root.icon
        color: root.selected ? Theme.accent : Theme.textSecondary
        implicitWidth: 18
        implicitHeight: 18
        Behavior on color {
            ColorAnimation { duration: Theme.durFast }
        }
    }

    Text {
        anchors.left: glyph.right
        anchors.leftMargin: 12
        anchors.right: parent.right
        anchors.rightMargin: 12
        anchors.verticalCenter: parent.verticalCenter
        text: root.text
        color: root.selected ? Theme.textPrimary : Theme.textSecondary
        font.pixelSize: Theme.fontBody
        font.weight: root.selected ? Font.DemiBold : Font.Normal
        font.family: Theme.fontFamily
        elide: Text.ElideRight
    }

    MouseArea {
        id: mouseArea
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
