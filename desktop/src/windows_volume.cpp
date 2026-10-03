#include "windows_volume.hpp"

#ifdef _WIN32

// clang-format off
#include <windows.h>
#include <mmdeviceapi.h>
#include <endpointvolume.h>
#include <functiondiscoverykeys_devpkey.h>
#include <propvarutil.h>
// clang-format on

#include <utility>

namespace panda::desktop {

namespace {

class ComScope {
public:
    ComScope() : result_(CoInitializeEx(nullptr, COINIT_MULTITHREADED)) {}

    ~ComScope() {
        if (SUCCEEDED(result_)) {
            CoUninitialize();
        }
    }

    ComScope(const ComScope&) = delete;
    ComScope& operator=(const ComScope&) = delete;

private:
    HRESULT result_{E_FAIL};
};

template <typename T>
void release(T*& pointer) {
    if (pointer != nullptr) {
        pointer->Release();
        pointer = nullptr;
    }
}

// Finds the active capture/render endpoint whose friendly name matches and
// hands its volume interface to `fn`. Returns false when nothing matched.
template <typename Fn>
bool with_endpoint_volume(const QString& deviceName, bool render, Fn&& fn) {
    const ComScope com;

    IMMDeviceEnumerator* enumerator = nullptr;
    if (FAILED(CoCreateInstance(
            __uuidof(MMDeviceEnumerator),
            nullptr,
            CLSCTX_ALL,
            __uuidof(IMMDeviceEnumerator),
            reinterpret_cast<void**>(&enumerator)
        ))) {
        return false;
    }

    IMMDeviceCollection* collection = nullptr;
    if (FAILED(enumerator->EnumAudioEndpoints(
            render ? eRender : eCapture,
            DEVICE_STATE_ACTIVE,
            &collection
        ))) {
        release(enumerator);
        return false;
    }

    const QString needle = deviceName.trimmed();
    bool matched = false;
    UINT count = 0;
    collection->GetCount(&count);
    for (UINT i = 0; i < count && !matched; ++i) {
        IMMDevice* device = nullptr;
        if (FAILED(collection->Item(i, &device))) {
            continue;
        }

        QString friendly;
        IPropertyStore* store = nullptr;
        if (SUCCEEDED(device->OpenPropertyStore(STGM_READ, &store))) {
            PROPVARIANT value;
            PropVariantInit(&value);
            if (SUCCEEDED(store->GetValue(PKEY_Device_FriendlyName, &value)) &&
                value.vt == VT_LPWSTR) {
                friendly = QString::fromWCharArray(value.pwszVal);
            }
            PropVariantClear(&value);
            release(store);
        }

        if (!friendly.isEmpty() &&
            QString::compare(friendly.trimmed(), needle, Qt::CaseInsensitive) ==
                0) {
            IAudioEndpointVolume* volume = nullptr;
            if (SUCCEEDED(device->Activate(
                    __uuidof(IAudioEndpointVolume),
                    CLSCTX_ALL,
                    nullptr,
                    reinterpret_cast<void**>(&volume)
                ))) {
                matched = true;
                fn(volume);
                release(volume);
            }
        }
        release(device);
    }

    release(collection);
    release(enumerator);
    return matched;
}

}  // namespace

std::optional<double> endpoint_volume(const QString& deviceName, bool render) {
    std::optional<double> result;
    with_endpoint_volume(deviceName, render, [&result](IAudioEndpointVolume* volume) {
        float scalar = 0.0F;
        if (SUCCEEDED(volume->GetMasterVolumeLevelScalar(&scalar))) {
            result = static_cast<double>(scalar);
        }
    });
    return result;
}

bool set_endpoint_volume(const QString& deviceName, bool render, double scalar) {
    const float value = static_cast<float>(scalar < 0.0 ? 0.0 : (scalar > 1.0 ? 1.0 : scalar));
    bool applied = false;
    const bool matched = with_endpoint_volume(
        deviceName,
        render,
        [value, &applied](IAudioEndpointVolume* volume) {
            applied = SUCCEEDED(
                volume->SetMasterVolumeLevelScalar(value, nullptr)
            );
        }
    );
    // "endpoint found" is not "volume changed": a refused set must not be
    // reported to the slider as success.
    return matched && applied;
}

}  // namespace panda::desktop

#else

namespace panda::desktop {

std::optional<double> endpoint_volume(const QString&, bool) {
    return std::nullopt;
}

bool set_endpoint_volume(const QString&, bool, double) {
    return false;
}

}  // namespace panda::desktop

#endif
