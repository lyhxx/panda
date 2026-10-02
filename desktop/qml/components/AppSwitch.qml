import QtQuick
import QtQuick.Controls

// macOS-style switch used for the on/off pipeline options.
Switch {
    id: control

    spacing: 8
    font.pixelSize: Theme.fontBody
    font.family: Theme.fontFamily

    indicator: Rectangle {
        implicitWidth: 42
        implicitHeight: 26
        radius: height / 2
        x: control.text.length > 0
           ? (control.mirrored ? control.width - width - control.rightPadding : control.leftPadding)
           : control.leftPadding + (control.availableWidth - width) / 2
        y: (control.height - height) / 2

        color: !control.enabled
               ? Theme.controlDisabled
               : (control.checked ? Theme.accent : (Theme.dark ? "#3A3A42" : "#D2D2D8"))
        Behavior on color {
            ColorAnimation { duration: Theme.durFast }
        }

        Rectangle {
            id: knob
            width: 22
            height: 22
            radius: height / 2
            y: (parent.height - height) / 2
            x: control.checked ? parent.width - width - 2 : 2
            color: "#FFFFFF"
            border.width: 1
            border.color: "#33000000"

            Behavior on x {
                NumberAnimation { duration: Theme.durNormal; easing.type: Theme.easing }
            }
        }
    }

    contentItem: Text {
        leftPadding: control.indicator && !control.mirrored ? control.indicator.width + control.spacing : 0
        rightPadding: control.indicator && control.mirrored ? control.indicator.width + control.spacing : 0
        text: control.text
        font: control.font
        color: control.enabled ? Theme.textPrimary : Theme.textDisabled
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
}
