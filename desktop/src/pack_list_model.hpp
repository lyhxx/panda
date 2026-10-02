#pragma once

#include "panda/modelstore/manifest.hpp"
#include "panda/status.hpp"

#include <QAbstractListModel>
#include <QHash>
#include <QString>
#include <QVariant>

#include <filesystem>
#include <vector>

class PackListModel final : public QAbstractListModel {
    Q_OBJECT
    Q_PROPERTY(int count READ count NOTIFY countChanged)
    Q_PROPERTY(QString voicesRoot READ voicesRoot WRITE setVoicesRoot NOTIFY voicesRootChanged)
    Q_PROPERTY(QString lastError READ lastError NOTIFY lastErrorChanged)
    Q_PROPERTY(int lastErrorCode READ lastErrorCode NOTIFY lastErrorChanged)
    Q_PROPERTY(bool lastErrorIsAlreadyInstalled READ lastErrorIsAlreadyInstalled NOTIFY lastErrorChanged)
    Q_PROPERTY(QString lastMessage READ lastMessage NOTIFY lastMessageChanged)
    Q_PROPERTY(QString filter READ filter WRITE setFilter NOTIFY filterChanged)

public:
    enum Role {
        PackIdRole = Qt::UserRole + 1,
        DisplayNameRole,
        PackVersionRole,
        EngineRole,
        KindRole,
        FolderPathRole,
        IconPathRole,
        ReferencePathRole,
    };
    Q_ENUM(Role)

    // Mirrors the core error codes so QML can react to specific failures
    // without hard-coding numbers. Values track panda::ErrorCode.
    enum PackError {
        NoError = static_cast<int>(panda::ErrorCode::none),
        AlreadyInstalled = static_cast<int>(panda::ErrorCode::already_exists),
        UnsupportedSchema = static_cast<int>(panda::ErrorCode::unsupported_schema),
        UnsupportedEngine = static_cast<int>(panda::ErrorCode::unsupported_engine),
        ChecksumMismatch = static_cast<int>(panda::ErrorCode::checksum_mismatch),
        UnsafePath = static_cast<int>(panda::ErrorCode::unsafe_path),
        InvalidManifest = static_cast<int>(panda::ErrorCode::invalid_manifest),
        PackNotFound = static_cast<int>(panda::ErrorCode::not_found),
    };
    Q_ENUM(PackError)

    explicit PackListModel(QObject* parent = nullptr);

    [[nodiscard]] int rowCount(
        const QModelIndex& parent = QModelIndex()
    ) const override;
    [[nodiscard]] QVariant data(
        const QModelIndex& index,
        int role = Qt::DisplayRole
    ) const override;
    [[nodiscard]] QHash<int, QByteArray> roleNames() const override;

    [[nodiscard]] int count() const;
    [[nodiscard]] QString voicesRoot() const;
    void setVoicesRoot(const QString& value);
    [[nodiscard]] QString lastError() const;
    [[nodiscard]] int lastErrorCode() const;
    [[nodiscard]] bool lastErrorIsAlreadyInstalled() const;
    [[nodiscard]] QString lastMessage() const;
    [[nodiscard]] QString filter() const;
    void setFilter(const QString& value);
    // Resolves a pack folder back to its human-readable name so the UI can
    // show the Chinese name instead of the pinyin folder id.
    [[nodiscard]] Q_INVOKABLE QString displayNameForFolder(const QString& folderPath) const;

    Q_INVOKABLE void refresh();
    Q_INVOKABLE bool installPack(const QString& archivePath, bool overwrite);
    Q_INVOKABLE bool removePack(const QString& packId);
    Q_INVOKABLE void clearMessages();
    // Checks the unfiltered set, so hiding a pack with the search box does not
    // make a restored selection look stale.
    [[nodiscard]] Q_INVOKABLE bool containsFolder(const QString& folderPath) const;

signals:
    void countChanged();
    void voicesRootChanged();
    void lastErrorChanged();
    void lastMessageChanged();
    void filterChanged();

private:
    struct Entry {
        panda::modelstore::Manifest manifest;
        std::filesystem::path path;
    };

    void set_error(panda::ErrorCode code, const QString& message);
    void set_message(const QString& value);
    void apply_filter();

    std::vector<Entry> all_entries_;
    std::vector<Entry> entries_;
    QString voicesRoot_;
    QString lastError_;
    int lastErrorCode_{0};
    QString lastMessage_;
    QString filter_;
};

