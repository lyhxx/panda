import QtQuick
import QtQuick.Shapes

// Large pill switch for the primary action, modelled on the reference control
// bar. When off the handle sits on the left and covers the mic icon; when on
// the track turns accent and the handle slides right. While the engine is
// loading it shows a spinner and a "正在启动…" label.
Item {
    id: root

    property bool on: false
    property bool busy: false
    property string icon: "mic"
    property string onText: qsTr("关闭变声")
    property string offText: qsTr("开启变声")
    property string busyText: qsTr("正在启动…")
    property bool tooltipAbove: false
    signal toggled()

    implicitWidth: 200
    implicitHeight: 56

    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: root.on ? Theme.accent : Theme.glassStrong
        border.width: 1
        border.color: root.on ? Theme.glassHighlight : Theme.glassBorder
        Behavior on color {
            ColorAnimation { duration: Theme.durNormal }
        }
    }

    Icon {
        anchors.left: parent.left
        anchors.leftMargin: 20
        anchors.verticalCenter: parent.verticalCenter
        name: root.icon
        color: root.on ? Theme.accentText : Theme.textSecondary
        implicitWidth: 22
        implicitHeight: 22
    }

    Text {
        anchors.left: parent.left
        anchors.leftMargin: 54
        anchors.right: parent.right
        anchors.rightMargin: 56
        anchors.verticalCenter: parent.verticalCenter
        text: root.busy
              ? root.busyText
              : (root.on ? root.onText : root.offText)
        color: root.on ? Theme.accentText : Theme.textPrimary
        font.pixelSize: Theme.fontBody
        font.weight: Font.DemiBold
        font.family: Theme.fontFamily
        elide: Text.ElideRight
    }

    Rectangle {
        id: handle
        width: 44
        height: 44
        radius: height / 2
        y: (parent.height - height) / 2
        x: root.on ? parent.width - width - 6 : 6
        color: root.on ? "#FFFFFF" : (Theme.dark ? "#3A3A42" : "#FFFFFF")
        Behavior on x {
            NumberAnimation { duration: Theme.durNormal; easing.type: Theme.easing }
        }

        Row {
            anchors.centerIn: parent
            spacing: 2
            visible: !root.busy
            Repeater {
                model: 3
                delegate: Rectangle {
                    width: 3
                    height: 14
                    radius: 1.5
                    color: root.on ? Theme.accent : Theme.textSecondary
                }
            }
        }

        Shape {
            anchors.centerIn: parent
            width: 24
            height: 24
            visible: root.busy
            preferredRendererType: Shape.CurveRenderer

            transform: Rotation {
                origin.x: 12
                origin.y: 12
                angle: 0
                NumberAnimation on angle {
                    from: 0
                    to: 360
                    duration: 900
                    loops: Animation.Infinite
                    running: root.busy
                }
            }

            ShapePath {
                strokeColor: root.on ? Theme.accentText : Theme.accent
                strokeWidth: 2.6
                fillColor: "transparent"
                capStyle: ShapePath.RoundCap
                startX: 12
                startY: 3
                PathAngleArc {
                    centerX: 12
                    centerY: 12
                    radiusX: 9
                    radiusY: 9
                    startAngle: -90
                    sweepAngle: 280
                }
            }
        }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.toggled()
    }

    Tooltip { anchorItem: mouse; text: root.on ? root.onText : root.offText; above: root.tooltipAbove }
}
