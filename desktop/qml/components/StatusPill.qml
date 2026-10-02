import QtQuick

// Small rounded status chip used in the transport bar and settings diagnostics.
Rectangle {
    id: root

    property string text: ""
    property color tone: Theme.textSecondary

    implicitWidth: label.implicitWidth + 18
    implicitHeight: 24
    radius: height / 2
    color: Qt.rgba(tone.r, tone.g, tone.b, Theme.dark ? 0.18 : 0.12)

    Text {
        id: label
        anchors.centerIn: parent
        text: root.text
        color: root.tone
        font.pixelSize: Theme.fontSmall
        font.family: Theme.fontFamily
    }
}
