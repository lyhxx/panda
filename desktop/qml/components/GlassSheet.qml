import QtQuick

// The surface every floating panel is cut from: the window's own gradient
// with three of its light blobs, finished with the glass border and the top
// edge highlight. Settings, confirmations and dropdowns all use it, so a
// popup opens as a piece of the same frosted glass instead of a flat plate
// that belongs to a different application.
Rectangle {
    id: sheet

    // The largest circle around (cx, cy) that still fits the panel, expressed
    // the way GlassBlob wants it (a fraction of the short side). Popups do not
    // clip their background, so containment is what keeps the light from
    // spilling past the rounded corners.
    function fitRadius(cx, cy) {
        var dx = Math.min(cx, 1 - cx) * width
        var dy = Math.min(cy, 1 - cy) * height
        return Math.min(dx, dy) / Math.min(width, height)
    }

    gradient: Gradient {
        GradientStop { position: 0.0; color: Theme.sheetTop }
        GradientStop { position: 0.55; color: Theme.sheetMid }
        GradientStop { position: 1.0; color: Theme.sheetBottom }
    }

    // The window's lights, in the window's arrangement: blue top-left, purple
    // top-right, teal along the bottom. They sit in the margins and the header
    // where the sheet is bare, and show through the translucent cards between.
    GlassBlob {
        anchors.fill: parent
        tint: Theme.blobAccent
        cx: 0.26
        cy: 0.30
        radius: sheet.fitRadius(cx, cy)
    }

    GlassBlob {
        anchors.fill: parent
        tint: Theme.blobPurple
        cx: 0.74
        cy: 0.28
        radius: sheet.fitRadius(cx, cy)
    }

    GlassBlob {
        anchors.fill: parent
        tint: Theme.blobTeal
        cx: 0.55
        cy: 0.72
        radius: sheet.fitRadius(cx, cy)
    }

    // Lit top edge, the way the frosted panels on the page catch the light.
    Rectangle {
        anchors.fill: parent
        radius: parent.radius
        gradient: Gradient {
            GradientStop { position: 0.0; color: Theme.sheetSheen }
            GradientStop { position: 0.45; color: "#00FFFFFF" }
        }
    }

    Rectangle {
        anchors.fill: parent
        radius: parent.radius
        color: "transparent"
        border.width: 1
        border.color: Theme.glassBorder
    }

    // Glass edge highlight along the flat top edge.
    Rectangle {
        anchors.top: parent.top
        anchors.topMargin: 1
        anchors.left: parent.left
        anchors.leftMargin: 14
        anchors.right: parent.right
        anchors.rightMargin: 14
        height: 1
        color: Theme.glassHighlight
        opacity: 0.7
    }
}
