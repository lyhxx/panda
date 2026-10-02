import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Flat, macOS-flavoured button with four variants.
//
//   primary   - solid accent fill, used for the single main action
//   secondary - subtle filled surface with a hairline border
//   ghost     - transparent until hovered
//   danger    - solid red, used for destructive confirmation
Button {
    id: control

    property string variant: "secondary"
    property string iconName: ""
    property int minHeight: 34
    property int radius: Theme.radiusControl

    readonly property color foreground: {
        if (!enabled) {
            return Theme.textDisabled
        }
        if (variant === "primary" || variant === "danger") {
            return Theme.accentText
        }
        return Theme.textPrimary
    }

    readonly property color backgroundColor: {
        if (!enabled) {
            return Theme.controlDisabled
        }
        switch (variant) {
        case "primary":
            return down ? Theme.accentPressed : (hovered ? Theme.accentHover : Theme.accent)
        case "danger":
            return down ? Theme.danger : (hovered ? Theme.dangerHover : Theme.danger)
        case "ghost":
            return down ? Theme.pressedOverlay : (hovered ? Theme.hoverOverlay : "transparent")
        default:
            return down ? Theme.controlPressed : (hovered ? Theme.controlHover : Theme.control)
        }
    }

    readonly property color borderColor: {
        if (!enabled || variant === "primary" || variant === "danger" || variant === "ghost") {
            return "transparent"
        }
        return Theme.controlBorder
    }

    hoverEnabled: true
    leftPadding: 16
    rightPadding: 16
    topPadding: 7
    bottomPadding: 7
    font.pixelSize: Theme.fontBody
    font.family: Theme.fontFamily

    implicitHeight: Math.max(minHeight, contentItem.implicitHeight + topPadding + bottomPadding)
    implicitWidth: contentItem.implicitWidth + leftPadding + rightPadding

    contentItem: RowLayout {
        width: control.availableWidth
        height: control.availableHeight
        spacing: control.iconName.length > 0 ? 7 : 0

        Item { Layout.fillWidth: true }

        Icon {
            visible: control.iconName.length > 0
            name: control.iconName
            color: control.foreground
            Layout.preferredWidth: 16
            Layout.preferredHeight: 16
            Layout.alignment: Qt.AlignVCenter
        }

        Text {
            text: control.text
            color: control.foreground
            font.pixelSize: control.font.pixelSize
            font.family: control.font.family
            font.weight: control.variant === "primary" ? Font.DemiBold : Font.Normal
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
            Layout.alignment: Qt.AlignVCenter
        }

        Item { Layout.fillWidth: true }
    }

    background: Rectangle {
        radius: control.radius
        color: control.backgroundColor
        border.width: control.borderColor.a > 0 ? 1 : 0
        border.color: control.borderColor

        Behavior on color {
            ColorAnimation { duration: Theme.durFast; easing.type: Theme.easing }
        }
    }
}
