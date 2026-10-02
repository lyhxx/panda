#include "theme_manager.hpp"

#include <QGuiApplication>
#include <QSettings>
#include <QStyleHints>

namespace {

constexpr auto kModeDark = "dark";
constexpr auto kModeLight = "light";
constexpr auto kModeSystem = "system";

bool is_valid_mode(const QString& value) {
    return value == QLatin1String(kModeDark) ||
           value == QLatin1String(kModeLight) ||
           value == QLatin1String(kModeSystem);
}

}  // namespace

ThemeManager::ThemeManager(QObject* parent)
    : QObject(parent) {
    QSettings settings;
    const auto stored = settings.value(QStringLiteral("ui/theme_mode")).toString();
    if (is_valid_mode(stored)) {
        mode_ = stored;
    }

    refresh_system_scheme(false);

    if (auto* hints = QGuiApplication::styleHints()) {
        connect(
            hints,
            &QStyleHints::colorSchemeChanged,
            this,
            [this] { refresh_system_scheme(true); }
        );
    }
}

QString ThemeManager::mode() const {
    return mode_;
}

void ThemeManager::setMode(const QString& value) {
    if (!is_valid_mode(value) || mode_ == value) {
        return;
    }
    mode_ = value;
    QSettings settings;
    settings.setValue(QStringLiteral("ui/theme_mode"), mode_);
    emit themeChanged();
}

bool ThemeManager::dark() const {
    if (mode_ == QLatin1String(kModeDark)) {
        return true;
    }
    if (mode_ == QLatin1String(kModeLight)) {
        return false;
    }
    return system_dark_;
}

QString ThemeManager::systemScheme() const {
    return system_dark_ ? QStringLiteral("dark") : QStringLiteral("light");
}

void ThemeManager::refresh_system_scheme(bool notify) {
    bool dark = true;
    if (auto* hints = QGuiApplication::styleHints()) {
        dark = hints->colorScheme() != Qt::ColorScheme::Light;
    }
    if (dark == system_dark_) {
        return;
    }
    system_dark_ = dark;
    if (notify && mode_ == QLatin1String(kModeSystem)) {
        emit themeChanged();
    }
}
