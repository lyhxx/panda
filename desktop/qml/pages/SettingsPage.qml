import QtQuick
import QtQuick.Layouts

// Audio and general settings. Audio is grouped into a two-column card grid,
// each card holding a device picker, a tick level meter and a volume slider.
Item {
    id: page

    Connections {
        target: realtimeController
        function onSettingsChanged() {
            prefillSpin.value = realtimeController.prefillChunks
            backlogSpin.value = realtimeController.maxBacklogChunks
        }
    }

    AppScrollView {
        anchors.fill: parent
        contentWidth: availableWidth

        ColumnLayout {
            width: Math.min(page.width - Theme.space6 * 2, 940)
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: Theme.space4

            Item { Layout.preferredHeight: Theme.space1 }

            SegmentedControl {
                Layout.alignment: Qt.AlignHCenter
                options: [
                    { "label": qsTr("音频设置"), "value": "audio" },
                    { "label": qsTr("常规设置"), "value": "general" }
                ]
                currentValue: AppState.settingsTab
                onActivated: AppState.settingsTab = value
            }

            Rectangle {
                Layout.fillWidth: true
                visible: realtimeController.deviceError.length > 0
                implicitHeight: deviceErrorText.implicitHeight + 20
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
                        id: deviceErrorText
                        Layout.fillWidth: true
                        text: realtimeController.deviceError
                        color: Theme.danger
                        font.pixelSize: Theme.fontBody
                        font.family: Theme.fontFamily
                        wrapMode: Text.WordWrap
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                visible: realtimeController.running
                implicitHeight: runningText.implicitHeight + 18
                radius: Theme.radiusControl
                color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.12)
                border.width: 1
                border.color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.3)

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 9
                    spacing: 8
                    Icon {
                        name: "info"
                        color: Theme.accent
                        implicitWidth: 16
                        implicitHeight: 16
                        Layout.alignment: Qt.AlignTop
                    }
                    Text {
                        id: runningText
                        Layout.fillWidth: true
                        text: qsTr("变声运行中：所有改动实时生效；切换设备/降噪会短暂重开音频流，不会重载模型。")
                        color: Theme.accent
                        font.pixelSize: Theme.fontSmall
                        font.family: Theme.fontFamily
                        wrapMode: Text.WordWrap
                    }
                }
            }

            // ---- Audio ---------------------------------------------------
            GridLayout {
                Layout.fillWidth: true
                visible: AppState.settingsTab === "audio"
                columns: 2
                columnSpacing: Theme.space4
                rowSpacing: Theme.space4

                // Microphone
                AppCard {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop

                    SectionTitle {
                        icon: "mic"
                        title: qsTr("输入设备（麦克风）选择")
                        subtitle: qsTr("选择实体麦克风，用于采集你的原声。")
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

                    Item { Layout.preferredHeight: Theme.space1 }

                    Text {
                        text: qsTr("输入设备（麦克风）音量")
                        color: Theme.textPrimary
                        font.pixelSize: Theme.fontBody
                        font.weight: Font.DemiBold
                        font.family: Theme.fontFamily
                    }
                    Text {
                        text: qsTr("数值越大越响；约 67 表示原始音量，100 为最大。")
                        color: Theme.textTertiary
                        font.pixelSize: Theme.fontSmall
                        font.family: Theme.fontFamily
                    }
                    VolumeSlider {
                        Layout.fillWidth: true
                        gainDb: realtimeController.inputGainDb
                        onGainMoved: realtimeController.inputGainDb = db
                    }
                }

                // Monitor
                AppCard {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop

                    SectionTitle {
                        icon: "headphones"
                        title: qsTr("监听设备（耳机）选择")
                        subtitle: qsTr("选择耳机，通过耳返监听自己的变声效果。")
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space2
                        AppComboBox {
                            Layout.fillWidth: true
                            model: [{ "id": -1, "label": qsTr("不监听") }].concat(
                                AppState.filteredDevices(realtimeController.outputDevices)
                            )
                            textRole: "label"
                            valueRole: "id"
                            desiredValue: AppState.selectedMonitorDevice
                            onActivated: AppState.selectedMonitorDevice = currentValue
                        }
                        AppIconButton {
                            iconName: "refresh"
                            iconSize: 16
                            size: 36
                            tooltip: qsTr("刷新设备")
                            onClicked: realtimeController.refreshDevices()
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        text: qsTr("选好设备即开启监听，选「不监听」即关闭；监听在开启变声后生效。建议用耳机，避免啸叫。")
                        color: Theme.textTertiary
                        font.pixelSize: Theme.fontSmall
                        font.family: Theme.fontFamily
                        wrapMode: Text.WordWrap
                    }

                    TickMeter {
                        Layout.fillWidth: true
                        stretch: true
                        value: Math.min(realtimeController.outputPeak, 1)
                        clipped: realtimeController.outputClipped
                    }

                    Item { Layout.preferredHeight: Theme.space1 }

                    Text {
                        text: qsTr("监听设备（耳机）音量")
                        color: Theme.textPrimary
                        font.pixelSize: Theme.fontBody
                        font.weight: Font.DemiBold
                        font.family: Theme.fontFamily
                    }
                    Text {
                        text: qsTr("只影响耳机监听，不影响给其它软件的输出。")
                        color: Theme.textTertiary
                        font.pixelSize: Theme.fontSmall
                        font.family: Theme.fontFamily
                    }
                    VolumeSlider {
                        Layout.fillWidth: true
                        gainDb: realtimeController.monitorGainDb
                        onGainMoved: realtimeController.monitorGainDb = db
                    }
                }

                // Output
                AppCard {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop

                    SectionTitle {
                        icon: "volume"
                        title: qsTr("变声输出（给其它软件）")
                        subtitle: qsTr("选虚拟声卡的写入端，Discord、游戏或 OBS 才能听到。")
                    }

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

                    Rectangle {
                        Layout.fillWidth: true
                        visible: AppState.selectedOutputDevice >= 0
                                 && !AppState.deviceIsVirtual(
                                     realtimeController.outputDevices,
                                     AppState.selectedOutputDevice
                                 )
                        implicitHeight: outputWarning.implicitHeight + 18
                        radius: Theme.radiusControl
                        color: Qt.rgba(Theme.warning.r, Theme.warning.g, Theme.warning.b, 0.12)
                        border.width: 1
                        border.color: Qt.rgba(Theme.warning.r, Theme.warning.g, Theme.warning.b, 0.3)

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 9
                            spacing: 8
                            Icon {
                                name: "alert"
                                color: Theme.warning
                                implicitWidth: 16
                                implicitHeight: 16
                                Layout.alignment: Qt.AlignTop
                            }
                            Text {
                                id: outputWarning
                                Layout.fillWidth: true
                                text: qsTr("当前输出不是虚拟声卡，其它软件听不到；仅适合本机试听。")
                                color: Theme.warning
                                font.pixelSize: Theme.fontSmall
                                font.family: Theme.fontFamily
                                wrapMode: Text.WordWrap
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space3

                        AppButton {
                            text: realtimeController.checkingRoute
                                  ? qsTr("检查中…")
                                  : qsTr("检查虚拟声卡路由")
                            iconName: "route"
                            enabled: !realtimeController.checkingRoute
                            onClicked: realtimeController.checkRoute()
                        }
                        Text {
                            Layout.fillWidth: true
                            text: realtimeController.routeReport
                            color: Theme.textSecondary
                            font.pixelSize: Theme.fontSmall
                            font.family: Theme.fontFamily
                            wrapMode: Text.WordWrap
                        }
                    }

                    Item { Layout.preferredHeight: Theme.space1 }

                    Text {
                        text: qsTr("输出音量")
                        color: Theme.textPrimary
                        font.pixelSize: Theme.fontBody
                        font.weight: Font.DemiBold
                        font.family: Theme.fontFamily
                    }
                    Text {
                        text: qsTr("软限幅会保证输出不削顶。")
                        color: Theme.textTertiary
                        font.pixelSize: Theme.fontSmall
                        font.family: Theme.fontFamily
                    }
                    VolumeSlider {
                        Layout.fillWidth: true
                        gainDb: realtimeController.outputGainDb
                        onGainMoved: realtimeController.outputGainDb = db
                    }
                }

                // Sound processing
                AppCard {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop

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
            }

            // ---- General -------------------------------------------------
            ColumnLayout {
                Layout.fillWidth: true
                visible: AppState.settingsTab === "general"
                spacing: Theme.space4

                AppCard {
                    Layout.fillWidth: true

                    SectionTitle {
                        icon: "monitor"
                        title: qsTr("外观")
                        subtitle: qsTr("选择界面主题；「跟随系统」会随 Windows 设置切换。")
                    }

                    SegmentedControl {
                        Layout.alignment: Qt.AlignLeft
                        options: [
                            { "value": "system", "icon": "monitor", "label": qsTr("跟随系统") },
                            { "value": "light", "icon": "sun", "label": qsTr("浅色") },
                            { "value": "dark", "icon": "moon", "label": qsTr("深色") }
                        ]
                        currentValue: themeManager.mode
                        onActivated: themeManager.mode = value
                    }
                }

                AppCard {
                    Layout.fillWidth: true

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

                    SectionTitle {
                        icon: "info"
                        title: qsTr("诊断")
                        subtitle: qsTr("下溢和丢帧只在真的发生时出现；日志用于排查无声问题。")
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space2
                        visible: realtimeController.hasStats

                        StatusPill {
                            visible: realtimeController.starvedReads > 0
                            tone: Theme.warning
                            text: qsTr("补零读 %1").arg(realtimeController.starvedReads)
                        }
                        StatusPill {
                            visible: realtimeController.underrunFrames > 0
                            tone: Theme.warning
                            text: qsTr("下溢 %1 帧").arg(realtimeController.underrunFrames)
                        }
                        StatusPill {
                            visible: realtimeController.droppedFrames > 0
                            tone: Theme.danger
                            text: qsTr("丢帧 %1").arg(realtimeController.droppedFrames)
                        }
                        Text {
                            visible: realtimeController.starvedReads === 0
                                     && realtimeController.underrunFrames === 0
                                     && realtimeController.droppedFrames === 0
                            text: qsTr("运行正常，未出现下溢或丢帧。")
                            color: Theme.textSecondary
                            font.pixelSize: Theme.fontSmall
                            font.family: Theme.fontFamily
                        }
                        Item { Layout.fillWidth: true }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 170
                        radius: Theme.radiusControl
                        color: Theme.dark ? "#66000000" : "#99FFFFFF"
                        border.width: 1
                        border.color: Theme.glassBorder
                        clip: true

                        AppScrollView {
                            anchors.fill: parent
                            anchors.margins: 10
                            contentWidth: availableWidth

                            TextEdit {
                                readOnly: true
                                text: realtimeController.logText.length > 0
                                      ? realtimeController.logText
                                      : qsTr("（暂无日志。开启变声后这里会显示 worker 输出。）")
                                color: Theme.textSecondary
                                font.pixelSize: Theme.fontCaption
                                font.family: "Cascadia Mono, Consolas, monospace"
                                wrapMode: TextEdit.WrapAnywhere
                                selectByMouse: true
                                width: parent.width
                            }
                        }
                    }
                }

                AppCard {
                    Layout.fillWidth: true

                    SectionTitle {
                        icon: "info"
                        title: qsTr("关于")
                    }

                    Text {
                        text: productName + "（" + productNameEn + "） " + Qt.application.version
                              + qsTr(" · 开源免费、本地优先的实时变声器")
                        color: Theme.textSecondary
                        font.pixelSize: Theme.fontBody
                        font.family: Theme.fontFamily
                    }
                }
            }

            Item { Layout.preferredHeight: 32 }
        }
    }
}
