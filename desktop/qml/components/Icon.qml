import QtQuick
import QtQuick.Shapes

// A small, dependency-free vector icon set drawn with Shape/PathSvg.
//
// Icons are defined on a 24x24 grid and tinted through `color`, so a single
// component serves both themes. `filled` fills the path as well as stroking it
// (used for the play/stop glyphs).
Item {
    id: root

    property string name: "check"
    property color color: "#FFFFFF"
    property real strokeWidth: 1.7
    property bool filled: name === "play" || name === "stop"

    implicitWidth: 18
    implicitHeight: 18

    readonly property string path: {
        switch (name) {
        case "waveform": return "M22 12h-4l-3 9L9 3l-3 9H2"
        case "sliders": return "M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"
        case "gear": return "M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"
        case "play": return "M7 4.5l12 7.5-12 7.5z"
        case "stop": return "M6.5 6.5h11v11h-11z"
        case "star": return "M12 2.6l2.9 5.88 6.49.94-4.7 4.58 1.11 6.46L12 17.4l-5.8 3.06 1.11-6.46-4.7-4.58 6.49-.94L12 2.6z"
        case "trash": return "M3.5 6h17M9.5 6V4.3A1.3 1.3 0 0 1 10.8 3h2.4a1.3 1.3 0 0 1 1.3 1.3V6M18.5 6v13.2A1.8 1.8 0 0 1 16.7 21H7.3a1.8 1.8 0 0 1-1.8-1.8V6M10 10.5v6M14 10.5v6"
        case "plus": return "M12 5v14M5 12h14"
        case "refresh": return "M21 4v6h-6M3 20v-6h6M3.6 9a8.5 8.5 0 0 1 14.2-3.2L21 8M3 16l3.2 2.2A8.5 8.5 0 0 0 20.4 15"
        case "search": return "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.35-4.35"
        case "chevron": return "M6 9l6 6 6-6"
        case "chevron-up": return "M6 15l6-6 6 6"
        case "x": return "M18 6L6 18M6 6l12 12"
        case "minus": return "M5 12h14"
        case "sun": return "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"
        case "moon": return "M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"
        case "monitor": return "M4 3h16a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1zM8 21h8M12 17v4"
        case "mic": return "M12 1.5a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0v-7a3 3 0 0 0-3-3zM19 10.5v1a7 7 0 0 1-14 0v-1M12 18.5v4M8.5 22.5h7"
        case "headphones": return "M3 18v-6a9 9 0 0 1 18 0v6M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3zM3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z"
        case "volume": return "M11 5L6 9H2v6h4l5 4V5zM19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"
        case "route": return "M17 1l4 4-4 4M3 11V9a4 4 0 0 1 4-4h14M7 23l-4-4 4-4M21 13v2a4 4 0 0 1-4 4H3"
        case "check": return "M20 6L9 17l-5-5"
        case "alert": return "M12 9.5v4M12 17.2h.01M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"
        case "info": return "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 16.5v-5M12 8h.01"
        case "power": return "M18.36 6.64a9 9 0 1 1-12.73 0M12 2v10"
        default: return ""
        }
    }

    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        transform: Scale {
            origin.x: 0
            origin.y: 0
            xScale: root.width / 24.0
            yScale: root.height / 24.0
        }
        ShapePath {
            strokeColor: root.color
            strokeWidth: root.strokeWidth * 24.0 / Math.max(1, Math.min(root.width, root.height))
            fillColor: root.filled ? root.color : "transparent"
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            PathSvg { path: root.path }
        }
    }
}
