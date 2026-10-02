import QtQuick
import QtQuick.Layouts

// Frosted-glass surface used for every grouped block. Children are laid out in
// a padded column, so pages only provide content.
Rectangle {
    id: card

    default property alias contentData: content.data

    property int padding: Theme.space5
    property color surface: Theme.glass

    color: surface
    radius: Theme.radiusCard
    border.width: 1
    border.color: Theme.glassBorder

    implicitWidth: content.implicitWidth + padding * 2
    implicitHeight: content.implicitHeight + padding * 2

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

    ColumnLayout {
        id: content
        anchors.fill: parent
        anchors.margins: card.padding
        spacing: Theme.space3
    }
}
