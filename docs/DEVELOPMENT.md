# Panda 开发文档

本文是 Panda 唯一的开发文档：环境搭建、架构、实现细节、测试、打包与发布都在这里。
产品介绍见 [README](../README.md)，版本变更见 [CHANGELOG](../CHANGELOG.md)。

## 1. 项目概览

### 1.1 产品原则

- 本地优先：变声不依赖账号和云端服务，音频不出本机。
- 模块解耦：界面、音频、推理和模型管理互不耦合，推理跑在独立进程。
- 格式开放：音色包是明文 ZIP，可检查、可迁移、可重新生成。
- CPU 可用：CPU 实时是默认路径，GPU 只是可选加速。
- 可降级：设备、模型、降噪都有明确的失败回退和用户提示。
- 可诊断：延迟、丢帧、推理耗时、电平和设备状态可视化，`panda doctor` 一键自检。
- 资源独立发布：公共模型、音色包、训练工具与客户端独立版本化。

### 1.2 仓库结构

Python 引擎源码位于 `python/`：

```text
panda/
  CMakeLists.txt            顶层构建，版本号从 version.hpp 解析
  CMakePresets.json         构建预设
  README.md                 产品文档（含开源组件清单）
  CHANGELOG.md              更新日志
  LICENSE / NOTICE
  core/                     C++20 核心库
    include/panda/          头文件（version.hpp = 全局版本唯一来源）
    src/
  cli/                      C++ 命令行入口（main.cpp）
  desktop/                  Qt 6 / QML 桌面应用
  python/                   Python 引擎
    pyproject.toml          setuptools 工程，dynamic version
    src/
      panda_cli/            统一命令行入口
      panda_infer/          DSP、抖动缓冲、实时会话、降噪、ONNX 导出、试听…
      panda_pack/           开放音色包导出
      panda_version.py      Python 侧版本唯一来源
  tests/                    测试
    core/                   C++ 测试源码（由 CTest 运行）
    test_*.py               Python 测试（unittest discover 运行）
  scripts/                  打包、安装、开发启动、测试语音生成等脚本
  docs/                     本文档与截图
  third_party/              第三方头文件与许可
  build/                    构建产物（不入库）
  dist/                     打包产物（不入库）
```

目录调整时必须同步更新本文档和构建脚本。

### 1.3 技术栈与代码规范

| 领域 | 选型 |
| --- | --- |
| 桌面 | Qt 6.8.3（QML/Quick）、C++20、CMake |
| 引擎 | Python 3.11、PyTorch 2.5.1（CPU）、sounddevice/PortAudio |
| 变声 | MeanVC2（ASR / DiT CFM / Vocos / FCPE + 说话人嵌入） |
| 降噪 | DeepFilterNet3（可选，三档） |
| 哈希 | SHA-256 |
| 配置 | C++ 侧 QSettings（注册表）+ JSON；音色包内 YAML/JSON |

规范：

- 字符编码 UTF-8，换行 LF；二进制模型优先 safetensors / ONNX。
- 音色包内只允许相对路径（`/` 分隔），禁止绝对路径、`..`、符号链接。
- 日志为结构化行，不记录原始音频、音色包内容、完整绝对路径。
- 提交规范：`feat:` `fix:` `docs:` `test:` `refactor:` `build:` `chore:`。

## 2. 开发环境

### 2.1 构建环境（已验证版本）

| 组件 | 位置 | 版本 |
| --- | --- | --- |
| VS Build Tools | `C:\BuildTools` | MSVC 14.44.35207，WinSDK 10.0.26100.0 |
| CMake / Ninja / MSBuild | `C:\BuildTools\...` | 随 Build Tools 安装 |
| Qt | `.tools\Qt\6.8.3\msvc2022_64` | 6.8.3（Quick/Controls2/Multimedia/windeployqt） |
| Miniforge | `.tools\miniforge3` | base 环境含 conda-pack 0.9.2 |
| Python 环境 | `.tools\miniforge3\envs\meanvc2-cpu` | Python 3.11.16 |
| MeanVC2 | `deps\MeanVC2` | 上游 commit 13acf84 |

`meanvc2-cpu` 环境关键包版本（完整清单见根目录 `environment.yml`）：

```text
torch 2.5.1+cpu        torchaudio 2.5.1+cpu    numpy 1.26.4
onnxruntime 1.30.0     onnx 1.23.1（导出）      onnxscript 0.7.2
deepfilternet 0.5.6    s3prl 0.4.18            sounddevice 0.5.6
soundfile / scipy / pillow（音色包导出）         einops / x-transformers / torchdiffeq
```

注意：`deepfilternet` 要求 `numpy<2`，会把 numpy 压回 1.x（与 `ml-dtypes`
的版本告警可忽略，全套测试在 numpy 1.26.4 下通过）。打包脚本同样拒绝
numpy 2.x 的便携环境。

### 2.2 新机器从零搭建

1. **克隆仓库**：

   ```powershell
   git clone https://github.com/lyhxx/panda.git
   cd panda
   ```

2. **C++ 工具链**：安装 Visual Studio Build Tools 2022（C++ 桌面开发 + CMake 工作负载），
   默认装到 `C:\BuildTools` 也可装到任意路径（配置时用 CMake 路径即可）。

3. **Qt**：用 Qt 安装器装 Qt 6.8.3 `msvc2022_64` 组件（Quick、Quick Controls 2、
   Multimedia、Shader Tools），安装到仓库旁的 `.tools\Qt\6.8.3\msvc2022_64`
   （`scripts\run_dev_desktop.ps1` 默认按此路径探测，可用 `-QtRoot` 覆盖）。

4. **Python 环境**：安装 Miniforge 到 `.tools\miniforge3`，然后：

   ```powershell
   conda env create -f environment.yml     # 建环境（见 2.5）
   conda activate meanvc2-cpu
   ```

5. **安装引擎包（editable）**：

   ```powershell
   python -m pip install -e .\python --no-deps --no-build-isolation
   panda --version     # 应输出 1.0.0
   ```

