import QtQuick
import QtQuick.Controls

// A square, chromeless icon button with an attached tooltip.
//
// Used for window chrome, favourite toggles, preview/delete affordances and
// the theme switch, where a labelled button would be too heavy.
AbstractButton {
    id: control

    property string iconName: ""
    property int iconSize: 17
    property int size: 30
    property int radius: Theme.radiusSmall
    property string tooltip: ""
    property color iconColor: Theme.textSecondary
    property color iconColorActive: Theme.textPrimary
    property bool danger: false
    property bool iconFilled: false

    implicitWidth: size
    implicitHeight: size
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus

    readonly property color effectiveIconColor: {
        if (!enabled) {
            return Theme.textDisabled
        }
        if (danger) {
            return control.down ? Theme.dangerHover : (control.hovered ? Theme.danger : Theme.textSecondary)
        }
        return (control.hovered || control.down || control.activeFocus)
                ? iconColorActive
                : iconColor
    }

    background: Rectangle {
        radius: control.radius
        color: control.down
               ? Theme.pressedOverlay
               : (control.hovered ? Theme.hoverOverlay : "transparent")
    }

    Icon {
        id: glyph
        anchors.centerIn: parent
        name: control.iconName
        color: control.effectiveIconColor
        filled: control.iconFilled || control.iconName === "play" || control.iconName === "stop"
        implicitWidth: control.iconSize
        implicitHeight: control.iconSize
        Behavior on color {
            ColorAnimation { duration: Theme.durFast }
        }
    }

    // Framed focus ring for keyboard users only.
    Rectangle {
        anchors.fill: parent
        radius: control.radius
        color: "transparent"
        border.width: 2
        border.color: Theme.accent
        visible: control.activeFocus
        opacity: 0.9
    }

    Tooltip { id: tip; anchorItem: control; text: control.tooltip }
}
