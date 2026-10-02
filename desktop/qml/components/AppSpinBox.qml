import QtQuick
import QtQuick.Controls

// Themed spin box with chevron steppers and an editable centre field.
SpinBox {
    id: control

    editable: true
    implicitHeight: 34
    implicitWidth: 132
    font.pixelSize: Theme.fontBody
    font.family: Theme.fontFamily
    leftPadding: 12
    rightPadding: 34

    contentItem: TextInput {
        text: control.displayText
        color: control.enabled ? Theme.textPrimary : Theme.textDisabled
        selectionColor: Theme.accent
        selectedTextColor: Theme.accentText
        horizontalAlignment: Qt.AlignLeft
        verticalAlignment: TextInput.AlignVCenter
        readOnly: !control.editable
        validator: control.validator
        inputMethodHints: control.inputMethodHints
        font: control.font
        clip: true
        leftPadding: 0
        rightPadding: 0
        topPadding: 0
        bottomPadding: 0
    }

    up.indicator: Rectangle {
        id: upIndicator
        x: control.mirrored ? 0 : control.width - width
        y: 0
        width: 28
        height: control.height / 2
        color: "transparent"

        HoverHandler { id: upHover }

        Rectangle {
            anchors.fill: parent
            anchors.margins: 1
            radius: Theme.radiusSmall
            color: control.up.pressed
                   ? Theme.pressedOverlay
                   : (upHover.hovered ? Theme.hoverOverlay : "transparent")
        }
        Icon {
            anchors.centerIn: parent
            name: "chevron-up"
            color: control.enabled ? Theme.textSecondary : Theme.textDisabled
            implicitWidth: 14
            implicitHeight: 14
        }
    }

    down.indicator: Rectangle {
        id: downIndicator
        x: control.mirrored ? 0 : control.width - width
        y: control.height - height
        width: 28
        height: control.height / 2
        color: "transparent"

        HoverHandler { id: downHover }

        Rectangle {
            anchors.fill: parent
            anchors.margins: 1
            radius: Theme.radiusSmall
            color: control.down.pressed
                   ? Theme.pressedOverlay
                   : (downHover.hovered ? Theme.hoverOverlay : "transparent")
        }
        Icon {
            anchors.centerIn: parent
            name: "chevron"
            color: control.enabled ? Theme.textSecondary : Theme.textDisabled
            implicitWidth: 14
            implicitHeight: 14
        }
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