6. **MeanVC2 与模型资产**：

   ```powershell
   git clone https://github.com/ASLP-lab/MeanVC2.git ..\deps\MeanVC2
   cd ..\deps\MeanVC2
   git checkout 13acf84
   python initialization.py --task all      # 自动下载大部分模型
   ```

   自动下载覆盖不了的两个点（见 2.3）：`wavlm_large.pt` 上游链接 404，改用
   HuggingFace 镜像；`wavlm_large_finetune.pth` 必须从 Google Drive 手动下载
   （上游标注不可自动获取）。

7. **DeepFilterNet 检查点**（可选降噪用）：首次使用降噪时会自动缓存到
   `%LOCALAPPDATA%\DeepFilterNet\DeepFilterNet\Cache\DeepFilterNet3`，
   需要其中的 `config.ini` 与 `checkpoints\model_120.ckpt.best`。

8. **验证**（见 2.5 命令）：CTest 全绿、Python 测试全绿、`panda doctor` 零错误。

### 2.3 模型资产与下载源

`deps\MeanVC2` 中必须存在（打包白名单照此复制）：

```text
preprocess/ckpts/fastu2pp_80ms.pt
preprocess/ckpts/fastu2pp_160ms.pt
preprocess/ckpts/wavlm_large.pt
preprocess/ckpts/wavlm_large_cfg.pt
preprocess/ckpts/wavlm_large_finetune.pth     ← Google Drive 手动（约 1.24 GB）
ckpts/pretrained_models/meanvc2_40ms_40ms.safetensors
ckpts/pretrained_models/meanvc2_120ms_40ms.safetensors
ckpts/vocos/vocos.pt
```

`wavlm_large.pt` 的上游 `initialization.py` GitHub 直链已 404，等价文件：

```text
https://huggingface.co/s3prl/converted_ckpts/resolve/main/wavlm_large.pt
```

### 2.4 环境迁移（换机 / 换盘）

不重装环境的两条路：

1. **发布资产即迁移包**：`Panda-runtime.zip` 就是 conda-pack 打出的完整环境，
   解压到新机器任意路径即可用（python 目录自包含，含 VC++ 运行库）。
   模型同理由 `Panda-Models.zip` 提供。
2. **conda 原生流程**（要重建可编辑安装的开发环境时）：

   ```powershell
   .tools\miniforge3\Scripts\conda.exe run -n base `
     conda pack -n meanvc2-cpu --format zip --ignore-editable-packages
   # 解压到新机后执行
   python\Scripts\conda-unpack.exe
   ```

   打包脚本对运行时解压加重试（终端防护在 5 万文件突发写入时会偶发拒写）。
   注意换路径验收不等于换机：editable 安装的 `.pth` 指向源码目录时，在同一台
   机器上的验收会被掩盖——脚本已在 conda-unpack 后剥离 `__editable__*.pth`，
   且 `panda_version.py` 随 `share\python` 分发，运行时对仓库零依赖。
   同类陷阱还有 VC 运行库：exe 与 Qt DLL 都动态链接 MSVCP140/VCRUNTIME140，
   Windows 不自带，windeployqt 也不部署——脚本从 VC redist 目录 app-local
   拷到包根，否则没装过 VC++ 运行库的机器在 loader 阶段就起不来。

### 2.5 环境验证命令

```powershell
# C++：配置、构建、测试（5 个 CTest 目标）
cmake -S . -B build\windows-msvc-desktop -G "Visual Studio 17 2022" -A x64 `
  -DCMAKE_PREFIX_PATH="<Qt>\6.8.3\msvc2022_64" -DPANDA_BUILD_DESKTOP=ON
cmake --build build\windows-msvc-desktop --config Release
ctest --test-dir build\windows-msvc-desktop -C Release

# Python：全部单元测试（179 个）
python -m unittest discover -s tests -v

# 命令与诊断
panda --version
panda doctor --meanvc2-root ..\deps\MeanVC2
```

## 3. 构建、测试与运行

### 3.1 开发启动桌面端

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_dev_desktop.ps1
```

脚本自动设置运行环境（也可手动配）：

| 环境变量 | 含义 | 示例取值 |
| --- | --- | --- |
| `PANDA_PYTHON` | 引擎解释器 | `.tools\miniforge3\envs\meanvc2-cpu\python.exe` |
| `PANDA_MEANVC2_ROOT` | MeanVC2 仓库 | `..\deps\MeanVC2` |
| `PANDA_VOICES_ROOT` | 音色包目录 | `dist\Panda\voices` |
| `PANDA_DEEPFILTER_ROOT` | 降噪检查点 | `%LOCALAPPDATA%\DeepFilterNet\...\DeepFilterNet3` |
| `PYTHONPATH` | 引擎源码 | `<repo>\python\src`（editable 安装后可省） |
| `PATH` | Qt DLL | `<Qt>\bin` |

发布包里这些由 `launch.cmd` 自动设置（见 12.3），用户零配置。

### 3.2 版本号单点管理

全仓库一个版本号，两个语言生态各有一个唯一来源，互相不直接依赖：

| 侧 | 唯一来源 | 消费方 |
| --- | --- | --- |
| C++ | `core\include\panda\version.hpp` 的 `Version{1,0,0}` | `version_string()`；根 CMakeLists 正则解析出 `project(VERSION)`；`scripts\package_windows.ps1` 解析出 manifest 与包名 |
| Python | `python\src\panda_version.py` 的 `__version__` | `pyproject.toml` dynamic version；`panda --version`；三个包（panda_cli/panda_infer/panda_pack）re-export |

`tests\test_version_consistency.py` 解析 version.hpp 与 `panda_version.__version__`
比对，任何一侧单独改版本都会让测试失败。

**发版时两处必须改成同一个值**，改完跑一次 Python 测试即可验证。

### 3.3 测试体系

| 套件 | 命令 | 规模 |
| --- | --- | --- |
| C++（core/desktop/协议/会话/设备） | `ctest --test-dir build\windows-msvc-desktop -C Release` | 5 个目标 |
| Python（引擎 + 音色包 + 安装器 + 版本一致性） | `python -m unittest discover -s tests -v` | 179 个 |

工程经验（都是踩过的坑）：

- C++ 套件曾出现**退出码 0 但没跑完**的假通过：CTest 现在要求
  `PANDA_CORE_TESTS_COMPLETE` 标记，截断的运行会失败而不是假装成功。
- 在部分机器上删除 `.tmp` 下新建目录会卡约 30 秒，C++ 测试用唯一路径 fixture 且不回收
  （`.tmp` 可手工清理，CTest 有 120s 超时）。
- Qt Test 目标必须建成控制台子系统，否则 GUI 子系统下**一行输出都没有**。
- `PSModulePath` 被 PowerShell 7 目录污染时，Windows PowerShell 加载不了
  Security 模块，签名测试要显式指定模块目录。
- 全量 Python 套件偶发一次未记录名称的失败（约 15 次里 1 次），单模块各跑
  10–15 次全过，疑似并发竞争；再现时用 `-v` 抓具体用例。

测试策略：单元（manifest、路径、哈希、配置、DSP、缓冲）、集成（安装/删除/
升级、安装器脚本）、音频回归（真实语音 + `panda voice-check` 客观相似度）、
实时（延迟、下溢、热插拔）、故障（损坏 ZIP、篡改包、越界路径）。

### 3.4 真实语音回归基准

**测试素材必须是真实语音。** 早期 `smoke.wav` 是 220 Hz 正弦波，所有"变声"
测试只证明管线通、从没证明换了说话人。现在用 Windows 自带 TTS 生成语音：

```powershell
.\scripts\make_test_speech.ps1 -VoiceName "Microsoft Zira Desktop" `
  -Text "..." -Output dist\speech-zira.wav

panda voice-check --meanvc2-root ..\deps\MeanVC2 `
  --source-wav dist\speech-zira.wav --target-wav dist\speech-huihui.wav
