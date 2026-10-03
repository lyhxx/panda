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
        if (filtered.length === 0) {
            return devices
        }
        // PortAudio reports one physical endpoint once per host API, so a
        // cable installed with VB-CABLE arrives as MME, DirectSound, WASAPI
        // and WDM-KS copies of the same two endpoints -- one row each. When
        // WASAPI already carries a virtual endpoint the cable is in the list,
        // so that is the whole list: adding the other APIs' copies back is
        // what made one choice look like six.
        if (anyVirtualDevice(filtered)) {
            return filtered
        }
        // WASAPI has no virtual endpoint at all, so some other host API holds
        // the only route to other applications. Take every cable from the
        // first API that has one instead of all of them: the remaining APIs
        // are copies of those same endpoints, and one API's set is already
        // the complete set it exposes.
        let source = ""
        for (let j = 0; j < devices.length; ++j) {
            if (devices[j].isVirtual === true) {
                source = devices[j].hostApi
                break
            }
        }
        if (source.length === 0) {
            return filtered
        }
        for (let k = 0; k < devices.length; ++k) {
            if (devices[k].isVirtual === true && devices[k].hostApi === source) {
                filtered.push(devices[k])
            }
        }
        return filtered
    }

    // Whether the picker has a virtual endpoint to offer at all. When it has
    // not, no choice on screen reaches other applications, and that one line
    // is what replaces the warning box.
    function anyVirtualDevice(devices) {
        for (let i = 0; i < devices.length; ++i) {
            if (devices[i].isVirtual === true) {
                return true
            }
        }
        return false
    }

    function deviceKey(devices, deviceId) {
        if (deviceId < 0) {
            // Persist the explicit "none" choice (不输出 / 不监听) so it is not
            // replaced by a default on the next launch. When the list is empty
            // the enumeration has not finished (or failed); return empty so a
            // shutdown cannot clobber a real choice with "none".
            return devices.length > 0 ? "none" : ""
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
        // MME truncates device names at 31 characters, so the very same cable
        // is stored as both "CABLE Input (VB-Audio Virtual C" and the full
        // WASAPI spelling. Matching either way round keeps a saved choice
        // from silently falling back to the default device just because the
        // API that named it is no longer listed.
        for (let j = 0; j < devices.length; ++j) {
            const deviceName = devices[j].deviceName
            if (deviceName.startsWith(name) || name.startsWith(deviceName)) {
                return devices[j].id
            }
        }
        return -1
    }

    // The system default is an index into the full enumeration, which on this
    // machine sits on MME while the picker only lists WASAPI -- two different
    // numberings that never meet. Resolve it by device name across host APIs,
    // and when even that fails, fall back to the first endpoint the user can
    // actually hear. The old code fell through to devices[0], which after a
    // VB-CABLE install is CABLE In 16ch: monitoring then played into the very
    // line the output was already using, and the headphones stayed silent.
    function deviceNameOf(devices, id) {
        for (let i = 0; i < devices.length; ++i) {
            if (devices[i].id === id) {
                return devices[i].deviceName
            }
        }
        return ""
    }

    function firstDeviceId(devices, preferred, allDevices) {
        if (containsDevice(devices, preferred)) {
            return preferred
        }
        if (allDevices !== undefined && preferred >= 0) {
            const name = deviceNameOf(allDevices, preferred)
            if (name.length > 0) {
                for (let i = 0; i < devices.length; ++i) {
                    if (devices[i].deviceName === name) {
                        return devices[i].id
                    }
                }
            }
        }
        for (let j = 0; j < devices.length; ++j) {
            if (devices[j].isVirtual !== true) {
                return devices[j].id
            }
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

    // ---- Selection -------------------------------------------------------
    // The library can shrink under our feet: a folder deleted in the file
    // manager leaves selectedPack pointing at nothing, and the next start
    // fails on a pack that is no longer there. Hand the selection back to a
    // pack that still exists -- the first one while any remain, an empty
    // library clears it. The model is passed in like every other dependency
    // here: no context property reaches into this singleton.
    function reconcilePackSelection(packs) {
        if (packs.containsFolder(selectedPack)) {
            return
        }
        selectedPack = packs.firstFolder()
    }
}
