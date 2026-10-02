find_package(Qt6 6.8 REQUIRED COMPONENTS Quick QuickControls2 QuickDialogs2)

qt_standard_project_setup(REQUIRES 6.8)

qt_add_executable(panda_desktop
    src/main.cpp
    src/device_list.cpp
    src/device_list.hpp
    src/pack_list_model.cpp
    src/pack_list_model.hpp
    src/worker_protocol.cpp
    src/worker_protocol.hpp
    src/realtime_controller.cpp
    src/realtime_controller.hpp
    src/session_store.cpp
    src/session_store.hpp
    src/theme_manager.cpp
    src/theme_manager.hpp
)

set(theme_qml qml/Theme.qml)
set(app_state_qml qml/AppState.qml)
set_source_files_properties(${theme_qml} ${app_state_qml}
    PROPERTIES QT_QML_SINGLETON_TYPE TRUE
)

qt_add_qml_module(panda_desktop
    URI Panda
    VERSION 1.0
    QML_FILES
        qml/Main.qml
        qml/GlassBackground.qml
        qml/GlassBlob.qml
        ${theme_qml}
        ${app_state_qml}
        qml/components/Icon.qml
        qml/components/AppButton.qml
        qml/components/AppIconButton.qml
        qml/components/AppTextField.qml
        qml/components/AppComboBox.qml
        qml/components/AppSpinBox.qml
        qml/components/AppSwitch.qml
        qml/components/AppSlider.qml
        qml/components/VolumeSlider.qml
        qml/components/TickMeter.qml
        qml/components/PowerToggle.qml
        qml/components/GlassRoundButton.qml
        qml/components/AppTabButton.qml
        qml/components/AppScrollBar.qml
        qml/components/AppScrollView.qml
        qml/components/Tooltip.qml
        qml/components/AppCard.qml
        qml/components/SectionTitle.qml
        qml/components/SettingRow.qml
        qml/components/LevelMeter.qml
        qml/components/AppConfirmDialog.qml
        qml/components/TopTab.qml
        qml/components/SegmentedControl.qml
        qml/components/StatusPill.qml
        qml/components/VoiceCard.qml
        qml/pages/VoiceLibraryPage.qml
        qml/pages/SettingsPage.qml
)

qt_add_resources(panda_desktop "panda_app_assets"
    PREFIX "/"
    FILES
        assets/logo.png
        assets/logo.svg
)

target_link_libraries(panda_desktop
    PRIVATE
        panda_core
        Qt6::Core
        Qt6::Quick
        Qt6::QuickControls2
        Qt6::QuickDialogs2
)

set_target_properties(panda_desktop PROPERTIES
    WIN32_EXECUTABLE TRUE
    MACOSX_BUNDLE TRUE
)

option(PANDA_BUILD_DESKTOP_TESTS "Build Qt model tests for the desktop app" ON)

if(PANDA_BUILD_DESKTOP_TESTS AND BUILD_TESTING)
    find_package(Qt6 6.8 REQUIRED COMPONENTS Test)

    qt_add_executable(panda_pack_model_tests
        tests/pack_list_model_test.cpp
        src/pack_list_model.cpp
        src/pack_list_model.hpp
    )

    target_include_directories(panda_pack_model_tests PRIVATE src)

    target_link_libraries(panda_pack_model_tests
        PRIVATE
            panda_core
            Qt6::Core
            Qt6::Test
    )

    qt_add_executable(panda_device_list_tests
        tests/device_list_test.cpp
        src/device_list.cpp
        src/device_list.hpp
    )

    target_include_directories(panda_device_list_tests PRIVATE src)

    target_link_libraries(panda_device_list_tests
        PRIVATE
            Qt6::Core
            Qt6::Test
    )

    qt_add_executable(panda_worker_protocol_tests
        tests/worker_protocol_test.cpp
        src/worker_protocol.cpp
        src/worker_protocol.hpp
    )

    target_include_directories(panda_worker_protocol_tests PRIVATE src)

    target_link_libraries(panda_worker_protocol_tests
        PRIVATE
            panda_core
            Qt6::Core
            Qt6::Test
    )

    qt_add_executable(panda_session_store_tests
        tests/session_store_test.cpp
        src/session_store.cpp
        src/session_store.hpp
        src/worker_protocol.cpp
        src/worker_protocol.hpp
    )

    target_include_directories(panda_session_store_tests PRIVATE src)

    target_link_libraries(panda_session_store_tests
        PRIVATE
            panda_core
            Qt6::Core
            Qt6::Test
    )

    foreach(target
        panda_pack_model_tests
        panda_device_list_tests
        panda_worker_protocol_tests
        panda_session_store_tests
    )
        # A test binary must stay a console application, otherwise Qt Test has
        # no stream to report into and the run looks silent even when it fails.
        set_target_properties(${target} PROPERTIES
            WIN32_EXECUTABLE FALSE
            MACOSX_BUNDLE FALSE
        )

        add_test(NAME ${target} COMMAND ${target})
        set_tests_properties(${target} PROPERTIES TIMEOUT 120)
        # The test executable needs the Qt runtime on PATH when CTest runs it.
        set_property(
            TEST ${target}
            PROPERTY ENVIRONMENT_MODIFICATION
            "PATH=path_list_prepend:$<TARGET_FILE_DIR:Qt6::Core>"
        )
    endforeach()
endif()