```

判定依据是说话人嵌入余弦相似度（转换后应更接近目标，且远离源），自带
"源→自身"对照保证度量可信。实测参考值：

```text
对照（源→自身）    转换后 vs 源   +0.7323
源 vs 目标         +0.2831
转换后 vs 目标     +0.7010   ← 0.28 → 0.70
转换后 vs 源       +0.2968
```

## 4. 总体架构

```text
┌────────────────────────────────────────────────────┐
│                Qt 6 / QML 桌面端                     │
│   音色库  设备/音量/降噪设置  主题  延迟/电平  日志面板   │
└───────────────┬────────────────────────────────────┘
                │ 进程内（C++ 控制器 + core 库）
┌───────────────▼────────────────────────────────────┐
│  panda_desktop 进程                                 │
│  worker_protocol：拼命令行、解析指标、崩溃重启决策        │
│  PackListModel / SessionStore / 设备解析（均带测试）    │
└───────────────┬────────────────────────────────────┘
                │ 子进程：python -m panda_cli realtime …
                │   stdout ← [panda.metrics] [panda.level] [panda.ready]
                │   stdin  ← 实时设置 JSON（不重载模型）
┌───────────────▼────────────────────────────────────┐
│  Python 引擎进程（panda_infer）                       │
│  音频回调(sounddevice) → 有界输入队列 → 工作线程          │
│    → 降噪 → 噪声门 → MeanVC2 推理 → 抖动缓冲            │
│    → 软限幅 → 输出/监听                               │
└────────────────────────────────────────────────────┘
```

### 4.1 线程与进程规则

- 推理在 Python **工作线程**，音频回调只做"拷入 + 读缓冲 + 拷出"，不推理、
  不做文件 I/O、不分配大块内存、不等锁。
- 输入队列有界，满则丢最旧（延迟有界优先于完整）。
- 桌面端与引擎**进程隔离**：引擎崩溃不拖垮界面；异常退出自动重启，最多 3 次
  （1/2/3 秒退避），稳定运行 10 秒后重置计数；主动停止与干净退出不重启
  （决策在 `should_restart_realtime`，有 C++ 测试）。
- 设置（音量/门限/设备/降噪/延迟档）经 stdin JSON 下发，实时生效且**不重载模型**。

### 4.2 stdout 协议

```text
[panda.metrics] {"chunk":24,"processing_ms":120.276,"chunk_ms":160.0,
  "buffer_ms":640.0,"overrun":false,"mean_ms":116.113,"max_ms":121.902,
  "starved_reads":0,"underrun_frames":0,"dropped_frames":50240,
  "input_dropped":0,"trimmed_frames":0,
  "prefill_frames":0,"prefill_reads":0,"resume_reads":0,
  "input_rms":...,"input_peak":...,"output_rms":...,"output_peak":...,
  "input_clipped":false,"output_clipped":false,
  "input_latency_ms":...,"output_latency_ms":...,"device_block_ms":...}
