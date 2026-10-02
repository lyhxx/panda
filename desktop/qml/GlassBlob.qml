import QtQuick
import QtQuick.Shapes

// A soft radial light blob. Several of these behind the UI give the frosted
// panels something colourful to show through, which is what sells the glass.
Item {
    id: root

    property color tint: "#00000000"
    property real cx: 0.5
    property real cy: 0.5
    property real radius: 0.5

    readonly property real centerX: width * cx
    readonly property real centerY: height * cy
    readonly property real coreRadius: Math.max(1, Math.min(width, height) * radius)

    Shape {
        anchors.fill: parent

        ShapePath {
            strokeColor: "transparent"
            fillGradient: RadialGradient {
                centerX: root.centerX
                centerY: root.centerY
                centerRadius: root.coreRadius
                focalX: root.centerX
                focalY: root.centerY
                focalRadius: 0

                GradientStop {
                    position: 0.0
                    color: root.tint
                }
                GradientStop {
                    position: 0.5
                    color: Qt.rgba(
                        root.tint.r, root.tint.g, root.tint.b, root.tint.a * 0.5
                    )
                }
                GradientStop {
                    position: 1.0
                    color: "#00000000"
                }
            }

            startX: root.centerX + root.coreRadius
            startY: root.centerY
            PathAngleArc {
                centerX: root.centerX
                centerY: root.centerY
                radiusX: root.coreRadius
                radiusY: root.coreRadius
                startAngle: 0
                sweepAngle: 360
            }
        }
    }
}
