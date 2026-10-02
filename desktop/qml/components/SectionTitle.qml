import QtQuick
import QtQuick.Layouts

// Card / page section header: optional accent icon, title and a subtitle.
ColumnLayout {
    id: root

    property string title: ""
    property string subtitle: ""
    property string icon: ""
    property int titleSize: Theme.fontTitle

    spacing: 3

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space2

        Icon {
            visible: root.icon.length > 0
            name: root.icon
            color: Theme.accent
            Layout.preferredWidth: 18
            Layout.preferredHeight: 18
            Layout.alignment: Qt.AlignVCenter
        }

        Text {
            text: root.title
            color: Theme.textPrimary
            font.pixelSize: root.titleSize
            font.weight: Font.DemiBold
            font.family: Theme.fontFamily
            Layout.fillWidth: true
        }
    }

    Text {
        visible: root.subtitle.length > 0
        text: root.subtitle
        color: Theme.textSecondary
        font.pixelSize: Theme.fontSmall
        font.family: Theme.fontFamily
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
}
