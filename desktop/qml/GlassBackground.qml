import QtQuick

// The window backdrop: a soft vertical gradient plus coloured light blobs.
// Everything else in the UI floats above it as frosted glass.
Item {
    id: root

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: Theme.backgroundTop }
            GradientStop { position: 0.55; color: Theme.backgroundMid }
            GradientStop { position: 1.0; color: Theme.backgroundBottom }
        }
    }

    GlassBlob {
        anchors.fill: parent
        tint: Theme.blobAccent
        cx: 0.16
        cy: 0.10
        radius: 0.66
    }

    GlassBlob {
        anchors.fill: parent
        tint: Theme.blobPurple
        cx: 0.94
        cy: 0.04
        radius: 0.58
    }

    GlassBlob {
        anchors.fill: parent
        tint: Theme.blobTeal
        cx: 0.80
        cy: 0.98
        radius: 0.62
    }
}
