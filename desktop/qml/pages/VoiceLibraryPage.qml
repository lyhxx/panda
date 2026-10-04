import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

// Voice library: category tabs, search / install, and a circular-avatar grid.
Item {
    id: page

    property string pendingArchive: ""
    property string pendingArchiveName: ""
    property string pendingPackId: ""
    property string pendingPackName: ""

    // A multi-selection installs one archive at a time so an "already
    // installed" hit can pause the run for a confirmation and resume after it.
    property var queue: []
    property int queueIndex: 0
    property int queueInstalled: 0
    property int queueFailed: 0
    property int queueSkipped: 0
    property int queueFailCode: 0
    property string queueFailText: ""
    property string overwriteResult: ""

    function archivePath(fileUrl) {
        return decodeURIComponent(String(fileUrl).replace(/^file:\/\/\//, ""))
    }

    function rememberFirstFailure() {
        if (queueFailText.length === 0) {
            queueFailText = packListModel.lastError
            queueFailCode = packListModel.lastErrorCode
        }
    }

    function startInstallQueue(fileUrls) {
        queue = []
        for (let i = 0; i < fileUrls.length; ++i) {
            queue.push(archivePath(fileUrls[i]))
        }
        queueIndex = 0
        queueInstalled = 0
        queueFailed = 0
        queueSkipped = 0
        queueFailText = ""
        queueFailCode = 0
        packListModel.clearMessages()
        Qt.callLater(stepInstallQueue)
    }

    function stepInstallQueue() {
        if (queueIndex >= queue.length) {
            // A single archive keeps installPack's own message, which names
            // the pack; only a real batch needs counting.
            if (queue.length > 1) {
                packListModel.reportBatch(queueInstalled, queueFailed,
                                          queueSkipped, queueFailCode,
                                          queueFailText)
            }
            return
        }
        const path = queue[queueIndex]
        if (packListModel.installPack(path, false)) {
            queueInstalled += 1
        } else if (packListModel.lastErrorIsAlreadyInstalled) {
            pendingArchive = path
            pendingArchiveName = path.split(/[\\/]/).pop()
            overwriteResult = ""
            overwriteDialog.open()
            return  // resumed by overwriteDialog.onClosed
        } else {
            queueFailed += 1
            rememberFirstFailure()
        }
        queueIndex += 1
        Qt.callLater(stepInstallQueue)
    }

    // Resumed from overwriteDialog.onClosed for every way that dialog can
    // end, including Escape, which fires neither confirmed nor canceled.
    function resumeAfterOverwrite(cover) {
        if (cover && packListModel.installPack(pendingArchive, true)) {
            queueInstalled += 1
        } else if (!cover) {
            queueSkipped += 1
        } else {
            queueFailed += 1
            rememberFirstFailure()
        }
        queueIndex += 1
        Qt.callLater(stepInstallQueue)
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
        // Qt 6 spells multi-select as a file mode, not the Qt 5 flag.
        fileMode: FileDialog.OpenFiles
        nameFilters: [
            qsTr("Panda 音色包 (*.zip)"),
            qsTr("所有文件 (*)")
        ]
        onAccepted: page.startInstallQueue(selectedFiles)
    }

    // ---- Auto-dismissing banners -----------------------------------------
    // The green line is gone after a few seconds; a failure stays up longer
    // so its reason can actually be read.
    Timer {
        id: messageTimer
        interval: 4000
        // clearMessages() wipes BOTH banners: a failure that landed while
        // this timer was armed (batch installs do exactly that) must keep
        // its own full window, so only a message-only state expires here.
        onTriggered: {
            if (packListModel.lastError.length === 0) {
                packListModel.clearMessages()
            }
        }
    }

    Timer {
        id: errorTimer
        interval: 8000
        // Only clear a failure that is still showing; an error already
        // replaced by a fresh success message must not take the green line
        // with it on its way out.
        onTriggered: {
            if (packListModel.lastError.length > 0) {
                packListModel.clearMessages()
            }
        }
    }

    Connections {
        target: packListModel

        function onLastMessageChanged() {
            if (packListModel.lastMessage.length > 0) {
                messageTimer.restart()
            }
        }
        function onLastErrorChanged() {
            if (packListModel.lastError.length > 0) {
                errorTimer.restart()
            }
        }
    }

    Component.onCompleted: {
        // Timers die with the page; coming back to a banner that survived a
        // route change has to start its countdown again.
        if (packListModel.lastMessage.length > 0) {
            messageTimer.restart()
        }
        if (packListModel.lastError.length > 0) {
            errorTimer.restart()
        }
    }

    AppConfirmDialog {
        id: overwriteDialog
        title: qsTr("覆盖安装")
        message: qsTr("「%1」已经安装过同 ID 的音色包，是否覆盖？")
                     .arg(page.pendingArchiveName)
        confirmText: qsTr("覆盖")
        // The buttons only mark the answer; the queue advances here, once,
        // because closing with Escape or the backdrop fires no other signal.
        onConfirmed: page.overwriteResult = "yes"
        onCanceled: page.overwriteResult = "no"
        onClosed: {
            const answer = page.overwriteResult
            page.overwriteResult = ""
            page.resumeAfterOverwrite(answer === "yes")
        }
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
