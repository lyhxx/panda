// Headless tests for the desktop voice-pack model. The QML layer cannot be
// exercised here, so these cover the model wiring: error propagation, error
// codes QML reacts to, and state reset.

#include "pack_list_model.hpp"

#include "panda/crypto/sha256.hpp"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QTemporaryDir>
#include <QTest>

#include <filesystem>

namespace {

bool write_bytes(const QString& path, const QByteArray& contents) {
    QFile file(path);
    if (!file.open(QIODevice::WriteOnly)) {
        return false;
    }
    return file.write(contents) == contents.size();
}

// Lays down a minimal pack that passes validate_pack_root: every listed file
// must exist, match its size and SHA-256, and the listing must match the
// directory contents exactly.
bool create_valid_pack(
    const QString& voicesRoot,
    const QString& id,
    const QString& name = QStringLiteral("Demo Voice")
) {
    const QDir root(voicesRoot);
    const auto packDir = id;
    if (!QDir().mkpath(root.filePath(packDir + QStringLiteral("/assets")))) {
        return false;
    }

    const auto entryPath = root.filePath(packDir + QStringLiteral("/mvc2_rt.yaml"));
    const auto assetPath = root.filePath(
        packDir + QStringLiteral("/assets/spk_emb.npy")
    );
    const auto registerPath = root.filePath(
        packDir + QStringLiteral("/assets/register.json")
    );
    if (!write_bytes(entryPath, QByteArrayLiteral("engine: meanvc2\n"))) {
        return false;
    }
    if (!write_bytes(assetPath, QByteArrayLiteral("speaker-embedding"))) {
        return false;
    }
    // A zero-shot pack must also carry the registration file.
    if (!write_bytes(
            registerPath,
            QByteArrayLiteral("{\"id\": \"demo-voice\"}\n")
        )) {
        return false;
    }

    std::string entryDigest;
    std::string assetDigest;
    std::string registerDigest;
    if (!panda::crypto::sha256_file(
            std::filesystem::path(entryPath.toStdWString()),
            entryDigest
        ).ok()) {
        return false;
    }
    if (!panda::crypto::sha256_file(
            std::filesystem::path(assetPath.toStdWString()),
            assetDigest
        ).ok()) {
        return false;
    }
    if (!panda::crypto::sha256_file(
            std::filesystem::path(registerPath.toStdWString()),
            registerDigest
        ).ok()) {
        return false;
    }

    QByteArray manifest;
    manifest += "{\n";
    manifest += "  \"schema_version\": 1,\n";
    manifest += "  \"format\": \"panda.voice-pack\",\n";
    manifest += "  \"id\": \"" + id.toUtf8() + "\",\n";
    manifest += "  \"name\": \"" + name.toUtf8() + "\",\n";
    manifest += "  \"version\": \"1.0.0\",\n";
    manifest += "  \"engine\": \"meanvc2\",\n";
    manifest += "  \"kind\": \"zero-shot\",\n";
    manifest += "  \"entry\": \"mvc2_rt.yaml\",\n";
    manifest += "  \"assets_dir\": \"assets\",\n";
    manifest += "  \"created_at\": \"2026-10-02T00:00:00Z\",\n";
    manifest += "  \"files\": [\n";
    manifest += "    {\"path\": \"mvc2_rt.yaml\", \"size\": ";
    manifest += QByteArray::number(QFileInfo(entryPath).size());
    manifest += ", \"sha256\": \"" + QByteArray::fromStdString(entryDigest);
    manifest += "\"},\n";
    manifest += "    {\"path\": \"assets/spk_emb.npy\", \"size\": ";
    manifest += QByteArray::number(QFileInfo(assetPath).size());
    manifest += ", \"sha256\": \"" + QByteArray::fromStdString(assetDigest);
    manifest += "\"},\n";
    manifest += "    {\"path\": \"assets/register.json\", \"size\": ";
    manifest += QByteArray::number(QFileInfo(registerPath).size());
    manifest += ", \"sha256\": \"" + QByteArray::fromStdString(registerDigest);
    manifest += "\"}\n";
    manifest += "  ]\n}\n";

    return write_bytes(
        root.filePath(packDir + QStringLiteral("/manifest.json")),
        manifest
    );
}

}  // namespace

