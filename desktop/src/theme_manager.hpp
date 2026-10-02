#pragma once

#include <QObject>
#include <QString>

// Owns the UI colour scheme choice.
//
// The user picks "dark", "light" or "system"; "system" follows the Windows
// setting reported by QStyleHints and reacts to it while the app is running.
// The choice is persisted so the window opens the way it was left.
class ThemeManager final : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString mode READ mode WRITE setMode NOTIFY themeChanged)
    Q_PROPERTY(bool dark READ dark NOTIFY themeChanged)
    Q_PROPERTY(QString systemScheme READ systemScheme NOTIFY themeChanged)

public:
    explicit ThemeManager(QObject* parent = nullptr);

    [[nodiscard]] QString mode() const;
    void setMode(const QString& value);
    [[nodiscard]] bool dark() const;
    [[nodiscard]] QString systemScheme() const;

signals:
    void themeChanged();

private:
    void refresh_system_scheme(bool notify);

    QString mode_{QStringLiteral("dark")};
    bool system_dark_{true};
};
