import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Application shell: a frameless liquid-glass window with a top navigation bar,
// a stacked page area and a floating control bar.
ApplicationWindow {
    id: root

    width: 1180
    height: 780
    minimumWidth: 960
    minimumHeight: 640
    visible: true
    title: productName
    color: "transparent"
    // Qt.FramelessWindowHint alone leaves the style without WS_MINIMIZEBOX,
    // so Windows refuses to minimize the window from the taskbar (the
    // title-bar button still worked because it calls showMinimized() itself).
    // The hint only sets the style bit -- it does not draw a system frame.
    flags: Qt.Window | Qt.FramelessWindowHint | Qt.WindowMinimizeButtonHint

    property int lastMonitorDevice: -1

    // The worker reports progress at real stage boundaries, so its number
    // arrives in steps (20 -> 30 -> 59 -> 80). Ease the displayed value
    // toward it so the text counts up continuously instead of jumping. A new
    // load resets the real value to zero, and snapping there beats animating
    // a restart backwards through every percentage it just showed.
    property real shownProgress: 0
    property bool easingProgress: false
    Behavior on shownProgress {
        enabled: root.easingProgress
        NumberAnimation {
            duration: 700
            easing.type: Easing.OutCubic
        }
    }
    Connections {
        target: realtimeController
        function onStartupProgressChanged() {
            var v = realtimeController.startupProgress
            root.easingProgress = v > root.shownProgress
            root.shownProgress = v
        }
    }

    readonly property string selectedPackName: AppState.selectedPack.length > 0
        ? (packListModel.displayNameForFolder(AppState.selectedPack)
           || AppState.selectedPack.replace(/\\/g, "/").split("/").pop())
        : qsTr("未选择音色")

    readonly property bool monitorOn: AppState.selectedMonitorDevice >= 0
    readonly property bool outputIsVirtual: AppState.selectedOutputDevice >= 0
        && AppState.deviceIsVirtual(realtimeController.outputDevices,
                                    AppState.selectedOutputDevice)

    function monitorDeviceName() {
        const id = AppState.selectedMonitorDevice
        if (id < 0) {
            return ""
        }
        const list = realtimeController.outputDevices
        for (let i = 0; i < list.length; ++i) {
            if (list[i].id === id) {
                return list[i].deviceName
            }
        }
        return ""
    }

    Binding {
        target: Theme
        property: "dark"
        value: themeManager.dark
    }

    function applySettings() {
        const saved = sessionStore.load()
        if (packListModel.containsFolder(saved.voicePack)) {
            AppState.selectedPack = saved.voicePack
        }
        AppState.selectedModel = saved.model
        AppState.selectedCompute = saved.compute
        AppState.selectedInputDevice = saved.inputDevice
        AppState.selectedOutputDevice = saved.outputDevice
        AppState.selectedMonitorDevice = saved.monitorDevice
        AppState.pendingInputDeviceKey = saved.inputDeviceKey
        AppState.pendingOutputDeviceKey = saved.outputDeviceKey
        AppState.pendingMonitorDeviceKey = saved.monitorDeviceKey
        realtimeController.monitorDevice = saved.monitorDevice
        realtimeController.prefillChunks = saved.prefillChunks
        realtimeController.maxBacklogChunks = saved.maxBacklogChunks
        realtimeController.noiseGateEnabled = saved.noiseGateEnabled
        realtimeController.noiseGateDb = saved.noiseGateDb
        realtimeController.inputGainDb = saved.inputGainDb
        realtimeController.outputGainDb = saved.outputGainDb
        realtimeController.monitorGainDb = saved.monitorGainDb
        realtimeController.denoise = saved.denoise
        realtimeController.denoiseLevel = saved.denoiseLevel
    }

    function persistSettings() {
        sessionStore.save({
            "voicePack": AppState.selectedPack,
            "model": AppState.selectedModel,
            "compute": AppState.selectedCompute,
            "inputDevice": AppState.selectedInputDevice,
            "inputDeviceKey": AppState.deviceKey(
                realtimeController.inputDevices,
                AppState.selectedInputDevice
            ),
            "outputDevice": AppState.selectedOutputDevice,
            "outputDeviceKey": AppState.deviceKey(
                realtimeController.outputDevices,
                AppState.selectedOutputDevice
            ),
            "monitorDevice": AppState.selectedMonitorDevice,
            "monitorDeviceKey": AppState.deviceKey(
                realtimeController.outputDevices,
                AppState.selectedMonitorDevice
            ),
            "prefillChunks": realtimeController.prefillChunks,
            "maxBacklogChunks": realtimeController.maxBacklogChunks,
            "noiseGateEnabled": realtimeController.noiseGateEnabled,
            "noiseGateDb": realtimeController.noiseGateDb,
            "inputGainDb": realtimeController.inputGainDb,
            "outputGainDb": realtimeController.outputGainDb,
            "monitorGainDb": realtimeController.monitorGainDb,
            "denoise": realtimeController.denoise,
            "denoiseLevel": realtimeController.denoiseLevel
        })
    }

    function toggleRealtime() {
        if (realtimeController.running) {
            realtimeController.stop()
            return
        }
        realtimeController.startRealtime(
            AppState.selectedPack,
            AppState.selectedModel,
            AppState.selectedCompute,
            AppState.selectedInputDevice,
            AppState.selectedOutputDevice
        )
    }

    function toggleMonitor() {
        if (AppState.selectedMonitorDevice >= 0) {
            root.lastMonitorDevice = AppState.selectedMonitorDevice
            AppState.selectedMonitorDevice = -1
            return
        }
        const outputs = AppState.filteredDevices(realtimeController.outputDevices)
        const fallback = AppState.firstDeviceId(
            outputs, realtimeController.defaultOutputDevice,
            realtimeController.outputDevices
        )
        AppState.selectedMonitorDevice = root.lastMonitorDevice >= 0
            ? root.lastMonitorDevice
            : fallback
    }

    // Keep a live microphone meter running while the audio settings are shown,
    // so the user does not need to start a conversion just to see input level.
    function syncMicMonitor() {
        const watching = AppState.settingsOpen
                         && AppState.settingsTab === "audio"
                         && !realtimeController.running
                         && AppState.selectedInputDevice >= 0
        if (watching) {
            realtimeController.startMicMonitor(AppState.selectedInputDevice)
        } else {
            realtimeController.stopMicMonitor()
        }
    }

    function pushLiveDevices() {
        if (realtimeController.running) {
            realtimeController.updateLiveDevices(
                AppState.selectedInputDevice,
                AppState.selectedOutputDevice
            )
        }
    }

    Component.onCompleted: {
        applySettings()
        realtimeController.refreshDevices()
        syncMicMonitor()
    }

    onClosing: {
        persistSettings()
        realtimeController.stopMicMonitor()
        // Quitting: no drain. A worker that outlived the window would keep the
        // microphone open, and the next start would fail with "device busy".
        realtimeController.stopNow()
    }

    Connections {
        target: realtimeController

        function onDevicesChanged() {
            // Only WASAPI devices are selectable, so resolve against that list
            // and normalise anything that cannot be shown.
            const inputs = AppState.filteredDevices(realtimeController.inputDevices)
            const outputs = AppState.filteredDevices(realtimeController.outputDevices)

            let inputId = AppState.resolveDeviceId(inputs, AppState.pendingInputDeviceKey)
            if (inputId < 0 && AppState.containsDevice(inputs, AppState.selectedInputDevice)) {
                inputId = AppState.selectedInputDevice
            }
            AppState.selectedInputDevice = inputId >= 0
                ? inputId
                : AppState.firstDeviceId(inputs, realtimeController.defaultInputDevice,
                                         realtimeController.inputDevices)
            AppState.pendingInputDeviceKey = ""

            let outputId = AppState.resolveDeviceId(outputs, AppState.pendingOutputDeviceKey)
            if (AppState.pendingOutputDeviceKey === "none") {
                outputId = -1
            } else if (outputId < 0 && AppState.containsDevice(outputs, AppState.selectedOutputDevice)) {
                outputId = AppState.selectedOutputDevice
            }
            AppState.selectedOutputDevice = outputId >= 0
                ? outputId
                : (AppState.pendingOutputDeviceKey === "none"
                   ? -1
                   : AppState.firstDeviceId(outputs, realtimeController.defaultOutputDevice,
                                            realtimeController.outputDevices))
            AppState.pendingOutputDeviceKey = ""

            let monitorId = AppState.resolveDeviceId(outputs, AppState.pendingMonitorDeviceKey)
            if (AppState.pendingMonitorDeviceKey === "none") {
                monitorId = -1
            } else if (monitorId < 0 && AppState.containsDevice(outputs, AppState.selectedMonitorDevice)) {
                monitorId = AppState.selectedMonitorDevice
            }
            AppState.selectedMonitorDevice = monitorId
            AppState.pendingMonitorDeviceKey = ""
            if (monitorId >= 0) {
                root.lastMonitorDevice = monitorId
            }

            root.syncMicMonitor()
        }

        function onRunningChanged() {
            root.syncMicMonitor()
        }
    }

    Connections {
        target: packListModel

        // The library is shared with the file manager: a folder deleted out
        // there removes a row here, possibly the one being played. Re-home the
        // selection the moment the rescan lands.
        function onPacksChanged() {
            AppState.reconcilePackSelection(packListModel)
        }
    }

    Connections {
        target: AppState

        function onSettingsOpenChanged() { root.syncMicMonitor() }
        function onSettingsTabChanged() { root.syncMicMonitor() }
        function onSelectedPackChanged() {
            // The speaker embedding is baked in at startup, so switching the
            // voice needs a reload; do it automatically if we are running.
            if (realtimeController.running) {
                realtimeController.loadVoicePack(AppState.selectedPack)
            }
        }
        function onSelectedInputDeviceChanged() {
            root.syncMicMonitor()
            root.pushLiveDevices()
        }
        function onSelectedOutputDeviceChanged() {
            // Monitoring only applies to a virtual output; clear it when the
            // user picks a device they can already hear.
            if (AppState.selectedMonitorDevice >= 0
                    && !AppState.deviceIsVirtual(
                        realtimeController.outputDevices,
                        AppState.selectedOutputDevice
                    )) {
                AppState.selectedMonitorDevice = -1
            }
            root.pushLiveDevices()
        }
        // Monitoring has a single source of truth: the selected monitor device.
        // Selecting a device turns monitoring on; "不监听" turns it off.
        function onSelectedMonitorDeviceChanged() {
            realtimeController.monitorDevice = AppState.selectedMonitorDevice
        }
    }

    // ---- Window frame ----------------------------------------------------
    Rectangle {
        id: windowFrame
        anchors.fill: parent
        radius: Theme.radiusWindow
        color: "transparent"
        clip: true

        GlassBackground {
            anchors.fill: parent
        }

        ColumnLayout {
            anchors.fill: parent
            spacing: 0

            // ---- Top bar -------------------------------------------------
            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: 64

                MouseArea {
                    anchors.fill: parent
                    onPressed: root.startSystemMove()
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 18
                    anchors.rightMargin: 12
                    spacing: Theme.space3

                    Image {
                        source: "qrc:/assets/logo.png"
                        sourceSize.width: 64
                        sourceSize.height: 64
                        Layout.preferredWidth: 38
                        Layout.preferredHeight: 38
                        Layout.alignment: Qt.AlignVCenter
                        smooth: true
                        mipmap: true
                    }

                    Text {
                        text: productName
                        color: Theme.textPrimary
                        font.pixelSize: 18
                        font.weight: Font.DemiBold
                        font.family: Theme.fontFamily
                        Layout.alignment: Qt.AlignVCenter
                    }

                    Item { Layout.fillWidth: true }

                    SegmentedControl {
                        Layout.alignment: Qt.AlignVCenter
                        options: [
                            { "value": "system", "icon": "monitor", "tooltip": qsTr("跟随系统") },
                            { "value": "light", "icon": "sun", "tooltip": qsTr("浅色") },
                            { "value": "dark", "icon": "moon", "tooltip": qsTr("深色") }
                        ]
                        currentValue: themeManager.mode
                        onActivated: themeManager.mode = value
                    }

                    AppIconButton {
                        iconName: "minus"
                        iconSize: 16
                        size: 34
                        tooltip: qsTr("最小化")
                        onClicked: root.showMinimized()
                    }

                    AppIconButton {
                        iconName: "x"
                        iconSize: 16
                        size: 34
                        danger: true
                        tooltip: qsTr("关闭")
                        onClicked: root.close()
                    }
                }
            }

            // ---- Page ----------------------------------------------------
            VoiceLibraryPage {
                Layout.fillWidth: true
                Layout.fillHeight: true
            }
        }

        // ---- Floating control bar ---------------------------------------
        ColumnLayout {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 18
            spacing: 10
            visible: true

            // Status / metrics
            RowLayout {
                Layout.alignment: Qt.AlignHCenter
                spacing: Theme.space2

                Text {
                    text: realtimeController.previewing
                          && realtimeController.previewName.length > 0
                          ? realtimeController.previewName
                          : root.selectedPackName
                    color: Theme.textPrimary
                    font.pixelSize: Theme.fontSmall
                    font.weight: Font.DemiBold
                    font.family: Theme.fontFamily
                }

                Text {
                    text: {
                        if (realtimeController.running && !realtimeController.ready) {
                            return realtimeController.startupProgress > 0
                                   ? qsTr("正在加载模型… %1%").arg(
                                       Math.round(root.shownProgress)
                                   )
                                   : realtimeController.status
                        }
                        return realtimeController.status.length > 0
                               ? realtimeController.status
                               : qsTr("选择音色后点击「开启变声」")
                    }
                    color: realtimeController.running
                           ? Theme.success
                           : Theme.textSecondary
                    font.pixelSize: Theme.fontSmall
                    font.family: Theme.fontFamily
                }

                StatusPill {
                    visible: realtimeController.hasStats
                             && realtimeController.running
                    // Mouth-to-ear: device capture + our jitter buffer +
                    // conversion + device playback. Counting only the middle
                    // two terms made the readout look better than the delay
                    // the listener actually heard.
                    //
                    // Slowly smoothed, because the jitter buffer level is an
                    // instant reading: the converter hands audio over in
                    // 120/240 ms bursts, so the raw depth swings from ~0 ms to
                    // ~260 ms inside one cycle while the delay a person
                    // perceives is the average of it. A fast animation would
                    // just redraw that swing at 0.5 s intervals -- the "up to
                    // 400 ms" jumps the status bar used to show.
                    property real latencyShown: realtimeController.latencyMs
                    Behavior on latencyShown {
                        NumberAnimation {
                            duration: 2500
                            easing.type: Easing.OutCubic
                        }
                    }
                    text: qsTr("延迟 %1ms").arg(Math.round(latencyShown))
                }

                StatusPill {
                    visible: realtimeController.hasStats
                    tone: realtimeController.overrun ? Theme.danger : Theme.success
                    text: realtimeController.overrun ? qsTr("过载") : qsTr("正常")
                }

                StatusPill {
                    visible: root.monitorOn
                    tone: Theme.accent
                    text: qsTr("监听已开启")
                }
            }

            RowLayout {
                Layout.alignment: Qt.AlignHCenter
                spacing: Theme.space3

                PowerToggle {
                    on: realtimeController.running
                    busy: realtimeController.running && !realtimeController.ready
                    icon: "mic"
                    tooltipAbove: true
                    onToggled: root.toggleRealtime()
                }

                GlassRoundButton {
                    iconName: "headphones"
                    active: root.monitorOn
                    visible: root.outputIsVirtual
                    tooltipAbove: true
                    tooltip: root.monitorOn
                             ? qsTr("关闭监听（当前：%1）").arg(root.monitorDeviceName())
                             : qsTr("开启监听：开始变声后用系统默认输出听自己的变声")
                    onClicked: root.toggleMonitor()
                }

                GlassRoundButton {
                    iconName: "sliders"
                    tooltipAbove: true
                    tooltip: qsTr("更多设置")
                    onClicked: AppState.settingsOpen = true
                }
            }
        }
    }

    AppSettingsDialog { }

    // ---- Frameless resize handles ---------------------------------------
    MouseArea {
        z: 1000
        width: 6
        height: parent.height
        anchors.left: parent.left
        cursorShape: Qt.SizeHorCursor
        onPressed: root.startSystemResize(Qt.LeftEdge)
    }
    MouseArea {
        z: 1000
        width: 6
        height: parent.height
        anchors.right: parent.right
        cursorShape: Qt.SizeHorCursor
        onPressed: root.startSystemResize(Qt.RightEdge)
    }
    MouseArea {
        z: 1000
        height: 6
        width: parent.width
        anchors.top: parent.top
        cursorShape: Qt.SizeVerCursor
        onPressed: root.startSystemResize(Qt.TopEdge)
    }
    MouseArea {
        z: 1000
        height: 6
        width: parent.width
        anchors.bottom: parent.bottom
        cursorShape: Qt.SizeVerCursor
        onPressed: root.startSystemResize(Qt.BottomEdge)
    }
    MouseArea {
        z: 1001
        width: 14
        height: 14
        anchors.left: parent.left
        anchors.top: parent.top
        cursorShape: Qt.SizeFDiagCursor
        onPressed: root.startSystemResize(Qt.LeftEdge | Qt.TopEdge)
    }
    MouseArea {
        z: 1001
        width: 14
        height: 14
        anchors.right: parent.right
        anchors.top: parent.top
        cursorShape: Qt.SizeBDiagCursor
        onPressed: root.startSystemResize(Qt.RightEdge | Qt.TopEdge)
    }
    MouseArea {
        z: 1001
        width: 14
        height: 14
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        cursorShape: Qt.SizeBDiagCursor
        onPressed: root.startSystemResize(Qt.LeftEdge | Qt.BottomEdge)
    }
    MouseArea {
        z: 1001
        width: 14
        height: 14
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        cursorShape: Qt.SizeFDiagCursor
        onPressed: root.startSystemResize(Qt.RightEdge | Qt.BottomEdge)
    }
}
