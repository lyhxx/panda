pragma Singleton

import QtQuick

// Central design tokens for the whole application.
//
// Every colour, radius, spacing step and duration lives here so the dark and
// light themes stay in sync and no control hard-codes a value. `dark` is set
// once from ThemeManager (via Main.qml) and everything else follows.
QtObject {
    id: theme

    property bool dark: true

    // ---- Brand / accents -------------------------------------------------
    readonly property color accent: dark ? "#0A84FF" : "#007AFF"
    readonly property color accentHover: dark ? "#3D9BFF" : "#0066DC"
    readonly property color accentPressed: dark ? "#0A6FD8" : "#0056C4"
    readonly property color accentText: "#FFFFFF"
    readonly property color danger: dark ? "#FF453A" : "#E0332A"
    readonly property color dangerHover: dark ? "#FF6B61" : "#C72A22"
    readonly property color warning: dark ? "#FFD60A" : "#B25000"
    readonly property color success: dark ? "#30D158" : "#1E9E45"

    // ---- Surfaces --------------------------------------------------------
    readonly property color window: dark ? "#131316" : "#ECECF0"
    readonly property color sidebar: dark ? "#1B1B1F" : "#E4E4E9"
    readonly property color content: dark ? "#17171A" : "#F6F6F9"
    readonly property color card: dark ? "#202024" : "#FFFFFF"
    readonly property color cardHover: dark ? "#26262B" : "#FFFFFF"
    readonly property color cardBorder: dark ? "#2E2E34" : "#E2E2E7"
    readonly property color separator: dark ? "#29292F" : "#E7E7EB"
    readonly property color titleBar: dark ? "#1B1B1F" : "#EDEDF2"

    // ---- Controls --------------------------------------------------------
    readonly property color control: dark ? "#2A2A30" : "#FFFFFF"
    readonly property color controlHover: dark ? "#33333A" : "#F1F1F5"
    readonly property color controlPressed: dark ? "#3A3A42" : "#E8E8EE"
    readonly property color controlBorder: dark ? "#3B3B43" : "#D4D4DA"
    readonly property color controlDisabled: dark ? "#232328" : "#EFEFF3"

    // ---- Text ------------------------------------------------------------
    readonly property color textPrimary: dark ? "#F5F5F7" : "#1C1C1E"
    readonly property color textSecondary: dark ? "#A0A0A8" : "#6C6C72"
    readonly property color textTertiary: dark ? "#6C6C74" : "#909098"
    readonly property color textDisabled: dark ? "#55555C" : "#B0B0B6"
    readonly property color mutedText: dark ? "#8E8E96" : "#8A8A90"

    // ---- Overlays --------------------------------------------------------
    readonly property color hoverOverlay: dark ? "#1FFFFFFF" : "#0F000000"
    readonly property color pressedOverlay: dark ? "#2EFFFFFF" : "#17000000"
    readonly property color selectedOverlay: dark ? "#260A84FF" : "#1F007AFF"
    readonly property color scrim: dark ? "#A6000000" : "#59000000"
    readonly property color tooltip: dark ? "#2C2C33" : "#2C2C33"

    // ---- Liquid glass ----------------------------------------------------
    // A soft gradient backdrop with coloured light blobs gives the frosted
    // panels something to show through. Values carry their own alpha.
    readonly property color backgroundTop: dark ? "#0C0E18" : "#EAF0FA"
    readonly property color backgroundMid: dark ? "#111327" : "#F2F0FB"
    readonly property color backgroundBottom: dark ? "#090A12" : "#E9EEF8"
    readonly property color blobAccent: dark ? "#7A0A84FF" : "#3D0A84FF"
    readonly property color blobPurple: dark ? "#66BF5AF2" : "#33BF5AF2"
    readonly property color blobTeal: dark ? "#4D00C7BE" : "#2B30D158"
    readonly property color glass: dark ? "#14FFFFFF" : "#96FFFFFF"
    readonly property color glassStrong: dark ? "#22FFFFFF" : "#C2FFFFFF"
    readonly property color glassBorder: dark ? "#1FFFFFFF" : "#2E000000"
    readonly property color glassHighlight: dark ? "#33FFFFFF" : "#D9FFFFFF"
    readonly property color glassPill: dark ? "#1AFFFFFF" : "#A6FFFFFF"

    // ---- Radii -----------------------------------------------------------
    readonly property int radiusWindow: 12
    readonly property int radiusCard: 14
    readonly property int radiusControl: 9
    readonly property int radiusSmall: 7
    readonly property int radiusPill: 999

    // ---- Spacing ---------------------------------------------------------
    readonly property int space1: 4
    readonly property int space2: 8
    readonly property int space3: 12
    readonly property int space4: 16
    readonly property int space5: 20
    readonly property int space6: 24
    readonly property int space7: 32

    // ---- Typography ------------------------------------------------------
    readonly property int fontCaption: 11
    readonly property int fontSmall: 12
    readonly property int fontBody: 13
    readonly property int fontTitle: 15
    readonly property int fontHeading: 18
    readonly property int fontLargeTitle: 26

    readonly property string fontFamily: "Segoe UI Variable Text, Segoe UI, Microsoft YaHei UI"

    // ---- Motion ----------------------------------------------------------
    readonly property int durFast: 110
    readonly property int durNormal: 180
    readonly property int durSlow: 260
    readonly property int easing: Easing.OutCubic
}