class PackListModelTest : public QObject {
    Q_OBJECT

private slots:
    void empty_root_scans_to_zero();
    void missing_archive_is_reported();
    void removing_an_unknown_pack_reports_not_found();
    void removing_an_unsafe_id_is_rejected();
    void clearing_messages_resets_state();
    void refresh_lists_an_installed_pack();
    void removing_an_installed_pack_succeeds();
    void filters_by_id_and_name();
    void refresh_keeps_the_active_filter();
    void contains_folder_uses_the_unfiltered_set();
};

void PackListModelTest::empty_root_scans_to_zero() {
    QTemporaryDir temp;
    QVERIFY(temp.isValid());

    PackListModel model;
    model.setVoicesRoot(temp.path());
    model.refresh();

    QCOMPARE(model.count(), 0);
    QVERIFY(model.lastError().isEmpty());
    QVERIFY(model.lastMessage().isEmpty());
}

void PackListModelTest::missing_archive_is_reported() {
    QTemporaryDir temp;
    QVERIFY(temp.isValid());

    PackListModel model;
    model.setVoicesRoot(temp.path());

    const auto missing = QDir(temp.path()).filePath(
        QStringLiteral("nope.zip")
    );
    QVERIFY(!model.installPack(missing, false));
    QVERIFY(!model.lastError().isEmpty());
    QCOMPARE(model.count(), 0);
}

void PackListModelTest::removing_an_unknown_pack_reports_not_found() {
    QTemporaryDir temp;
    QVERIFY(temp.isValid());

    PackListModel model;
    model.setVoicesRoot(temp.path());

    QVERIFY(!model.removePack(QStringLiteral("missing-pack")));
    QCOMPARE(
        model.lastErrorCode(),
        static_cast<int>(PackListModel::PackNotFound)
    );
}

void PackListModelTest::removing_an_unsafe_id_is_rejected() {
    QTemporaryDir temp;
    QVERIFY(temp.isValid());

    PackListModel model;
    model.setVoicesRoot(temp.path());

    // Traversal attempts must never reach the filesystem.
    QVERIFY(!model.removePack(QStringLiteral("../escape")));
    QCOMPARE(
        model.lastErrorCode(),
        static_cast<int>(PackListModel::InvalidManifest)
    );
    QVERIFY(!model.removePack(QStringLiteral("a/b")));
}

void PackListModelTest::clearing_messages_resets_state() {
    QTemporaryDir temp;
    QVERIFY(temp.isValid());

    PackListModel model;
    model.setVoicesRoot(temp.path());
    QVERIFY(!model.removePack(QStringLiteral("missing-pack")));
    QVERIFY(!model.lastError().isEmpty());

    model.clearMessages();

    QVERIFY(model.lastError().isEmpty());
    QCOMPARE(
        model.lastErrorCode(),
        static_cast<int>(PackListModel::NoError)
    );
}

void PackListModelTest::refresh_lists_an_installed_pack() {
    QTemporaryDir temp;
    QVERIFY(temp.isValid());
    QVERIFY(create_valid_pack(temp.path(), QStringLiteral("demo-voice")));

    PackListModel model;
    model.setVoicesRoot(temp.path());
    model.refresh();

    QCOMPARE(model.count(), 1);
    QCOMPARE(
        model.index(0, 0).data(PackListModel::PackIdRole).toString(),
        QStringLiteral("demo-voice")
    );
    QCOMPARE(
        model.index(0, 0).data(PackListModel::DisplayNameRole).toString(),
        QStringLiteral("Demo Voice")
    );
    QVERIFY(model.lastError().isEmpty());
}

