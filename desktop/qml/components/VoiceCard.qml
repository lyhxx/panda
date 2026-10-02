import QtQuick

// Voice-pack card: a circular avatar with the name below, matching the
// reference gallery. The selected voice is ringed and slightly enlarged;
// favourite and hover actions float around the avatar.
Item {
    id: root

    required property string packId
    required property string displayName
    required property string packVersion
    required property string engine
    required property string kind
    required property string folderPath
    required property string iconPath
    required property string referencePath
    required property bool isFavorite

    signal deleteRequested(string packId, string packName)

    readonly property bool selected: AppState.selectedPack === folderPath
    readonly property bool hovered: mouse.containsMouse
    readonly property bool canInteract: !realtimeController.running

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: AppState.selectedPack = root.folderPath
    }

    Item {
        id: avatarArea
        width: 108
        height: 108
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        anchors.topMargin: 8
        scale: root.selected ? 1.07 : (root.hovered ? 1.03 : 1.0)
        Behavior on scale {
            NumberAnimation { duration: Theme.durNormal; easing.type: Theme.easing }
        }

        Rectangle {
            anchors.fill: parent
            radius: width / 2
            color: "transparent"
            border.width: root.selected ? 3 : (root.hovered ? 1 : 0)
            border.color: Theme.accent
        }

        Rectangle {
            anchors.centerIn: parent
            width: 90
            height: 90
            radius: width / 2
            visible: root.iconPath.length === 0
            gradient: Gradient {
                GradientStop {
                    position: 0.0
                    color: root.selected
                           ? Theme.accent
                           : (Theme.dark ? "#3A4256" : "#DCE1EA")
                }
                GradientStop {
                    position: 1.0
                    color: root.selected
                           ? Qt.darker(Theme.accent, 1.3)
                           : (Theme.dark ? "#29303F" : "#C6CDDA")
                }
            }

            Text {
                anchors.centerIn: parent
                text: root.displayName.length > 0
                      ? root.displayName.substring(0, 1)
                      : "?"
                color: root.selected
                       ? Theme.accentText
                       : (Theme.dark ? "#EAF1F8" : "#2B3340")
                font.pixelSize: 34
                font.weight: Font.DemiBold
                font.family: Theme.fontFamily
            }
        }

        Image {
            anchors.centerIn: parent
            width: 90
            height: 90
            visible: root.iconPath.length > 0
            source: root.iconPath.length > 0
                    ? "file:///" + root.iconPath.replace(/\\/g, "/")
                    : ""
            sourceSize.width: 180
            sourceSize.height: 180
            fillMode: Image.PreserveAspectFit
            smooth: true
            mipmap: true
        }

        AppIconButton {
            anchors.top: parent.top
            anchors.right: parent.right
            size: 26
            iconSize: 15
            iconName: "star"
            iconFilled: root.isFavorite
            iconColor: root.isFavorite ? Theme.warning : Theme.textTertiary
            iconColorActive: root.isFavorite ? Theme.warning : Theme.textPrimary
            tooltip: root.isFavorite ? qsTr("取消收藏") : qsTr("收藏")
            onClicked: packListModel.toggleFavorite(root.packId)
        }
    }

    Text {
        id: nameLabel
        anchors.top: avatarArea.bottom
        anchors.topMargin: 8
        anchors.left: parent.left
        anchors.right: parent.right
        text: root.displayName
        color: Theme.textPrimary
        font.pixelSize: Theme.fontBody
        font.weight: Font.DemiBold
        font.family: Theme.fontFamily
        horizontalAlignment: Text.AlignHCenter
        elide: Text.ElideRight
    }

    Row {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: nameLabel.bottom
        anchors.topMargin: 4
        spacing: 2
        opacity: (root.selected || root.hovered || previewButton.hovered || deleteButton.hovered)
                 ? 1 : 0
        Behavior on opacity {
            NumberAnimation { duration: Theme.durFast }
        }

        AppIconButton {
            id: previewButton
            size: 28
            iconSize: 15
            iconName: "play"
            tooltip: qsTr("试听")
            enabled: root.canInteract && !realtimeController.previewing
            onClicked: realtimeController.previewFile(root.referencePath)
        }

        AppIconButton {
            id: deleteButton
            size: 28
            iconSize: 15
            iconName: "trash"
            danger: true
            tooltip: qsTr("删除")
            onClicked: root.deleteRequested(root.packId, root.displayName)
        }
    }
}