[panda.level]  ...   电平刷新
[panda.ready]  ...   首块就绪
```

- 前缀固定，后随单行 JSON；`processing_ms > chunk_ms` 即 overrun。
- C++ 侧 `panda::audio::parse_realtime_stats` 解析，同时兼容 MeanVC2 上游
  `run_rt.py` 的旧控制台格式；指标前缀常量在 core 头文件里，生产/消费共用。
- 指标行走数值显示，不混进日志面板（否则每秒刷两屏）。

### 4.3 配置与日志

- 用户配置：Windows 注册表（QSettings），`SessionStore` 双向清洗——未知模型/
  后端回退默认、延迟走 `clamp_latency`、负设备 id 视为未选、音色包不存在则清空。
- 设备持久化存 `hostApi|设备名` 稳定键，重启后对新设备列表重新解析，
  Windows 设备顺序变化时仍按稳定键选对设备。
- 音色与安装状态：`voices\<id>\manifest.json` 明文 + `package-manifest.json`
  （打包完整性）。日志落盘在 `AppData`，桌面端「打开日志文件」按钮直达，
  日志面板跟随文件尾部。

## 5. 音频管线

### 5.1 分块与抖动缓冲

- 引擎按 **160 ms 块**处理（MeanVC2 分块决定，与实现无关）。
- `panda_infer.jitter_buffer.JitterBuffer`：预滚、下溢计数、超限丢最旧、深度统计。
- **启动盈余问题**（实测发现）：转换器开头几块返回空，随后一次吐多块追赶，
  这波快于播放消耗，盈余**永远留在缓冲里**变成固定延迟（580 ms 对 320 ms
  预滚）。`JitterBuffer.trim_to` 在深度超过「预滚 + 修剪余量」时回收，
  修剪发生在缓冲还装着预滚静音时，丢的是静音不是语音。
- 稳态深度由**修剪阈值**决定而不是预滚目标。余量 1 块时缓冲恰好压在阈值上，
  一次推理抖动就触发修剪，表现为**说话漏字**；默认余量 4 块，实测零修剪：

  | 余量 | 被修剪的已转换音频 | 输出下溢 | 缓冲峰值 |
  | --- | --- | --- | --- |
  | 1 块（旧默认） | 10.76 s（约 18%） | 1.86 s | 320 ms |
  | 2 块 | 0 | 0.14 s | 360 ms |
  | 4 块（现默认） | 0 | 0.14 s | 360 ms |

- 预滚静音单独统计（`prefill_*`），不算下溢；只有稳态补零才计
  `underrun_frames` / `starved_reads`。

### 5.2 采样率转换

WASAPI 共享模式只接受设备自身混音格式（通常 48 kHz），固定开 16 kHz 直接报
`Invalid sample rate`。按设备原生采样率开流，软件转到引擎的 16 kHz：

- `panda_infer.dsp.StreamResampler` 是**有状态**的：FIR 历史跨块保留，
  分块结果与一次性连续处理逐样本一致（有测试），否则每个块边界都是咔哒声。
- 整数倍率走多相路径，非整数退回线性插值；63 抽头线性相位群延迟约
  0.6 ms（48 kHz），远小于块长。

### 5.3 门限、限幅与增益

| 组件 | 行为 | 默认 |
| --- | --- | --- |
| `NoiseGate` | 按块判断、块内斜坡、开快关慢保字头；**不是降噪器** | 关，`-45 dB` 推荐 |
| `SoftLimiter` | 拐点以下透明，以上 tanh 平滑压顶，永不削顶 | 开，上限 0.891（约 -1 dBFS） |
| `OutputGain` | 限幅前固定增益 -24…+12 dB | 0 dB |
| 输入增益 | 降噪与噪声门之前 | 0 dB |
| 监听增益 | 独立于主输出 | 0 dB |

噪声门实测只对**低于阈值**的平稳噪声有效（16 kHz、160 ms、-45 dBFS）：

| 静音段环境声 | 抑制 |
| --- | --- |
| 白噪声 -60 dB / 风扇 -50 dB | 29.1 / 29.8 dB |
| 风扇 -40 dB / 键盘 -40 dB | 0.0 / 0.1 dB |
| 别人说话 -40 / -30 dB | 1.0 / 0.1 dB |

### 5.4 降噪（DeepFilterNet，可选）

- DFN 的 Python API 是离线的（`enhance()` 每次重置循环状态），逐块直调与整段
  差异达 0.235，"保留状态"反而更差（0.60）。采用**重叠相加 + 交叉淡化**
  （`panda_infer.denoise.Denoiser`）：差异 0.0595，代价 160 ms 延迟、1.6× CPU。
  交叉淡化必须在 DFN 自己的 48 kHz 上做，只降一次采样。
- 三档：`strong`（完整抑制，默认）/ `balanced`（≤12 dB）/ `gentle`（≤6 dB）。
  10 dB SNR 真实语音 + 风扇/键盘实测：

  | 档位 | 停顿段抑制（风扇/键盘） | 语音段 SI-SDR |
  | --- | --- | --- |
  | strong | 23.9 / 33.5 dB | +2.32 / +2.58 dB |
  | balanced | 11.3 / 12.3 dB | +2.11 / +2.73 dB |
  | gentle | 5.8 / 6.3 dB | +1.23 / +1.83 dB |

- 它**不处理别人说话**（-0.3 dB）：是降噪器不是说话人分离器。
- 集成在噪声门**之前**，默认关闭；界面标注 +160 ms 与"不去除他人说话"。
- 复现测量：`scripts\evaluate_denoise.py`。

### 5.5 监听输出

第二路独立播放（`MonitorTap` 把主设备刚播的块扇出到自己的抖动缓冲）：
不从主输出抢采样、不影响转换时序；输出走虚拟声卡时也能听见自己；
选"不监听"关闭。设备下拉对虚拟设备加"（虚拟声卡）"标记，机器上没有虚拟
声卡时输出列表下方给一行提示。

## 6. 推理引擎

### 6.1 MeanVC2 优先与变体选择

公共模型：ASR（Fast-U2++）、DiT CFM、Vocos、FCPE；音色专属：`spk_emb`、
`register`、可选 `dit.safetensors`。

两个变体同机实测（160 ms 块、CPU）：

| | 40ms | 120ms |
| --- | --- | --- |
| 每 160 ms 块耗时 | 122 ms | **53.8 ms** |
| 稳态缓冲 | 320 ms | **60 ms** |
| 恒等保持（自身→自身） | 0.732 | **0.791** |
| 转换后 vs 目标 | 0.701 | 0.696 |

上游 README 的"110 ms 端到端"是 40ms 变体按**自己的 40 ms 分块**算的首包
延迟；我们的流式块对两者都是 160 ms，该优势用不上，而 40ms 每秒要跑约三倍
DiT 步数。**默认 120ms**，40ms 保留可选——只有把音频块改小它才会翻身。

### 6.2 线程与预热

- batch=1 小模型**单线程最快**（实测 1 线程 115 ms / 2 线程 137 ms / 8 线程 154 ms），
  官方 `torch.set_num_threads(1)` 是验证过的默认，不要调大。
- **必须预热**：预热前首块 348 ms（连吃 5 块缓冲），预热 3 块静音后最大 133 ms；
  预热后要重置流式缓存，否则丢音频开头。桌面端首块等待 348→133 ms 即来源于此。
- 约 0.4% 的块超 160 ms 预算——抖动缓冲就是为此存在的，不是每块都必须准时。

### 6.3 ONNX 导出现状（去 Python 化的边界）

| 阶段 | 结论 | 关键坑 |
| --- | --- | --- |
| Vocoder | ✅ 已验证 | 入口是 `decode` 不是 `forward`；iSTFT 的 `aten::complex` 只有 dynamo 能翻；dynamo 的 `ScatterND` 索引是 int32，需转 int64 且 Cast 必须紧贴消费者（放图开头会先吃 25 GB 内存再放弃）。相对偏差 4.1e-05 |
| ASR | ✅ 两变体已验证 | 恰好相反：dynamo 在符号形状 `Eq(u0, -1)` 上失败，旧导出器一次通过；offset 必须 ≥ 缓存长度，否则切出空张量报维度错误。相对偏差 4.2e-07 / 4.9e-07 |
| DiT | ❌ 当前不可行 | `jit.script` 卡未标注默认参 + jaxtyping 注解；`jit.trace` 撞 KV 缓存数据相关分支（trace 会把布尔烧成常量，不泛化） |

结论：**当前工具链做不出纯 ONNX/C++ 运行时**，除非把 DiT 流式路径重写成可
trace 的形式。Python 引擎实测 RTF 0.757、零下溢，继续作为后端；ASR/vocoder
导出作为已验证基础保留。导出命令会与 PyTorch 对比数值，相对偏差 >1e-3 直接
报错：

```powershell
python -m panda_infer.onnx_export --meanvc2-root ..\deps\MeanVC2 `
  --stage vocoder --output dist\vocoder.onnx
python -m panda_infer.onnx_export --meanvc2-root ..\deps\MeanVC2 `
  --stage asr --model 40ms --output dist\asr-40ms.onnx
