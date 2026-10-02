#pragma once

#include <QObject>
#include <QSettings>
#include <QString>
#include <QVariantMap>

namespace panda::desktop {

// Persists the choices a user makes once and expects to keep: voice pack,
// devices, model and latency settings.
//
// Values are validated on load, so a settings file that was hand-edited, left
// over from an older build, or written by a different machine cannot put the
// application into an unusable state.
class SessionStore : public QObject {
    Q_OBJECT

public:
    explicit SessionStore(QObject* parent = nullptr);

    // Test seam: keep the settings in a specific INI file.
    explicit SessionStore(const QString& file_path, QObject* parent = nullptr);

    [[nodiscard]] Q_INVOKABLE QVariantMap load() const;
    Q_INVOKABLE void save(const QVariantMap& values) const;
    Q_INVOKABLE void clear() const;

    [[nodiscard]] static QVariantMap sanitize(const QVariantMap& values);

private:
    [[nodiscard]] QSettings make_settings() const;

    QString override_path_;
};

}  // namespace panda::desktop