void PackListModelTest::removing_an_installed_pack_succeeds() {
    QTemporaryDir temp;
    QVERIFY(temp.isValid());
    QVERIFY(create_valid_pack(temp.path(), QStringLiteral("demo-voice")));

    PackListModel model;
    model.setVoicesRoot(temp.path());
    model.refresh();
    QCOMPARE(model.count(), 1);

    QVERIFY(model.removePack(QStringLiteral("demo-voice")));

    QCOMPARE(model.count(), 0);
    QVERIFY(!QDir(temp.path()).exists(QStringLiteral("demo-voice")));
    QVERIFY(!model.lastMessage().isEmpty());
    QVERIFY(model.lastError().isEmpty());
}

void PackListModelTest::filters_by_id_and_name() {
    QTemporaryDir temp;
    QVERIFY(temp.isValid());
    QVERIFY(create_valid_pack(temp.path(), QStringLiteral("manbo"), QStringLiteral("曼波")));
    QVERIFY(create_valid_pack(temp.path(), QStringLiteral("nai-long"), QStringLiteral("奶龙")));

    PackListModel model;
    model.setVoicesRoot(temp.path());
    model.refresh();
    QCOMPARE(model.count(), 2);

    model.setFilter(QStringLiteral("manbo"));
    QCOMPARE(model.count(), 1);
    QCOMPARE(
        model.index(0, 0).data(PackListModel::PackIdRole).toString(),
        QStringLiteral("manbo")
    );

    // Name matching is case-insensitive and works for non-ASCII names.
    model.setFilter(QStringLiteral("奶龙"));
    QCOMPARE(model.count(), 1);
    QCOMPARE(
        model.index(0, 0).data(PackListModel::PackIdRole).toString(),
        QStringLiteral("nai-long")
    );

    model.setFilter(QStringLiteral("MANBO"));
    QCOMPARE(model.count(), 1);

    // Whitespace-only filters clear the search.
    model.setFilter(QStringLiteral("   "));
    QCOMPARE(model.count(), 2);

    model.setFilter(QStringLiteral("nothing-matches"));
    QCOMPARE(model.count(), 0);
}

void PackListModelTest::refresh_keeps_the_active_filter() {
    QTemporaryDir temp;
    QVERIFY(temp.isValid());
    QVERIFY(create_valid_pack(temp.path(), QStringLiteral("manbo")));
    QVERIFY(create_valid_pack(temp.path(), QStringLiteral("nai-long")));

    PackListModel model;
    model.setVoicesRoot(temp.path());
    model.setFilter(QStringLiteral("manbo"));
    model.refresh();

    QCOMPARE(model.count(), 1);
    QCOMPARE(model.filter(), QStringLiteral("manbo"));

    // Clearing the filter reveals the pack that was hidden.
    model.setFilter(QString());
    QCOMPARE(model.count(), 2);
}

void PackListModelTest::contains_folder_uses_the_unfiltered_set() {
    QTemporaryDir temp;
    QVERIFY(temp.isValid());
    QVERIFY(create_valid_pack(temp.path(), QStringLiteral("manbo"), QStringLiteral("Manbo")));
    QVERIFY(
        create_valid_pack(
            temp.path(),
            QStringLiteral("nai-long"),
            QStringLiteral("Nai Long")
        )
    );

    PackListModel model;
    model.setVoicesRoot(temp.path());
    model.refresh();
    QCOMPARE(model.count(), 2);

    // Take the path the same way QML does, so the comparison is exact.
    const auto manbo = model.index(0, 0)
                           .data(PackListModel::FolderPathRole)
                           .toString();
    QVERIFY(!manbo.isEmpty());
    QVERIFY(model.containsFolder(manbo));
    QVERIFY(!model.containsFolder(manbo + QStringLiteral("-missing")));
    QVERIFY(!model.containsFolder(QString()));

    // Hiding a pack with the search box must not make it look deleted.
    model.setFilter(QStringLiteral("Nai Long"));
    QCOMPARE(model.count(), 1);
    QVERIFY(model.containsFolder(manbo));
}

QTEST_GUILESS_MAIN(PackListModelTest)

#include "pack_list_model_test.moc"