```

## 7. 音色包

### 7.1 格式 v1

音色包是明文 ZIP，`manifest.json` 位于根目录（不套随机目录）：

```text
voice-pack.zip
  manifest.json
  mvc2_<id>_rt.yaml
  assets/
    register.json
    spk_emb.npy
    dit.safetensors          # 仅 fine-tuned，可选
  reference/reference.wav    # 可选，建议保留
  LICENSES.json              # 可选
```

资源规则：`zero-shot` 必须有 `spk_emb.npy` + `register.json`；`fine-tuned`
必须有 `dit.safetensors` + `spk_emb.npy`；引擎公共模型不进音色包；
包内只允许 `/` 分隔的相对路径，禁止 `../`、绝对路径、驱动器/UNC 前缀、
符号链接与硬链接。Manifest 不得含密钥、令牌、绝对路径、可执行文件与 DLL。

`manifest.json` 关键字段：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| schema_version | 是 | 当前 1 |
| format | 是 | 固定 `panda.voice-pack` |
| id | 是 | 只允许小写字母、数字、短横线 |
| name / version | 是 | 展示名 / 语义化版本 |
| engine | 是 | `meanvc2` / `rvc` / `dsp` |
| kind | 是 | `zero-shot` / `fine-tuned` / `dsp` |
| entry / assets_dir | 是 | 运行 YAML / 资产目录（包内相对路径） |
| files | 是 | 除 manifest 外全部文件的 path+size+sha256（小写十六进制），安装器必须实校验 |

安装原子性：读 ZIP → 解压到临时目录 → 路径检查 → 读 manifest → 校验大小与
SHA-256 → 检查 schema 与引擎支持 → 移入 `voices\<id>` → 更新索引。
任一步失败保持原包不变。限制（代码常量 + 测试覆盖）：ZIP ≤2 GB、单文件
≤1 GB、文件数 ≤256、解压总量 ≤4 GB。

升级规则：同 id 可覆盖；新旧 `schema_version` 不一致拒绝（`unsupported_schema`，
原包不动）；覆盖前校验已装目录的 id 与新包一致；删除只删 `voices\<id>`，
先验 id 合法性（`../escape` 直接拒）、目录含 manifest 且 id 相符、解析路径
必须在 `voices_root` 正下方，公共模型不会被触及。

### 7.2 导出工具

```powershell
panda pack --name "我的音色" --id my-voice --audio 1.wav `
  --meanvc2-root ..\deps\MeanVC2 --python python --device cpu `
  --output out --overwrite
```

- 输入支持 WAV / MP3 / FLAC / OGG / M4A / AAC / WMA（soundfile 解码、混单声道、
  重采样 16 kHz、写规范 PCM WAV 参考）。
- 调用官方 MeanVC2 提取说话人嵌入（`extract_spk_emb.py`，subprocess 隔离），
  生成 `spk_emb.npy`、`register.json`、运行 YAML、`manifest.json` 并打包。
- 发布物 `Panda-Pack.zip` **不带环境**（源码 + 使用说明，几 MB），使用方自备
  Python 3.10+、`numpy soundfile scipy pillow` 与 MeanVC2 仓库；解压后
  `python -m panda_pack --help`。

### 7.3 安装、删除与目录

- 桌面端：单个安装（文件选择 + 覆盖确认）、**批量安装**（多选/拖放，逐项进度
  与失败清单横幅）、行内删除（二次确认）、搜索/收藏/排序。
- 命令行：`panda_cli install <pack.zip> <voices-root> [--overwrite]`、
  `list`、`remove <voices-root> <pack-id>`（错误码见 core `ErrorCode`，
  如 6=unsupported_schema、12=not_found）。
- 错误码映射成中文界面文案，覆盖"已安装/schema 不匹配/校验失败"等。
- **`voices/` 只在本地**：不进 git、不进 Release 资产（打包脚本自动排除）、
  升级覆盖不删除；音色涉及授权，任何仓库都不放。

## 8. 桌面应用

液态玻璃界面，主要能力：

- **音色库**：卡片网格、试听（`panda preview`，按参考音频试最多 8 秒，用所选
  输出设备原生采样率）、搜索（id+名称，刷新后保持）、收藏、排序（收藏优先/名称）、
  安装/删除/批量安装。
- **底部控制条**：状态行（音色名、状态文案、延迟状态条 2.5s OutCubic 平滑、
  过载指示、监听指示）+ 三个按钮：开启/停止、监听开关（仅输出为虚拟声卡时
  显示）、打开设置。主题三态切换（跟随系统/浅色/深色）在标题栏。
- **设置弹窗**（玻璃风格）：
  - 音频页：输入（设备下拉 + 电平条 + 麦克风音量直调系统音量）、输出（首行
    "不输出"占位；虚拟设备标记；无虚拟声卡时一行提示与 VB-CABLE 下载引导；
    电平条 + 输出音量）、监听、声音处理（降噪开关 + 三档、静音门开关 + 阈值）。
    两个设备下拉在枚举到达前显示占位（正在检测/检测失败），枚举失败就地显示
    错误并可点刷新重试。
  - 常规页：性能与延迟（预滚块数、缓冲上限，`clamp_latency` 钳制并回显）、
    诊断入口、关于。
  - 模型与算力（120ms/40ms、cpu/cuda）由会话记忆并传给引擎（默认 120ms/cpu，
    见 6.1）；1.0.0 界面暂无切换入口。麦克风自检走命令行 `panda mic-test`
    （录 3 秒回放，区分采集/权限/输出问题），界面暂无入口。
- **诊断**：运行日志面板（跟随文件尾；`[panda.metrics]` 分流到数值区）+
  「打开日志文件」按钮；只有真发生过 starve/下溢/丢帧才显示诊断行，
  健康会话不刷一排零。
- **会话持久化**：音色包、设备、模型、算力、延迟、门限、降噪档、主题、
  收藏与排序全部跨重启记忆；恢复的音色包必须仍存在才生效。
- **崩溃恢复**：worker 异常退出自动重启（见 4.1），关闭程序时主动停 worker。

未实现（明确不做在 1.0.0）：音高变换（需要真正的流式变调算法）。

## 9. 虚拟声卡路由

变声器只完成一半：把麦克风换成目标音色。另一半是让**别的软件**听到结果——
Discord/游戏/OBS 都只从"麦克风"取声，需要虚拟声卡当桥：

```text
真实麦克风 ──► Panda（变声） ──► 虚拟声卡写入端（CABLE Input）
                                      │
                                      ▼
                             虚拟声卡采集端（CABLE Output） ──► Discord/游戏/OBS
