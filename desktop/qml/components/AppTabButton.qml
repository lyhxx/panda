import QtQuick
import QtQuick.Controls

// Top category tab with an animated accent underline.
TabButton {
    id: control

    implicitWidth: contentItem.implicitWidth + 24

    contentItem: Text {
        text: control.text
        color: control.checked ? Theme.textPrimary : Theme.textSecondary
        font.pixelSize: Theme.fontTitle
        font.weight: control.checked ? Font.DemiBold : Font.Normal
        font.family: Theme.fontFamily
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }

    background: Item {
        Rectangle {
            anchors.bottom: parent.bottom
            anchors.horizontalCenter: parent.horizontalCenter
            width: Math.max(0, parent.width - 6)
            height: 2
            radius: 1
            color: Theme.accent
            visible: control.checked
        }
    }
}
