import QtQuick
import QtQuick.Controls

// Fully custom combo box: themed field plus a popup list with hover highlight
// and a check mark on the current entry. It keeps the standard ComboBox API
// (textRole / valueRole / indexOfValue / currentValue / activated) used by the
// pages, so only the visuals are replaced.
ComboBox {
    id: control

    // The value to display, re-resolved whenever it or the model changes.
    // ComboBox writes currentIndex itself when the model is (re)assigned, which
    // breaks a plain currentIndex binding; syncing explicitly avoids a combo
    // that silently stops following the state.
    property var desiredValue

    function syncCurrentIndex() {
        if (desiredValue === undefined || desiredValue === null) {
            return
        }
        const index = indexOfValue(desiredValue)
        if (index >= 0 && index !== currentIndex) {
            currentIndex = index
        }
    }

    onDesiredValueChanged: syncCurrentIndex()
    onCountChanged: syncCurrentIndex()
    Component.onCompleted: syncCurrentIndex()

    font.pixelSize: Theme.fontBody
    font.family: Theme.fontFamily
    implicitHeight: 36
    implicitWidth: 200
    padding: 0
    hoverEnabled: true

    background: Rectangle {
        radius: Theme.radiusControl
        color: !control.enabled
               ? Theme.controlDisabled
               : (control.hovered && !control.popup.visible ? Theme.controlHover : Theme.control)
        border.width: 1
        border.color: control.activeFocus || control.popup.visible ? Theme.accent : Theme.controlBorder
        Behavior on color {
            ColorAnimation { duration: Theme.durFast }
        }
        Behavior on border.color {
            ColorAnimation { duration: Theme.durFast }
        }
    }

    contentItem: Text {
        leftPadding: 12
        rightPadding: 32
        text: control.displayText
        color: control.enabled ? Theme.textPrimary : Theme.textDisabled
        font: control.font
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    indicator: Icon {
        x: control.width - width - 11
        y: (control.height - height) / 2
        name: "chevron"
        color: control.enabled ? Theme.textSecondary : Theme.textDisabled
        implicitWidth: 15
        implicitHeight: 15
        rotation: control.popup.visible ? 180 : 0
        Behavior on rotation {
            NumberAnimation { duration: Theme.durFast }
        }
    }

    delegate: ItemDelegate {
        id: entry
        required property int index
        required property var model

        width: control.width
        height: 34
        padding: 0
        highlighted: control.highlightedIndex === index

        contentItem: Text {
            leftPadding: 12
            rightPadding: 30
            text: control.textAt(entry.index)
            color: Theme.textPrimary
            font.pixelSize: Theme.fontBody
            font.family: Theme.fontFamily
            font.weight: control.currentIndex === entry.index ? Font.DemiBold : Font.Normal
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }

        background: Rectangle {
            radius: Theme.radiusSmall
            color: entry.highlighted ? Theme.hoverOverlay : "transparent"
        }

        Icon {
            anchors.right: parent.right
            anchors.rightMargin: 11
            anchors.verticalCenter: parent.verticalCenter
            name: "check"
            visible: control.currentIndex === entry.index
            color: Theme.accent
            implicitWidth: 14
            implicitHeight: 14
        }
    }

    popup: Popup {
        y: control.height + 6
        width: control.width
        implicitHeight: Math.min(contentItem.implicitHeight + 10, 320)
        padding: 5
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            radius: Theme.radiusControl
            color: Theme.dark ? "#2A2A31" : "#FFFFFF"
            border.width: 1
            border.color: Theme.cardBorder
        }

        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: AppScrollBar { }
        }

        enter: Transition {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.durFast }
        }
        exit: Transition {
            NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.durFast }
        }
    }
}