```

**v1 不自带驱动**：内核驱动要管理员权限 + 代码签名，会把"下载即用"变成
"先过一遍安全警告"。依赖用户自装虚拟声卡（VB-CABLE 免费最简 / VoiceMeeter
功能更多），装完 Panda 本身仍是用户级程序。

步骤：

1. 桌面端输出下拉没有虚拟声卡时给**去 www.vb-cable.com 下载**按钮。
   安装三步顺序不能错：**解压 → 右键管理员运行 → 重启**（否则报
   `LOADDRV: The path does not exist`(-106)）。
2. 终端验证路由：`panda route-check --python <python>`，有路由时直接给出两端
   该选的设备名；没有时退出码 1。此命令只留在终端，界面不调用。
3. Panda 输出选 `CABLE Input`（虚拟设备带"（虚拟声卡）"标记）。
4. 其它软件麦克风选 `CABLE Output`。
5. 可选监听：输出写虚拟声卡的同时，"监听输出"选自己的耳机（独立缓冲，
   不抢主输出采样）；选"不监听"关闭。

已知限制与排错：

- 采样率要一致（44.1 kHz 且驱动不重采样可能变调/杂音）。
- 虚拟声卡不提供降噪，噪声会被一起转换；监听有自己的预滚，与主输出不完全同步。

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 安装器报 -106 | 没用管理员身份，或在压缩包预览里直接运行 | 解压后右键**以管理员身份运行** |
| 装完没有设备 | 官网要求重启 | 重启电脑后点**刷新** |
| route-check 无路由 | 只装了一端/没装 | 装 VB-CABLE 后重跑 |
| 对方听不到 | 该软件麦克风没改成 CABLE Output | 在该软件里改 |
| 自己是聋的 | 输出被独占 | 监听选自己的耳机 |

自带签名驱动留作后续（内核驱动 + EV 证书 + 一次管理员安装）。

## 10. 训练（MeanVC2）

官方项目：https://github.com/ASLP-lab/MeanVC2

### 10.1 两种使用方式

- **零样本**（默认路径）：干净目标人声提取说话人嵌入即可，公共基座推理，
  音色包只有几 KB（`spk_emb + register + YAML`），CPU 可完成。
- **说话人微调**：训练 DiT，音色包增加几十 MB（`dit.safetensors`）。

### 10.2 官方环境与数据

```bash
git clone https://github.com/ASLP-lab/MeanVC2.git && cd MeanVC2
conda create -n meanvc2 python=3.11 -y && conda activate meanvc2
pip install torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
python initialization.py --task all        # WavLM 微调权重按官方 README 手动下载
```

数据建议：先做 5–10 分钟冒烟训练再扩量。零样本 5–30 秒即可；微调试听
10–30 分钟、初步效果 1–3 小时、稳定 10 小时以上。要求单人、无音乐、无混响、
无多人对话、尽量无噪声削波、片段 3–15 秒、WAV；文件名只用小写字母/数字/
短横线/下划线。

### 10.3 特征与训练

```bash
# 120ms+40ms 模型
python preprocess/extract_mel.py       --input_dir data/wavs --output_dir data/mels
python preprocess/extract_bn_160ms.py  --input_dir data/wavs --output_dir data/bns
python preprocess/extract_spk_emb.py   --input_dir data/wavs --output_dir data/xvectors
python scripts/create_filelist.py --bn-dir data/bns --mel-dir data/mels \
  --xvector-dir data/xvectors --output data/train.list
# 40ms 模型用 extract_bn_80ms.py 替代 extract_bn_160ms.py

