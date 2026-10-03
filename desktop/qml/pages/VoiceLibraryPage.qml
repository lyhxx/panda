import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

// Voice library: category tabs, search / install, and a circular-avatar grid.
Item {
    id: page

    property string pendingArchive: ""
    property string pendingPackId: ""
    property string pendingPackName: ""

    function installArchive(fileUrl) {
        const path = decodeURIComponent(String(fileUrl).replace(/^file:\/\/\//, ""))
        page.pendingArchive = path
        packListModel.clearMessages()
        if (!packListModel.installPack(path, false)
                && packListModel.lastErrorIsAlreadyInstalled) {
            overwriteDialog.open()
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.space6
        anchors.rightMargin: Theme.space6
        anchors.topMargin: Theme.space1
        anchors.bottomMargin: 100
        spacing: Theme.space4

        // ---- Toolbar -----------------------------------------------------
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space3

            Item { Layout.fillWidth: true }

            AppTextField {
                Layout.preferredWidth: 260
                placeholderText: qsTr("搜索名称或拼音")
                leadingIcon: "search"
                text: packListModel.filter
                onTextEdited: packListModel.filter = text
            }

            AppButton {
                text: qsTr("安装音色包")
                iconName: "plus"
                variant: "primary"
                onClicked: {
                    packListModel.clearMessages()
                    installDialog.open()
                }
            }
        }

        // ---- Banners -----------------------------------------------------
        Rectangle {
            Layout.fillWidth: true
            visible: packListModel.lastError.length > 0
            implicitHeight: errorText.implicitHeight + 20
            radius: Theme.radiusControl
            color: Qt.rgba(Theme.danger.r, Theme.danger.g, Theme.danger.b, 0.14)
            border.width: 1
            border.color: Qt.rgba(Theme.danger.r, Theme.danger.g, Theme.danger.b, 0.35)

            RowLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 8
                Icon {
                    name: "alert"
                    color: Theme.danger
                    implicitWidth: 16
                    implicitHeight: 16
                    Layout.alignment: Qt.AlignTop
                }
                Text {
                    id: errorText
                    Layout.fillWidth: true
                    text: packListModel.lastError
                    color: Theme.danger
                    font.pixelSize: Theme.fontBody
                    font.family: Theme.fontFamily
                    wrapMode: Text.WordWrap
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            visible: packListModel.lastMessage.length > 0
            implicitHeight: messageText.implicitHeight + 20
            radius: Theme.radiusControl
            color: Qt.rgba(Theme.success.r, Theme.success.g, Theme.success.b, 0.14)
            border.width: 1
            border.color: Qt.rgba(Theme.success.r, Theme.success.g, Theme.success.b, 0.35)

            RowLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 8
                Icon {
                    name: "check"
                    color: Theme.success
                    implicitWidth: 16
                    implicitHeight: 16
                    Layout.alignment: Qt.AlignTop
                }
                Text {
                    id: messageText
                    Layout.fillWidth: true
                    text: packListModel.lastMessage
                    color: Theme.success
                    font.pixelSize: Theme.fontBody
                    font.family: Theme.fontFamily
                    wrapMode: Text.WordWrap
                }
            }
        }

        // ---- Grid --------------------------------------------------------
        GridView {
            id: voiceGrid
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            cellWidth: 150
            cellHeight: 188
            model: packListModel
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: AppScrollBar { }
            visible: packListModel.count > 0

            delegate: VoiceCard {
                width: voiceGrid.cellWidth
                height: voiceGrid.cellHeight
                onDeleteRequested: function(packId, packName) {
                    page.pendingPackId = packId
                    page.pendingPackName = packName
                    deleteDialog.open()
                }
            }
        }

        // ---- Empty state -------------------------------------------------
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: packListModel.count === 0

            ColumnLayout {
                anchors.centerIn: parent
                width: Math.min(parent.width, 420)
                spacing: Theme.space3

                Rectangle {
                    Layout.alignment: Qt.AlignHCenter
                    width: 76
                    height: 76
                    radius: width / 2
                    color: Theme.glass

                    Icon {
                        anchors.centerIn: parent
                        name: "waveform"
                        color: Theme.textTertiary
                        implicitWidth: 30
                        implicitHeight: 30
                    }
                }

                Text {
                    Layout.fillWidth: true
                    text: qsTr("还没有安装音色包")
                    color: Theme.textPrimary
                    font.pixelSize: Theme.fontHeading
                    font.weight: Font.DemiBold
                    font.family: Theme.fontFamily
                    horizontalAlignment: Text.AlignHCenter
                }

                Text {
                    Layout.fillWidth: true
                    text: qsTr("点击「安装音色包」导入 ZIP，或把音色包文件夹直接放进 voices 目录，列表会自动更新。")
                    color: Theme.textSecondary
                    font.pixelSize: Theme.fontBody
                    font.family: Theme.fontFamily
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                }

                AppButton {
                    Layout.alignment: Qt.AlignHCenter
                    text: qsTr("安装音色包")
                    iconName: "plus"
                    variant: "primary"
                    onClicked: {
                        packListModel.clearMessages()
                        installDialog.open()
                    }
                }
            }
        }
    }

    FileDialog {
        id: installDialog
        title: qsTr("选择音色包")
        nameFilters: [
            qsTr("Panda 音色包 (*.zip)"),
            qsTr("所有文件 (*)")
        ]
        onAccepted: page.installArchive(selectedFile)
    }

    AppConfirmDialog {
        id: overwriteDialog
        title: qsTr("覆盖安装")
        message: qsTr("已经安装过同 ID 的音色包，是否覆盖？")
        confirmText: qsTr("覆盖")
        onConfirmed: packListModel.installPack(page.pendingArchive, true)
    }

    AppConfirmDialog {
        id: deleteDialog
        title: qsTr("删除音色包")
        message: qsTr("确定删除「%1」吗？此操作不可撤销。").arg(page.pendingPackName)
        confirmText: qsTr("删除")
        destructive: true
        onConfirmed: {
            packListModel.removePack(page.pendingPackId)
            AppState.reconcilePackSelection(packListModel)
        }
    }
}
