import QtQuick
import QtQuick.Controls

// Themed single-line text field with an optional leading icon.
TextField {
    id: control

    property string leadingIcon: ""

    placeholderTextColor: Theme.textTertiary
    color: Theme.textPrimary
    font.pixelSize: Theme.fontBody
    font.family: Theme.fontFamily
    selectByMouse: true
    selectionColor: Theme.accent
    selectedTextColor: Theme.accentText

    leftPadding: leadingIcon.length > 0 ? 34 : 12
    rightPadding: 12
    topPadding: 8
    bottomPadding: 8

    implicitHeight: 36
    implicitWidth: 200

    Icon {
        visible: control.leadingIcon.length > 0
        anchors.left: parent.left
        anchors.leftMargin: 12
        anchors.verticalCenter: parent.verticalCenter
        name: control.leadingIcon
        color: Theme.textTertiary
        implicitWidth: 15
        implicitHeight: 15
    }

    background: Rectangle {
        radius: Theme.radiusControl
        color: control.enabled ? Theme.control : Theme.controlDisabled
        border.width: 1
        border.color: control.activeFocus ? Theme.accent : Theme.controlBorder
        Behavior on border.color {
            ColorAnimation { duration: Theme.durFast }
        }
    }
}
