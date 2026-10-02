import QtQuick
import QtQuick.Layouts

// Segmented control. Each option is { value, icon?, label?, tooltip? }.
// The active segment is an accent pill, matching the reference settings tabs.
Item {
    id: root

    property var options: []
    property string currentValue: ""
    signal activated(string value)

    implicitHeight: 40
    implicitWidth: content.implicitWidth + 8

    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: Theme.glass
        border.width: 1
        border.color: Theme.glassBorder
    }

    RowLayout {
        id: content
        anchors.centerIn: parent
        spacing: 3

        Repeater {
            model: root.options

            delegate: Item {
                id: segment
                required property var modelData

                readonly property bool selected: root.currentValue === modelData.value

                implicitWidth: segmentRow.implicitWidth + 28
                implicitHeight: 32

                Rectangle {
                    anchors.fill: parent
                    radius: height / 2
                    color: segment.selected
                           ? Theme.accent
                           : (segmentMouse.containsMouse ? Theme.hoverOverlay : "transparent")
                    border.width: segment.selected ? 1 : 0
                    border.color: Theme.glassHighlight
                    Behavior on color {
                        ColorAnimation { duration: Theme.durFast }
                    }
                }

                RowLayout {
                    id: segmentRow
                    anchors.centerIn: parent
                    spacing: 6

                    Icon {
                        visible: segment.modelData.icon !== undefined
                                 && segment.modelData.icon.length > 0
                        name: segment.modelData.icon !== undefined
                              ? segment.modelData.icon : ""
                        color: segment.selected ? Theme.accentText : Theme.textSecondary
                        Layout.preferredWidth: 15
                        Layout.preferredHeight: 15
                        Layout.alignment: Qt.AlignVCenter
                    }

                    Text {
                        visible: segment.modelData.label !== undefined
                                 && segment.modelData.label.length > 0
                        text: segment.modelData.label !== undefined
                              ? segment.modelData.label : ""
                        color: segment.selected ? Theme.accentText : Theme.textSecondary
                        font.pixelSize: Theme.fontBody
                        font.weight: segment.selected ? Font.DemiBold : Font.Normal
                        font.family: Theme.fontFamily
                        Layout.alignment: Qt.AlignVCenter
                    }
                }

                MouseArea {
                    id: segmentMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        root.currentValue = segment.modelData.value
                        root.activated(segment.modelData.value)
                    }
                }

                Tooltip {
                    anchorItem: segmentMouse
                    text: segment.modelData.tooltip !== undefined
                          ? segment.modelData.tooltip : ""
                }
            }
        }
    }
}
