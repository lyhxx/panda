import QtQuick

// Level meter drawn as a row of ticks that light up with the level, matching
// the reference settings UI.
Row {
    id: root

    property real value: 0          // 0..1
    property bool clipped: false
    property bool stretch: false
    property int segments: stretch
        ? Math.max(8, Math.floor((width + spacing) / (tickWidth + spacing)))
        : 28
    property int tickWidth: 4
    property int tickHeight: 14

    spacing: 3

    Repeater {
        model: root.segments

        delegate: Rectangle {
            required property int index

            width: root.tickWidth
            height: root.tickHeight
            radius: 1.5

            readonly property bool lit: (index + 1) / root.segments
                                         <= Math.max(0, Math.min(1, root.value))

            color: !lit
                   ? (Theme.dark ? "#33FFFFFF" : "#22000000")
                   : (root.clipped
                      ? Theme.danger
                      : (index >= root.segments * 0.86 ? Theme.warning : Theme.accent))

            Behavior on color {
                ColorAnimation { duration: Theme.durFast }
            }
        }
    }
}