DATASET_PATH=data/train.list EXP_NAME=speaker_120ms bash scripts/train_120ms_40ms.sh 0
```

显存不足按序降 `batch-size`/`max-len`、提 `grad-accumulation-steps`、开
`grad-ckpt 1`。先用小参数验证能存取 checkpoint 再上正式参数。

已知问题：

- 训练脚本用 Bash + `accelerate` + 进程替换，Windows 请用 WSL2 或 Linux GPU 机。
- 上游 `default_config.yaml` 写着 `distributed_type: MULTI_NPU`，NVIDIA 环境
  要生成自己的 Accelerate 配置。
- 上游 shell 脚本**没有直接暴露预训练 checkpoint 参数**——上线训练前必须确认
  `train.py` 从 `meanvc2_120ms_40ms.safetensors` 初始化，否则可能是从头训练。
- CPU 只适合特征提取与排障；正式训练 8 GB 显存起步，12–24 GB 更稳。

### 10.4 产物入包

```text
assets/{dit.safetensors, spk_emb.npy, register.json} + mvc2_<id>_rt.yaml + manifest.json
```

导出前检查：干净环境可加载、特征维度与运行时一致、YAML 的 dit 路径正确、
`spk_emb` 与训练说话人一致、版本号递增、manifest 哈希重算。
**训练完成 ≠ 音色包可用**：至少过离线推理、实时推理、音高、响度、长句、
静音输入六关。

## 11. 性能与实测数据

### 11.1 延迟预算（端到端约 440 ms 的构成）

| 环节 | 量级 | 说明 |
| --- | --- | --- |
| 输入分块 | 160 ms | 必须等一块填满 |
| 推理 | ~120 ms（40ms 变体；120ms 变体约 54 ms） | 单线程 CPU |
| 输出预滚 | 160 ms（1 块默认） | 可调，换抗抖动余量 |

**原定"低于 150 ms"在 MeanVC2 上无法达成**：光分块 + 预滚就 320 ms，与实现
质量无关。要 150 ms 量级需要帧级流式引擎（引擎层替换，不是调参）。真机
含系统缓冲的端到端实测：p50 289 ms / p95 378 ms。

### 11.2 CPU 基准（480 块 ≈ 76.8 秒音频）

```text
CPU:      14 核移动级处理器，16 kHz，160 ms 块，单线程
RTF:      0.757        延迟: mean 121 / p50 120 / p95 132 / p99 145 ms
超时块:   2 / 480      长期漂移: 无     初始化: ~6 秒（含 WavLM 说话人模型）
```

### 11.3 30 分钟连续运行（阶段验收）

```text
11177 块，下溢 0，饿读 0，丢帧 0，输入丢失 0
内存 2021 → 2023.6 MB（非单调，无泄漏），线程 38–41，CPU 均值 0.736 核
采集与播放无时钟漂移；单块最大 242 ms（正是抖动缓冲要吸收的）
```

### 11.4 端到端仿真（`panda simulate`，WAV 驱动整条管线）

```text
20 秒音频 / 40ms 变体：125 块，平均推理 118.9 ms，最大 133.1 ms（预热后）
下溢 0，缓冲丢帧 0，输出 20.42 s
预热前首块 348 ms → 预热 3 块后 133 ms
```

预滚取舍：1 块=启动静音 0.32 s、峰值 157 ms；2 块=0.48 s、峰值 133 ms，
均零下溢。`--prefill-chunks` / `--max-backlog-chunks` 在 realtime、simulate
与启动器上都可调。

## 12. 打包与发布

### 12.1 打包命令

```powershell
.\scripts\package_windows.ps1 -BundlePython -BundleMeanVC2
```

流程：构建 → CTest → 暂存目录（`dist\Panda.building-<pid>`）→ windeployqt
（锁文件重试 3 次）→ 签名（有证书时）→ conda-pack 环境 + 解压（瞬时故障重试
3 次）+ conda-unpack → 复制 DeepFilterNet/MeanVC2 → 自带 doctor 自检 →
文档与 manifest（逐文件 SHA-256）→ **原子换入** `dist\Panda` → 分切四资产。

主要参数：`-BundlePython`、`-BundleMeanVC2`、`-NoZip`（不出资产）、
`-SkipTests`、`-CertificateThumbprint`/`-TimestampUrl`（签名）、
`-OutputDirectory`。输入路径全部有默认值（`.tools` / `..\deps\MeanVC2` /
`%LOCALAPPDATA%\DeepFilterNet\...`）。

### 12.2 四资产（GitHub Release）

| 资产 | 内容 | 约大小 |
| --- | --- | --- |
| `Panda-<版本>.zip` | 主程序：exe、Qt 运行库、`share\python`（引擎源码）、文档、`launch.cmd`、manifest | ~0.1 GB |
| `Panda-runtime.zip` | `python\`（完整 conda 环境，自包含 VC++ 运行库）+ `DeepFilterNet\` | ~0.7 GB |
| `Panda-Models.zip` | `MeanVC2\`（白名单模型，约 1.8 GB 解压后） | ~1.7 GB |
| `Panda-Pack.zip` | `Panda-Pack\`：导出工具源码 + `README.txt` 使用说明，不带环境 | 几 MB |

规则：

- **单资产 ≤2 GiB**（GitHub 上限），打包后逐个校验，超限直接报错——
  模型包按 1.8 GB 阈值预留分卷余地。
- 资产内**不含 `voices/`**（用户私密音色，脚本自动排除）；打包目录
  `dist\Panda\voices` 保留用于验证。
- 主包清单 `package-manifest.json` 描述**组装后**的完整目录（三包解压到一起
  即与清单一致），安装器据此逐文件校验。

### 12.3 用户解压方式（零配置）

三个应用包解压到**同一个空文件夹**（并排合并），然后双击：

```text
Panda-1.0.0.zip   ─┐
Panda-runtime.zip  ├──► 同一文件夹：panda_desktop.exe、launch.cmd、
Panda-Models.zip   ─┘              python\、DeepFilterNet\、MeanVC2\
                                        │
                                  双击 launch.cmd
