#include "panda/version.hpp"
#include "panda/product.hpp"
#include "pack_list_model.hpp"
#include "realtime_controller.hpp"
#include "session_store.hpp"
#include "theme_manager.hpp"

#include <QGuiApplication>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QIcon>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQuickStyle>
#include <QStandardPaths>

namespace {

void set_environment_if_empty(const char* name, const QString& value) {
    if (qEnvironmentVariableIsEmpty(name) && !value.isEmpty()) {
        qputenv(name, value.toUtf8());
    }
}

void configure_bundled_environment() {
    const QDir application_dir(QCoreApplication::applicationDirPath());
    const auto portable_marker = application_dir.filePath(
        QStringLiteral("portable")
    );

    const auto bundled_python = application_dir.filePath(
        QStringLiteral("python/python.exe")
    );
    if (QFileInfo::exists(bundled_python)) {
        set_environment_if_empty("PANDA_PYTHON", bundled_python);
    }

    const auto bundled_meanvc2 = application_dir.filePath(
        QStringLiteral("MeanVC2")
    );
    if (QFileInfo::exists(
            QDir(bundled_meanvc2).filePath(QStringLiteral("runtime/run_rt.py"))
        )) {
        set_environment_if_empty("PANDA_MEANVC2_ROOT", bundled_meanvc2);
    }

    if (QFileInfo::exists(portable_marker)) {
        set_environment_if_empty(
            "PANDA_VOICES_ROOT",
            application_dir.filePath(QStringLiteral("voices"))
        );
    }

    const auto voices_path_file = application_dir.filePath(
        QStringLiteral("voices-path.txt")
    );
    if (qEnvironmentVariableIsEmpty("PANDA_VOICES_ROOT") &&
        QFileInfo::exists(voices_path_file)) {
        QFile file(voices_path_file);
        if (file.open(QIODevice::ReadOnly | QIODevice::Text)) {
            auto configured_path = QString::fromUtf8(
                file.readAll()
            ).trimmed();
            // Windows PowerShell 5.1 writes UTF-8 with a BOM, and fromUtf8
            // keeps it as U+FEFF: a "path" starting with that character is
            // not absolute anymore, so mkpath would create a garbage folder
            // relative to the working directory and the library looks empty.
            if (configured_path.startsWith(QChar::ByteOrderMark)) {
                configured_path.remove(0, 1);
            }
            if (!configured_path.isEmpty()) {
                qputenv("PANDA_VOICES_ROOT", configured_path.toUtf8());
            }
        }
    }

    const auto bundled_modules = application_dir.filePath(
        QStringLiteral("share/python")
    );
    if (!QFileInfo::exists(bundled_modules)) {
        return;
    }

    if (!qEnvironmentVariableIsSet("PYTHONDONTWRITEBYTECODE")) {
        qputenv("PYTHONDONTWRITEBYTECODE", "1");
    }

    auto python_paths = qEnvironmentVariable("PYTHONPATH")
                            .split(QDir::listSeparator(), Qt::SkipEmptyParts);
    if (!python_paths.contains(bundled_modules, Qt::CaseInsensitive)) {
        python_paths.prepend(bundled_modules);
        qputenv(
            "PYTHONPATH",
            python_paths.join(QDir::listSeparator()).toUtf8()
        );
    }
}

}  // namespace

int main(int argc, char* argv[]) {
    QString application_version = QString::fromUtf8(panda::version_string());
    QCoreApplication::setApplicationName(
        QString::fromUtf8(panda::kProductId.data(), int(panda::kProductId.size()))
    );
    QCoreApplication::setOrganizationName(
        QString::fromUtf8(panda::kProductId.data(), int(panda::kProductId.size()))
    );
    QCoreApplication::setApplicationVersion(application_version);

    QGuiApplication application(argc, argv);
    application.setWindowIcon(QIcon(QStringLiteral(":/assets/logo.png")));
    // The Basic style is pure QML, so every control can be fully re-themed
    // without an OS-native look leaking through (native scrollbars, popups,
    // editable fields, and so on).
    QQuickStyle::setStyle(QStringLiteral("Basic"));
    configure_bundled_environment();

    const auto configured_root = qEnvironmentVariable("PANDA_VOICES_ROOT");
    const auto voices_root = configured_root.isEmpty()
        ? QDir(QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation))
              .filePath("voices")
        : configured_root;
    QDir().mkpath(voices_root);

    PackListModel pack_list_model;
    pack_list_model.setVoicesRoot(voices_root);
    pack_list_model.refresh();
    RealtimeController realtime_controller;
    panda::desktop::SessionStore session_store;
    ThemeManager theme_manager;

    QQmlApplicationEngine engine;
    engine.rootContext()->setContextProperty(
        "packListModel",
        &pack_list_model
    );
    engine.rootContext()->setContextProperty(
        "realtimeController",
        &realtime_controller
    );
    engine.rootContext()->setContextProperty("sessionStore", &session_store);
    engine.rootContext()->setContextProperty("themeManager", &theme_manager);
    engine.rootContext()->setContextProperty(
        "productName",
        QString::fromUtf8(
            panda::kProductName.data(),
            int(panda::kProductName.size())
        )
    );
    engine.rootContext()->setContextProperty(
        "productNameEn",
        QString::fromUtf8(
            panda::kProductNameEn.data(),
            int(panda::kProductNameEn.size())
        )
    );
    engine.loadFromModule("Panda", "Main");

    if (engine.rootObjects().isEmpty()) {
        return EXIT_FAILURE;
    }

    return application.exec();
}

