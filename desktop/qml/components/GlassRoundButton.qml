import QtQuick
import QtQuick.Controls

// Circular glass button used in the floating control bar.
AbstractButton {
    id: root

    property string iconName: ""
    property bool active: false
    property string tooltip: ""
    property bool tooltipAbove: false
    property int diameter: 56

    implicitWidth: diameter
    implicitHeight: diameter
    hoverEnabled: true

    background: Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: root.active
               ? Theme.accent
               : (root.down
                  ? Theme.pressedOverlay
                  : (root.hovered ? Theme.hoverOverlay : Theme.glassStrong))
        border.width: 1
        border.color: root.active ? Theme.glassHighlight : Theme.glassBorder
        Behavior on color {
            ColorAnimation { duration: Theme.durFast }
        }
    }

    contentItem: Item { }

    Icon {
        anchors.centerIn: parent
        name: root.iconName
        color: root.active ? Theme.accentText : Theme.textPrimary
        implicitWidth: 22
        implicitHeight: 22
    }

    Tooltip { anchorItem: root; text: root.tooltip; above: root.tooltipAbove }
}
