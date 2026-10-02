pragma Singleton

import QtQuick

// Shared, mutable UI state that both the shell (Main.qml) and the individual
// pages need. Keeping it here avoids passing a dozen properties through every
// page and keeps the selected voice/device consistent across navigations.
QtObject {
    id: state

    property string currentPage: "voices"   // kept for compatibility
    property bool settingsOpen: false
    property string settingsTab: "audio"    // "audio" | "general"

    property string selectedPack: ""
    property string selectedModel: "120ms"
    property string selectedCompute: "cpu"

    property int selectedInputDevice: -1
    property int selectedOutputDevice: -1
    property int selectedMonitorDevice: -1

    property string deviceApiFilter: "wasapi"    // "wasapi" | "all"
    property bool showAllDevices: false

    // Stable keys used to re-resolve a device after Windows renumbers them.
    property string pendingInputDeviceKey: ""
    property string pendingOutputDeviceKey: ""
    property string pendingMonitorDeviceKey: ""

    property bool mainOutputIsVirtual: false

    // ---- Device helpers --------------------------------------------------
    // Pure functions: callers pass the current device list in, so the
    // singleton never depends on a context property.
    function containsDevice(devices, deviceId) {
        for (let i = 0; i < devices.length; ++i) {
            if (devices[i].id === deviceId) {
                return true
            }
        }
        return false
    }

    function filteredDevices(devices) {
        if (deviceApiFilter === "all") {
            return devices
        }
        const filtered = []
        for (let i = 0; i < devices.length; ++i) {
            if (devices[i].hostApi === "Windows WASAPI") {
                filtered.push(devices[i])
            }
        }
        // WASAPI is the right choice in practice, but a few devices (older
        // hardware, some virtual cards) only appear under another host API.
        // Rather than hide them behind a setting, fall back automatically when
        // WASAPI exposes nothing at all.
        return filtered.length > 0 ? filtered : devices
    }

    function deviceKey(devices, deviceId) {
        if (deviceId < 0) {
            // Persist the explicit "none" choice (不输出 / 不监听) so it is not
            // replaced by a default on the next launch.
            return "none"
        }
        for (let i = 0; i < devices.length; ++i) {
            if (devices[i].id === deviceId) {
                return devices[i].hostApi + "|" + devices[i].deviceName
            }
        }
        return ""
    }

    function deviceIdFromKey(devices, key) {
        if (!key || key.length === 0) {
            return -1
        }
        for (let i = 0; i < devices.length; ++i) {
            if (devices[i].hostApi + "|" + devices[i].deviceName === key) {
                return devices[i].id
            }
        }
        return -1
    }

    // Resolves a saved "hostApi|deviceName" key, falling back to a device with
    // the same name under another host API. This matters because we now only
    // list WASAPI devices, while an older session may have stored an MME or
    // WDM-KS endpoint.
    function resolveDeviceId(devices, key) {
        if (!key || key.length === 0 || key === "none") {
            return -1
        }
        const exact = deviceIdFromKey(devices, key)
        if (exact >= 0) {
            return exact
        }
        const separator = key.indexOf("|")
        const name = separator >= 0 ? key.substring(separator + 1) : key
        for (let i = 0; i < devices.length; ++i) {
            if (devices[i].deviceName === name) {
                return devices[i].id
            }
        }
        return -1
    }

    function firstDeviceId(devices, preferred) {
        if (containsDevice(devices, preferred)) {
            return preferred
        }
        return devices.length > 0 ? devices[0].id : -1
    }

    function deviceIsVirtual(devices, deviceId) {
        for (let i = 0; i < devices.length; ++i) {
            if (devices[i].id === deviceId) {
                return devices[i].isVirtual === true
            }
        }
        return false
    }
}
