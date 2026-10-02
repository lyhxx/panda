import QtQuick
import QtQuick.Controls

// ScrollView with the themed scrollbar and a transparent background.
ScrollView {
    id: control

    clip: true
    background: null
    ScrollBar.vertical: AppScrollBar { }
    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
}