```

`launch.cmd` 设置 `ROOT` 下的 `python\`、`MeanVC2\`、`DeepFilterNet\`、
`share\python`（PYTHONPATH）后拉起 `panda_desktop.exe`，全部相对自身路径，
不依赖环境变量、不挑盘符路径。

### 12.4 安装版（仅内部使用 / 可选分发）

```powershell
.\scripts\install_windows.ps1 -SourceDirectory dist\Panda   # 复制前逐文件校验 manifest
.\scripts\uninstall_windows.ps1 -InstallDirectory <dir>      # 保留 voices，-RemoveVoices 才删
```

`-Force` 原地升级：只替换 `app/`，音色目录保留，`install.json` 记录
`previous_version`。`-SkipVerify` 故意装未校验包；`-RequireSignature`
要求签名（校验和只证明没被改，签名才证明谁打的）。

### 12.5 发布流程（打 tag 才打包）

**只有用户明确要求打 tag 时才执行发布打包**；Release 说明保持简要
（指向 CHANGELOG，不写详版）。清单：

1. 两处版本号改成同一值（3.2），跑 Python 测试 + CTest 全绿。
2. 决定取舍：`dist\Panda\voices` 的私密音色不会进资产（自动排除），无需手动清理；
   若要绝对保险，打包前手动清空 `dist\Panda\voices`。
3. 打包：`.\scripts\package_windows.ps1 -BundlePython -BundleMeanVC2`
   （终端**不要**用 `2>&1 | Tee` 转发——脚本 `$ErrorActionPreference=Stop`
   会把 windeployqt 的良性 stderr 警告当致命错误；要留日志用
   `cmd /c "... > log 2>&1"` 级重定向）。
4. 换路径验收（模拟换机）：把四个资产解压到一个**全新的空路径**，清掉
   `PANDA_*`/`PYTHONPATH`，依次跑：
   ```powershell
   python\python.exe -m panda_cli doctor --meanvc2-root <解压目录>\MeanVC2 `
     --deepfilter-root <解压目录>\DeepFilterNet\DeepFilterNet3
   # （PYTHONPATH 指向 <解压目录>\share\python）
   panda simulate --meanvc2-root ... --input ... --output ...   # 真实跑一次变声
   launch.cmd                                                    # 界面能开
   ```
5. 打 tag（与版本号一致，如 `v1.0.0`）并推送。
6. GitHub Release：建 tag 对应 Release，上传四资产，说明**简要**
   （版本亮点 3–5 行 + 资产表 + 指向 CHANGELOG）。
7. 合规核对：README「许可」的组件表与实际捆绑一致；`third_party/notices/`
   中每个捆绑组件都有对应许可证原文（Qt 为 LGPL 动态链接，需随包附
   许可证文本与源码获取说明）。

> 1.0.0 发布前验收已执行并全绿（2026-10-04）：四资产解压到 C 盘全新路径、
> 环境变量全裸，`doctor` 零错误，真实模型 `simulate --fast` RTF 0.32、
> 零下溢零丢帧，`launch.cmd` 拉起界面 23 秒无崩溃、正常退出。
> 打包过程中 360 安全大脑对"批量哈希 + 复制 DLL"启发式报警为误报，
> 产物已按 manifest 逐文件核对完整（缺 0）。

### 12.6 打包注意事项

- windeployqt 良性警告（dxcompiler/dxil）会被 PowerShell 重定向放大：
  转发 stderr 必须在 cmd 层做，见 12.5-3。
- 5 万文件突发解压可能被终端防护拒写个别文件（实测 ucrtbase.dll ENOENT），
  脚本已对运行时解压加重试；重放同条目必定成功说明是瞬时故障。
- `windeployqt` 对刚复制的 exe 加锁时会重试 3 次（EDR 扫描）。
- 打包取材均来自本仓库目录（build 产物、`.tools` 的 conda/Qt、
  `deps\MeanVC2`），大文件不进 git。
- conda 环境自带 vcruntime140/msvcp140 全套，运行时**不需要**目标机装
  VC++ redist。

## 13. 决策记录

| 决策 | 理由 |
| --- | --- |
| 音色包明文开放 | 可检查、可备份、可迁移、可被工具链处理、社区可贡献 |
| MeanVC2 优先 | 低延迟流式、Apache-2.0、模型轻、CPU 可跑、官方训练代码公开 |
| 公共模型与音色资源解耦 | 客户端、公共模型、音色包各自独立发布与版本化 |
| 推理留在 Python 引擎进程 | RTF 0.757 零下溢已验证；ONNX 化被 DiT trace 卡死，收益只有打包体积 |
| 引擎子进程 + stdout/stdin 协议 | 崩溃隔离、语言无关、指标可测试；Named Pipe/JSON-RPC 属未定，未实现 |
| 默认 120ms 变体 | 每块耗时一半、缓冲小一个量级、恒等保持更好（见 6.1） |
| v1 虚拟声卡依赖用户自装 | 内核驱动需管理员 + EV 签名，违背零门槛安装 |
| 三应用包 + 工具包的四资产发布 | 单文件 2 GiB 上限；三包同目录解压即用；工具包不带环境 |
| 单线程推理 | batch=1 小模型实测单线程最快（见 6.2） |
| 版本号双来源 + 一致性测试 | 两语言生态解耦，但发版必须同值，由测试强制 |

## 14. 路线图（均未排期，属"待定"）

1. **打包瘦身**：清零引用训练杂物（wandb/sklearn/matplotlib/numba/librosa/
   transformers）、砍 40ms 备选模型（省 ~300 MB）、核实 WavLM 1.24 GB 是否可
   精简——不阻塞发布。
2. **ONNX 化去 Python**：vocoder/ASR 已导出，卡在 DiT 流式路径的可 trace 重写。
3. **帧级引擎**：只有"延迟要压到 150 ms 量级"成为优先级时才做。
4. **代码签名**：管线已实现并测试（`-CertificateThumbprint`），只差证书。
5. **自带签名虚拟声卡驱动**：EV 证书 + 管理员安装 + 内核驱动开发。
6. GPU/CUDA 可选加速、RVC/DSP 后端、音高变换、Linux/macOS——均为设计预留，
   未开始。

## 15. 文档与提交规范

- 文档只有三份：`README.md`（产品）、`docs/DEVELOPMENT.md`（本文）、
  `CHANGELOG.md`（更新日志）；界面改动必须更新截图。
- 文档和代码在同一个提交中更新；命令示例必须可复制执行；
  配置示例标明路径基准；协议字段必须有版本与兼容规则；
  音色包格式变更必须写迁移说明；未确定的决策标"待定"，不写成已支持。
- 提交类型：`feat:` `fix:` `docs:` `test:` `refactor:` `build:` `chore:`。
- Definition of Done：有自动化测试、有错误处理与用户提示、有性能数据、
  有日志与诊断、有文档更新、有回滚/降级路径、不引入未记录的运行时依赖。
