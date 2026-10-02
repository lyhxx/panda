#include "pack_list_model.hpp"

#include "panda/modelstore/installer.hpp"

#include <QByteArray>
#include <QDir>
#include <QModelIndex>

#include <algorithm>
#include <utility>

namespace {

QString from_utf8(const std::string& value) {
    return QString::fromUtf8(value.data(), static_cast<int>(value.size()));
}

QString describe_error(const panda::Status& status) {
    switch (status.code) {
        case panda::ErrorCode::already_exists:
            return QObject::tr("这个音色包已经安装过了。");
        case panda::ErrorCode::unsupported_schema:
            return QObject::tr(
                "音色包的 schema_version 与已安装版本不一致，不能直接覆盖；"
                "请先删除旧包，或使用迁移工具。"
            );
        case panda::ErrorCode::unsupported_engine:
            return QObject::tr("不支持这个音色包使用的引擎。");
        case panda::ErrorCode::checksum_mismatch:
            return QObject::tr("音色包校验失败，文件可能已损坏或被修改。");
        case panda::ErrorCode::unsafe_path:
            return QObject::tr("音色包内部包含不安全的路径，已拒绝安装。");
        case panda::ErrorCode::invalid_manifest:
            return QObject::tr("音色包的 manifest.json 无效。");
        case panda::ErrorCode::invalid_archive:
            return QObject::tr("无法解压这个文件，请确认它是有效的音色包 ZIP。");
        case panda::ErrorCode::not_found:
            return QObject::tr("音色包不存在。");
        case panda::ErrorCode::io_error:
            return QObject::tr("读写出错：%1").arg(from_utf8(status.message));
        default:
            return from_utf8(status.message);
    }
}

}  // namespace

PackListModel::PackListModel(QObject* parent)
    : QAbstractListModel(parent) {}

int PackListModel::rowCount(const QModelIndex& parent) const {
    if (parent.isValid()) {
        return 0;
    }
    return static_cast<int>(entries_.size());
}

QVariant PackListModel::data(const QModelIndex& index, int role) const {
    if (!index.isValid() || index.row() < 0 ||
        index.row() >= static_cast<int>(entries_.size())) {
        return {};
    }

    const auto& entry = entries_[static_cast<std::size_t>(index.row())];
    switch (role) {
        case PackIdRole:
            return from_utf8(entry.manifest.id);
        case DisplayNameRole:
            return from_utf8(entry.manifest.name);
        case PackVersionRole:
            return from_utf8(entry.manifest.version);
        case EngineRole:
            return from_utf8(entry.manifest.engine);
        case KindRole:
            return from_utf8(entry.manifest.kind);
        case FolderPathRole:
            return QString::fromStdWString(entry.path.wstring());
        case IconPathRole: {
            if (entry.manifest.icon.empty()) {
                return {};
            }
            const auto icon = entry.path / std::filesystem::path(entry.manifest.icon);
            std::error_code error;
            if (!std::filesystem::is_regular_file(icon, error)) {
                return {};
            }
            return QString::fromStdWString(icon.wstring());
        }
        case ReferencePathRole: {
            const auto preferred =
                entry.path / "reference" / "reference.wav";
            std::error_code error;
            if (std::filesystem::is_regular_file(preferred, error)) {
                return QString::fromStdWString(preferred.wstring());
            }
            const auto directory = entry.path / "reference";
            if (std::filesystem::is_directory(directory, error)) {
                for (const auto& item :
                     std::filesystem::directory_iterator(directory, error)) {
                    if (item.is_regular_file() &&
                        item.path().extension() == ".wav") {
                        return QString::fromStdWString(item.path().wstring());
                    }
                }
            }
            return {};
        }
        default:
            return {};
    }
}

QHash<int, QByteArray> PackListModel::roleNames() const {
    return {
        {PackIdRole, "packId"},
        {DisplayNameRole, "displayName"},
        {PackVersionRole, "packVersion"},
        {EngineRole, "engine"},
        {KindRole, "kind"},
        {FolderPathRole, "folderPath"},
        {IconPathRole, "iconPath"},
        {ReferencePathRole, "referencePath"},
    };
}

int PackListModel::count() const {
    return static_cast<int>(entries_.size());
}

QString PackListModel::voicesRoot() const {
    return voicesRoot_;
}

void PackListModel::setVoicesRoot(const QString& value) {
    if (voicesRoot_ == value) {
        return;
    }
    voicesRoot_ = value;
    emit voicesRootChanged();
}

QString PackListModel::lastError() const {
    return lastError_;
}

int PackListModel::lastErrorCode() const {
    return lastErrorCode_;
}

bool PackListModel::lastErrorIsAlreadyInstalled() const {
    return lastErrorCode_ == static_cast<int>(panda::ErrorCode::already_exists);
}

QString PackListModel::lastMessage() const {
    return lastMessage_;
}

void PackListModel::set_error(panda::ErrorCode code, const QString& message) {
    lastErrorCode_ = static_cast<int>(code);
    lastError_ = message;
    emit lastErrorChanged();
}

