import QtQuick
import QtQuick.Layouts

// A top navigation tab, shown as a pill inside a glass group.
Item {
    id: root

    property string icon: ""
    property string text: ""
    property bool selected: false
    signal clicked()

    implicitWidth: row.implicitWidth + 28
    implicitHeight: 30

    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: root.selected
               ? Theme.glassStrong
               : (mouse.containsMouse ? Theme.hoverOverlay : "transparent")
        border.width: root.selected ? 1 : 0
        border.color: Theme.glassHighlight
        Behavior on color {
            ColorAnimation { duration: Theme.durFast }
        }
    }

    RowLayout {
        id: row
        anchors.centerIn: parent
        spacing: 6

        Icon {
            name: root.icon
            color: root.selected ? Theme.textPrimary : Theme.textSecondary
            Layout.preferredWidth: 15
            Layout.preferredHeight: 15
            Layout.alignment: Qt.AlignVCenter
        }

        Text {
            text: root.text
            color: root.selected ? Theme.textPrimary : Theme.textSecondary
            font.pixelSize: Theme.fontBody
            font.weight: root.selected ? Font.DemiBold : Font.Normal
            font.family: Theme.fontFamily
            Layout.alignment: Qt.AlignVCenter
        }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
