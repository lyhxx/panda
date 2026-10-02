import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Themed modal confirmation dialog with a dimmed backdrop.
Popup {
    id: root

    property string title: ""
    property string message: ""
    property string confirmText: qsTr("确定")
    property string cancelText: qsTr("取消")
    property bool destructive: false

    signal confirmed()
    signal canceled()

    modal: true
    focus: true
    width: 400
    padding: Theme.space5
    anchors.centerIn: Overlay.overlay
    closePolicy: Popup.CloseOnEscape

    Overlay.modal: Rectangle {
        color: Theme.scrim
    }

    background: Rectangle {
        radius: Theme.radiusCard
        color: Theme.dark ? "#26262C" : "#FFFFFF"
        border.width: 1
        border.color: Theme.cardBorder
    }

    contentItem: ColumnLayout {
        spacing: Theme.space4

        Text {
            text: root.title
            color: Theme.textPrimary
            font.pixelSize: Theme.fontTitle
            font.weight: Font.DemiBold
            font.family: Theme.fontFamily
            Layout.fillWidth: true
        }

        Text {
            text: root.message
            color: Theme.textSecondary
            font.pixelSize: Theme.fontBody
            font.family: Theme.fontFamily
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: Theme.space1
            spacing: Theme.space3

            Item { Layout.fillWidth: true }

            AppButton {
                text: root.cancelText
                variant: "secondary"
                onClicked: {
                    root.canceled()
                    root.close()
                }
            }

            AppButton {
                text: root.confirmText
                variant: root.destructive ? "danger" : "primary"
                onClicked: {
                    root.confirmed()
                    root.close()
                }
            }
        }
    }

    onClosed: {
        // Treated as cancel when dismissed without a button (Escape / backdrop).
    }
}
