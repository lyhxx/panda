import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Settings as a modal dialog (no separate page). Audio holds input/output and
// the sound-processing toggles; general holds performance, diagnostics and
// about. Theme follows the system, so there is no appearance section.
Popup {
    id: dialog

    property bool deviceIsVirtual: AppState.selectedOutputDevice >= 0
        && AppState.deviceIsVirtual(
            realtimeController.outputDevices,
            AppState.selectedOutputDevice
        )
    // True while the picker can offer a virtual endpoint at all. When it
    // cannot, the one thing worth saying is that other applications will stay
    // silent, so that single line replaces the old warning box.
    property bool hasVirtualOutput: AppState.anyVirtualDevice(
        AppState.filteredDevices(realtimeController.outputDevices)
    )

    function setMonitoring(on) {
        if (!on) {
            AppState.selectedMonitorDevice = -1
            return
        }
        AppState.selectedMonitorDevice = AppState.firstDeviceId(
            AppState.filteredDevices(realtimeController.outputDevices),
            realtimeController.defaultOutputDevice,
            realtimeController.outputDevices
        )
    }

    // The endpoint monitoring will actually play on, resolved the same way
    // setMonitoring() resolves it so the caption never promises a device the
    // switch does not use. "Headphones" was hardcoded before, which is a lie
    // on a machine whose system default is the speakers -- or worse, once the
    // default id used to fall through onto the virtual cable itself.
    readonly property string monitorTargetName: {
        const outputs = AppState.filteredDevices(realtimeController.outputDevices)
        const id = AppState.firstDeviceId(outputs,
                                           realtimeController.defaultOutputDevice,
                                           realtimeController.outputDevices)
        const name = AppState.deviceNameOf(realtimeController.outputDevices, id)
        const cut = name.indexOf(" (")
        return cut > 0 ? name.substring(0, cut) : name
    }

    property real systemMicVolume: 80
    property real systemOutputVolume: 50

    // Mirror the Windows mixer: read the endpoint volume for the selected
    // devices so the sliders show the same numbers as 系统 > 声音.
    function refreshSystemVolumes() {
        if (AppState.selectedInputDevice >= 0) {
            const mic = realtimeController.deviceVolume(AppState.selectedInputDevice, false)
            if (mic >= 0) {
                systemMicVolume = mic * 100
            }
        }
        if (AppState.selectedOutputDevice >= 0) {
            const out = realtimeController.deviceVolume(AppState.selectedOutputDevice, true)
            if (out >= 0) {
                systemOutputVolume = out * 100
            }
        }
    }

    onOpened: refreshSystemVolumes()

    Connections {
        target: AppState
        function onSelectedInputDeviceChanged() { dialog.refreshSystemVolumes() }
        function onSelectedOutputDeviceChanged() { dialog.refreshSystemVolumes() }
    }

    modal: true
    focus: true
    visible: AppState.settingsOpen
    anchors.centerIn: Overlay.overlay
    width: Math.min(parent ? parent.width - 80 : 760, 760)
    height: Math.min(parent ? parent.height - 80 : 640, 640)
    padding: 0
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    onClosed: AppState.settingsOpen = false

    Overlay.modal: Rectangle { color: Theme.scrim }

    background: GlassSheet {
        radius: Theme.radiusCard
    }

    contentItem: ColumnLayout {
        spacing: 0

        // Header -----------------------------------------------------------
        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 58

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.space5
                anchors.rightMargin: Theme.space2
                spacing: Theme.space2

                Text {
                    text: qsTr("设置")
                    color: Theme.textPrimary
                    font.pixelSize: Theme.fontHeading
                    font.weight: Font.DemiBold
                    font.family: Theme.fontFamily
                }

                Item { Layout.fillWidth: true }

                AppIconButton {
                    iconName: "x"
                    iconSize: 16
                    size: 32
                    tooltip: qsTr("关闭")
                    onClicked: AppState.settingsOpen = false
                }
            }

            // Catches the light like a glass edge instead of ruling a hard
            // table line across the sheet.
            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                gradient: Gradient {
                    GradientStop { position: 0.0; color: "transparent" }
                    GradientStop { position: 0.5; color: Theme.glassBorder }
                    GradientStop { position: 1.0; color: "transparent" }
                }
            }
        }

        // Tabs -------------------------------------------------------------
        SegmentedControl {
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: Theme.space4
            options: [
                { "label": qsTr("音频设置"), "value": "audio" },
                { "label": qsTr("常规设置"), "value": "general" }
            ]
            currentValue: AppState.settingsTab
            onActivated: AppState.settingsTab = value
        }

        AppScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.topMargin: Theme.space4
            contentWidth: availableWidth

            ColumnLayout {
                width: parent.width - Theme.space5 * 2
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: Theme.space4

                // ---- Audio -----------------------------------------------
                ColumnLayout {
                    Layout.fillWidth: true
                    visible: AppState.settingsTab === "audio"
                    spacing: Theme.space4

                    // Input
                    AppCard {
                        Layout.fillWidth: true

                        SectionTitle {
                            icon: "mic"
                            title: qsTr("输入")
                            subtitle: qsTr("选择你的麦克风。不确定就保持默认。")
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.space2
                            AppComboBox {
                                Layout.fillWidth: true
                                model: AppState.filteredDevices(realtimeController.inputDevices)
                                textRole: "label"
                                valueRole: "id"
                                enabled: count > 0
                                desiredValue: AppState.selectedInputDevice
                                onActivated: AppState.selectedInputDevice = currentValue
                            }
                            AppIconButton {
                                iconName: "refresh"
                                iconSize: 16
                                size: 36
                                tooltip: qsTr("刷新设备")
                                onClicked: realtimeController.refreshDevices()
                            }
                        }

                        TickMeter {
                            Layout.fillWidth: true
                            stretch: true
                            value: Math.min(realtimeController.inputPeak, 1)
                            clipped: realtimeController.inputClipped
                        }

                        Text {
                            text: qsTr("麦克风音量")
                            color: Theme.textPrimary
                            font.pixelSize: Theme.fontBody
                            font.weight: Font.DemiBold
                            font.family: Theme.fontFamily
                        }
                        Text {
                            text: qsTr("直接调这个麦克风的系统音量。")
                            color: Theme.textTertiary
                            font.pixelSize: Theme.fontSmall
                            font.family: Theme.fontFamily
                        }
                        VolumeSlider {
                            Layout.fillWidth: true
                            systemVolume: true
                            gainDb: dialog.systemMicVolume
                            onGainMoved: {
                                dialog.systemMicVolume = db
                                realtimeController.setDeviceVolume(
                                    AppState.selectedInputDevice, false, db / 100
                                )
                            }
                        }
                    }

                    // Output
                    AppCard {
                        Layout.fillWidth: true

                        SectionTitle {
                            icon: "volume"
                            title: qsTr("输出")
                            subtitle: qsTr("给其它软件的声音。普通扬声器只有本机能听到。")
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.space2

                            AppComboBox {
                                Layout.fillWidth: true
                                model: [{ "id": -1, "label": qsTr("不输出") }].concat(
                                    AppState.filteredDevices(realtimeController.outputDevices)
                                )
                                textRole: "label"
                                valueRole: "id"
                                desiredValue: AppState.selectedOutputDevice
                                onActivated: AppState.selectedOutputDevice = currentValue
                            }
                            AppIconButton {
                                iconName: "refresh"
                                iconSize: 16
                                size: 36
                                tooltip: qsTr("刷新设备")
                                onClicked: realtimeController.refreshDevices()
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.space3
                            // The machine has no virtual endpoint to offer, so
                            // nothing on screen can reach other applications.
                            // Saying that is not enough on its own: the fix is
                            // one download away, so the download is here too,
                            // together with the three steps that actually make
                            // it work -- VB-CABLE's installer reports
                            // "LOADDRV: The path does not exist" (-106) when it
                            // is started without administrator rights or
                            // straight out of the zip, and no device appears
                            // until the reboot. The origin is spelled out
                            // because VB-Audio asks that any pointer to
                            // VB-CABLE names it.
                            visible: !dialog.hasVirtualOutput

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 3

                                Text {
                                    text: qsTr("未检测到虚拟声卡，其它软件听不到。")
                                    color: Theme.textTertiary
                                    font.pixelSize: Theme.fontSmall
                                    font.family: Theme.fontFamily
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                }
                                Text {
                                    text: qsTr("下载后：解压 → 右键以管理员身份运行 → 重启 → 回来点刷新")
                                    color: Theme.textSecondary
                                    font.pixelSize: Theme.fontSmall
                                    font.family: Theme.fontFamily
                                    font.weight: Font.DemiBold
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                }
                            }
                            AppButton {
                                iconName: "download"
                                text: qsTr("去 www.vb-cable.com 下载")
                                onClicked: Qt.openUrlExternally(
                                    "https://www.vb-cable.com/"
                                )
                            }
                        }

                        TickMeter {
                            Layout.fillWidth: true
                            stretch: true
                            value: Math.min(realtimeController.outputPeak, 1)
                            clipped: realtimeController.outputClipped
                        }

                        Text {
                            // Picking the cable is only half the job: the
                            // converted audio now goes to a line that another
                            // application has to read, and that application
                            // stays silent until the conversion runs. The one
                            // step that happens outside this app is named
                            // here, because nothing else on screen would ever
                            // mention it.
                            visible: dialog.deviceIsVirtual
                            text: qsTr("用法：点「开启变声」→ 对方软件的麦克风选 CABLE Output。")
                            color: Theme.textTertiary
                            font.pixelSize: Theme.fontSmall
                            font.family: Theme.fontFamily
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.space3
                            // Monitoring only makes sense when the converted
                            // voice goes somewhere you cannot hear (a virtual
                            // cable). With a local output it would just be the
                            // same device twice, so keep it out of the way.
                            visible: dialog.deviceIsVirtual

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2
                                Text {
                                    text: qsTr("监听")
                                    color: Theme.textPrimary
                                    font.pixelSize: Theme.fontBody
                                    font.family: Theme.fontFamily
                                }
                                Text {
                                    text: dialog.monitorTargetName.length > 0
                                          ? qsTr("用系统默认输出（%1）听自己的变声；开启变声后生效。").arg(dialog.monitorTargetName)
                                          : qsTr("用系统默认输出听自己的变声；开启变声后生效。")
                                    color: Theme.textTertiary
                                    font.pixelSize: Theme.fontSmall
                                    font.family: Theme.fontFamily
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                }
                            }
                            AppSwitch {
                                Layout.alignment: Qt.AlignVCenter
                                checked: AppState.selectedMonitorDevice >= 0
                                onToggled: dialog.setMonitoring(checked)
                            }
                        }

                        Text {
                            text: qsTr("输出音量")
                            color: Theme.textPrimary
                            font.pixelSize: Theme.fontBody
                            font.weight: Font.DemiBold
                            font.family: Theme.fontFamily
                        }
                        Text {
                            text: qsTr("直接调这个输出设备的系统音量。")
                            color: Theme.textTertiary
                            font.pixelSize: Theme.fontSmall
                            font.family: Theme.fontFamily
                        }
                        VolumeSlider {
                            Layout.fillWidth: true
                            systemVolume: true
                            gainDb: dialog.systemOutputVolume
                            onGainMoved: {
                                dialog.systemOutputVolume = db
                                realtimeController.setDeviceVolume(
                                    AppState.selectedOutputDevice, true, db / 100
                                )
                            }
                        }
                    }
                }

                // Sound processing (still under audio)
                AppCard {
                    Layout.fillWidth: true
                    visible: AppState.settingsTab === "audio"

                    SectionTitle {
                        icon: "waveform"
                        title: qsTr("声音处理")
                        subtitle: qsTr("默认关闭；需要时再开启。")
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space3
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Text {
                                text: qsTr("降噪")
                                color: Theme.textPrimary
                                font.pixelSize: Theme.fontBody
                                font.family: Theme.fontFamily
                            }
                            Text {
                                text: qsTr("抑制键盘、风扇等噪声；增加约 160 ms 延迟。")
                                color: Theme.textTertiary
                                font.pixelSize: Theme.fontSmall
                                font.family: Theme.fontFamily
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                        }
                        AppSwitch {
                            Layout.alignment: Qt.AlignVCenter
                            checked: realtimeController.denoise
                            onToggled: realtimeController.denoise = checked
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        visible: realtimeController.denoise
                        spacing: Theme.space3
                        Text {
                            text: qsTr("降噪强度")
                            color: Theme.textSecondary
                            font.pixelSize: Theme.fontSmall
                            font.family: Theme.fontFamily
                        }
                        AppComboBox {
                            Layout.fillWidth: true
                            model: [
                                { "label": qsTr("强"), "value": "strong" },
                                { "label": qsTr("标准"), "value": "balanced" },
                                { "label": qsTr("轻"), "value": "gentle" }
                            ]
                            textRole: "label"
                            valueRole: "value"
                            desiredValue: realtimeController.denoiseLevel
                            onActivated: realtimeController.denoiseLevel = currentValue
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space3
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Text {
                                text: qsTr("静音门")
                                color: Theme.textPrimary
                                font.pixelSize: Theme.fontBody
                                font.family: Theme.fontFamily
                            }
                            Text {
                                text: qsTr("不说话时挡掉低于阈值的背景声。")
                                color: Theme.textTertiary
                                font.pixelSize: Theme.fontSmall
                                font.family: Theme.fontFamily
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                        }
                        AppSwitch {
                            Layout.alignment: Qt.AlignVCenter
                            checked: realtimeController.noiseGateEnabled
                            onToggled: realtimeController.noiseGateEnabled = checked
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        visible: realtimeController.noiseGateEnabled
                        spacing: 2
                        Text {
                            text: qsTr("静音门阈值")
                            color: Theme.textSecondary
                            font.pixelSize: Theme.fontSmall
                            font.family: Theme.fontFamily
                        }
                        VolumeSlider {
                            Layout.fillWidth: true
                            percentage: false
                            minDb: -90
                            maxDb: -10
                            gainDb: realtimeController.noiseGateDb
                            onGainMoved: realtimeController.noiseGateDb = db
                        }
                    }
                }

                // ---- General ---------------------------------------------
                AppCard {
                    Layout.fillWidth: true
                    visible: AppState.settingsTab === "general"

                    SectionTitle {
                        icon: "gear"
                        title: qsTr("性能与延迟")
                        subtitle: qsTr("一般不用改；出现卡顿时再调。")
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space3
                        Text {
                            Layout.fillWidth: true
                            text: qsTr("预滚块数")
                            color: Theme.textPrimary
                            font.pixelSize: Theme.fontBody
                            font.family: Theme.fontFamily
                        }
                        AppSpinBox {
                            id: prefillSpin
                            Layout.preferredWidth: 132
                            from: 0
                            to: 8
                            value: realtimeController.prefillChunks
                            onValueModified: realtimeController.prefillChunks = value
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space3
                        Text {
                            Layout.fillWidth: true
                            text: qsTr("缓冲上限")
                            color: Theme.textPrimary
                            font.pixelSize: Theme.fontBody
                            font.family: Theme.fontFamily
                        }
                        AppSpinBox {
                            id: backlogSpin
                            Layout.preferredWidth: 132
                            from: 2
                            to: 32
                            value: realtimeController.maxBacklogChunks
                            onValueModified: realtimeController.maxBacklogChunks = value
                        }
                    }
                }

                AppCard {
                    Layout.fillWidth: true
                    visible: AppState.settingsTab === "general"

                    SectionTitle {
                        icon: "info"
                        title: qsTr("诊断")
                        subtitle: qsTr("下溢和丢帧只在真的发生时出现；日志用于排查无声问题。")
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space4

                        // The log is a file on disk rather than something
                        // this window renders: showing it here duplicated a
                        // viewer inside the settings and capped whatever a
                        // reader could take away from it. One button hands the
                        // file to the system's own viewer instead, which also
                        // means the whole file can be copied or sent on.
                        AppButton {
                            iconName: "file"
                            text: qsTr("打开日志文件")
                            onClicked: realtimeController.openLogFile()
                        }

                        Text {
                            Layout.fillWidth: true
                            text: realtimeController.logFilePath
                            color: Theme.textTertiary
                            font.pixelSize: Theme.fontCaption
                            font.family: "Cascadia Mono, Consolas, monospace"
                            elide: Text.ElideMiddle
                        }
                    }
                }

                AppCard {
                    Layout.fillWidth: true
                    visible: AppState.settingsTab === "general"

                    SectionTitle { icon: "info"; title: qsTr("关于") }

                    Text {
                        text: productName + "（" + productNameEn + "） " + Qt.application.version
                              + qsTr(" · 开源免费、本地优先的实时变声器")
                        color: Theme.textSecondary
                        font.pixelSize: Theme.fontBody
                        font.family: Theme.fontFamily
                    }
                }

                Item { Layout.preferredHeight: Theme.space5 }
            }
        }
    }
}
