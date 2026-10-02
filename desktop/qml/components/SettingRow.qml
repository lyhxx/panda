import QtQuick
import QtQuick.Layouts

// A macOS System-Settings style row: label (and hint) on the left, the control
// on the right, with an optional hairline separator underneath.
ColumnLayout {
    id: root

    property string label: ""
    property string hint: ""
    property real controlWidth: -1
    property bool showSeparator: false
    default property alias control: slot.data

    spacing: Theme.space2

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space5

        ColumnLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignVCenter
            spacing: 2

            Text {
                text: root.label
                color: Theme.textPrimary
                font.pixelSize: Theme.fontBody
                font.family: Theme.fontFamily
                Layout.fillWidth: true
            }
            Text {
                visible: root.hint.length > 0
                text: root.hint
                color: Theme.textTertiary
                font.pixelSize: Theme.fontSmall
                font.family: Theme.fontFamily
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }

        RowLayout {
            id: slot
            Layout.alignment: Qt.AlignVCenter
            Layout.preferredWidth: root.controlWidth > 0 ? root.controlWidth : implicitWidth
            spacing: Theme.space2
        }
    }

    Rectangle {
        Layout.fillWidth: true
        Layout.topMargin: Theme.space1
        height: 1
        color: Theme.separator
        visible: root.showSeparator
    }
}
