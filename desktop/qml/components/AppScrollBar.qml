import QtQuick
import QtQuick.Controls

// Thin, self-hiding scrollbar that replaces the platform one.
ScrollBar {
    id: control

    padding: 3
    policy: ScrollBar.AsNeeded
    minimumSize: 0.08
    implicitWidth: 11
    implicitHeight: 11
    hoverEnabled: true

    contentItem: Rectangle {
        implicitWidth: 6
        implicitHeight: 6
        radius: width / 2
        color: control.pressed ? Theme.textSecondary : Theme.textTertiary
        opacity: (control.active || control.hovered) && control.policy !== ScrollBar.AlwaysOff ? 0.9 : 0.0
        Behavior on opacity {
            NumberAnimation { duration: Theme.durNormal }
        }
    }

    background: Item { }
}
