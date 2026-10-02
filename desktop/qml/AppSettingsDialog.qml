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

    function setMonitoring(on) {
        if (!on) {
            AppState.selectedMonitorDevice = -1
            return
        }
        AppState.selectedMonitorDevice = AppState.firstDeviceId(
            AppState.filteredDevices(realtimeController.outputDevices),
            realtimeController.defaultOutputDevice
        )
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

    background: Rectangle {
        radius: Theme.radiusCard
        color: Theme.dark ? "#1E1E23" : "#FFFFFF"
        border.width: 1
        border.color: Theme.cardBorder
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

            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: Theme.separator
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
                GridLayout {
                    Layout.fillWidth: true
                    visible: AppState.settingsTab === "audio"
                    columns: 2
                    columnSpacing: Theme.space4
                    rowSpacing: Theme.space4

                    // Input
                    AppCard {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignTop

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
                                currentIndex: (count, indexOfValue(AppState.selectedInputDevice))
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
                            text: qsTr("数值越大越响；约 67 表示原始音量。")
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

                    // Output
                    AppCard {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignTop

                        SectionTitle {
                            icon: "volume"
                            title: qsTr("输出")
                            subtitle: qsTr("给其它软件的声音。普通扬声器只有本机能听到。")
                        }

                        AppComboBox {
                            Layout.fillWidth: true
                            model: [{ "id": -1, "label": qsTr("不输出") }].concat(
                                AppState.filteredDevices(realtimeController.outputDevices)
                            )
                            textRole: "label"
                            valueRole: "id"
                            currentIndex: (count, indexOfValue(AppState.selectedOutputDevice))
                            onActivated: AppState.selectedOutputDevice = currentValue
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            visible: AppState.selectedOutputDevice >= 0
                                     && !dialog.deviceIsVirtual
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

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.space3

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
                                    text: qsTr("用系统默认输出（耳机）听自己的变声；开启变声后生效。")
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
                        VolumeSlider {
                            Layout.fillWidth: true
                            gainDb: realtimeController.outputGainDb
                            onGainMoved: realtimeController.outputGainDb = db
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
                            currentIndex: (count, indexOfValue(realtimeController.denoiseLevel))
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
