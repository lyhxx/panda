# 熊猫变声器 (Panda Voice Changer) — 软件

开源、免费、本地优先的实时变声器**客户端**（Qt 6 / QML + C++20）。

这个仓库只包含软件本身，**不包含音频处理引擎和模型**：

| 仓库 | 地址 | 内容 |
| --- | --- | --- |
| **panda**（本仓库） | https://github.com/lyhxx/panda | 桌面界面、C++ 核心、音色包校验/安装、打包与安装脚本 |
| **panda-engine** | https://github.com/lyhxx/panda-engine | 音频处理引擎（Python：实时会话、DSP、降噪、音色包导出） |
| **panda-models** | https://github.com/lyhxx/panda-models | 处理后的模型（ONNX / 微调模型 / 默认音色包） |

> 相关仓库
>
> - 引擎：[github.com/lyhxx/panda-engine](https://github.com/lyhxx/panda-engine)
> - 模型：[github.com/lyhxx/panda-models](https://github.com/lyhxx/panda-models)

## 目录

```text
CMakeLists.txt        顶层构建
core/                 C++20 核心库（音色包 manifest/安装、指标解析）
desktop/              Qt/QML 桌面应用
cli/                  C++ 命令行
tests/                C++ / 脚本测试
third_party/          第三方头文件
scripts/              打包、安装、开发启动脚本
docs/                 架构与设计文档
```

## 构建

```powershell
cmake -S . -B build/windows-msvc-desktop -G "Visual Studio 17 2022" -A x64 `
  -DCMAKE_PREFIX_PATH="<Qt 6.8 msvc2022_64>" -DPANDA_BUILD_DESKTOP=ON
cmake --build build/windows-msvc-desktop --config Release
ctest --test-dir build/windows-msvc-desktop -C Release
```

## 运行（开发）

桌面应用通过环境变量找到引擎与模型：

```text
PANDA_PYTHON          引擎使用的 Python 解释器
PANDA_MEANVC2_ROOT    MeanVC2 仓库（含运行时与 checkpoint）
PANDA_VOICES_ROOT     音色包目录
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_dev_desktop.ps1
```

## 许可

Apache License 2.0，见 [LICENSE](LICENSE)。第三方声明见
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
