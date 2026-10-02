import QtQuick
import QtQuick.Controls

// iOS-style horizontal slider: a thin track, a filled portion and a round
// handle with a dot. Replaces spin boxes for the volume controls.
Slider {
    id: control

    implicitWidth: 220
    implicitHeight: 28
    padding: 0
    stepSize: 1
    snapMode: Slider.SnapAlways
    hoverEnabled: true

    readonly property color activeColor: control.enabled ? Theme.accent : Theme.textDisabled

    background: Rectangle {
        x: control.leftPadding
        y: control.topPadding + (control.availableHeight - height) / 2
        width: control.availableWidth
        height: 5
        radius: height / 2
        color: Theme.dark ? "#3A3A42" : "#D6D6DC"

        Rectangle {
            width: control.visualPosition * parent.width
            height: parent.height
            radius: parent.radius
            color: control.activeColor
            Behavior on color {
                ColorAnimation { duration: Theme.durFast }
            }
        }
    }

    handle: Rectangle {
        x: control.leftPadding + control.visualPosition * (control.availableWidth - width)
        y: control.topPadding + (control.availableHeight - height) / 2
        width: control.pressed || control.hovered ? 21 : 19
        height: width
        radius: width / 2
        color: "#FFFFFF"
        border.width: 1
        border.color: Theme.dark ? "#33000000" : "#22000000"

        Behavior on width {
            NumberAnimation { duration: Theme.durFast }
        }

        Rectangle {
            anchors.centerIn: parent
            width: parent.width * 0.42
            height: width
            radius: width / 2
            color: control.activeColor
        }
    }
}