void PackListModel::set_message(const QString& value) {
    if (lastMessage_ == value) {
        return;
    }
    lastMessage_ = value;
    emit lastMessageChanged();
}

void PackListModel::clearMessages() {
    set_message(QString());
    set_error(panda::ErrorCode::none, QString());
}

bool PackListModel::containsFolder(const QString& folderPath) const {
    if (folderPath.isEmpty()) {
        return false;
    }
    return std::any_of(
        all_entries_.begin(),
        all_entries_.end(),
        [&folderPath](const Entry& entry) {
            return QString::fromStdWString(entry.path.wstring()) == folderPath;
        }
    );
}

void PackListModel::refresh() {
    std::vector<panda::modelstore::Manifest> manifests;
    const auto status = panda::modelstore::scan_voice_packs(
        std::filesystem::path(voicesRoot_.toStdWString()),
        manifests
    );

    all_entries_.clear();
    if (status.ok()) {
        all_entries_.reserve(manifests.size());
        for (auto& manifest : manifests) {
            const auto id = from_utf8(manifest.id).toStdWString();
            all_entries_.push_back(Entry{
                std::move(manifest),
                std::filesystem::path(voicesRoot_.toStdWString()) / id,
            });
        }
    }

    apply_filter();

    // Report outside the model reset so views see errors after the new rows.
    if (status.ok()) {
        set_error(panda::ErrorCode::none, QString());
    } else {
        set_error(status.code, describe_error(status));
    }
}

QString PackListModel::filter() const {
    return filter_;
}

void PackListModel::setFilter(const QString& value) {
    if (filter_ == value) {
        return;
    }
    filter_ = value;
    apply_filter();
    emit filterChanged();
}

QString PackListModel::displayNameForFolder(const QString& folderPath) const {
    if (folderPath.isEmpty()) {
        return {};
    }
    const QString needle = QString(folderPath).replace(u'\\', u'/');
    for (const auto& entry : all_entries_) {
        const QString candidate =
            QString::fromStdWString(entry.path.wstring()).replace(u'\\', u'/');
        if (QString::compare(candidate, needle, Qt::CaseInsensitive) == 0) {
            return from_utf8(entry.manifest.name);
        }
    }
    return {};
}

void PackListModel::apply_filter() {
    const auto needle = filter_.trimmed();

    beginResetModel();
    entries_.clear();
    entries_.reserve(all_entries_.size());
    for (const auto& entry : all_entries_) {
        const auto id = from_utf8(entry.manifest.id);
        if (needle.isEmpty()) {
            entries_.push_back(entry);
            continue;
        }

        const auto name = from_utf8(entry.manifest.name);
        if (id.contains(needle, Qt::CaseInsensitive) ||
            name.contains(needle, Qt::CaseInsensitive)) {
            entries_.push_back(entry);
        }
    }

    const auto compare_name = [](const Entry& left, const Entry& right) {
        const auto left_name = from_utf8(left.manifest.name);
        const auto right_name = from_utf8(right.manifest.name);
        const auto by_name = QString::compare(
            left_name,
            right_name,
            Qt::CaseInsensitive
        );
        if (by_name != 0) {
            return by_name < 0;
        }
        return QString::compare(
            from_utf8(left.manifest.id),
            from_utf8(right.manifest.id),
            Qt::CaseInsensitive
        ) < 0;
    };
    std::sort(entries_.begin(), entries_.end(), compare_name);
    endResetModel();

    emit countChanged();
}

bool PackListModel::installPack(const QString& archivePath, bool overwrite) {
    if (voicesRoot_.isEmpty()) {
        set_error(panda::ErrorCode::invalid_argument, tr("音色库目录未设置。"));
        return false;
    }

    panda::modelstore::InstallOptions options;
    options.overwrite = overwrite;
    panda::modelstore::InstallResult result;
    const auto status = panda::modelstore::install_voice_pack(
        std::filesystem::path(archivePath.toStdWString()),
        std::filesystem::path(voicesRoot_.toStdWString()),
        options,
        result
    );
    if (!status.ok()) {
        set_message(QString());
        set_error(status.code, describe_error(status));
        return false;
    }

    const auto name = from_utf8(result.manifest.name);
    refresh();
    set_message(tr("已安装：%1").arg(name));
    return true;
}

bool PackListModel::removePack(const QString& packId) {
    if (voicesRoot_.isEmpty()) {
        set_error(panda::ErrorCode::invalid_argument, tr("音色库目录未设置。"));
        return false;
    }

    const auto status = panda::modelstore::remove_voice_pack(
        std::filesystem::path(voicesRoot_.toStdWString()),
        packId.toUtf8().toStdString()
    );
    if (!status.ok()) {
        set_message(QString());
        set_error(status.code, describe_error(status));
        return false;
    }

    refresh();
    set_message(tr("已删除：%1").arg(packId));
    return true;
}

