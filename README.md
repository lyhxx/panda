# 熊猫变声器 (Panda Voice Changer)

开源、免费、**本地优先**的实时变声器。麦克风的声音在本机实时换成目标音色——
无账号、无云端、无水印，音频不出这台电脑。

- **CPU 就能实时跑**：无需显卡，实测 RTF 0.32–0.76，连续 30 分钟零音频卡顿
- **液态玻璃界面**：浅色 / 深色 / 跟随系统三主题
- **音色包生态**：一行命令把任意音频打成可校验的 `.zip` 音色包，界面里单个或批量安装
- **实时降噪**（DeepFilterNet 三档）、噪声门、软限幅、耳机监听
- **绿色版零安装**：解压即用，不需要 Python、不需要管理员权限

系统要求：Windows 10/11 x64。

## 下载与使用

从 [Releases](../../releases) 下载四个资产：

| 资产 | 内容 | 大小 |
| --- | --- | --- |
| `Panda-1.0.0.zip` | 主程序（exe、Qt 运行库、引擎、启动脚本） | ~40 MB |
| `Panda-runtime.zip` | Python 运行时 + 降噪模型 | ~0.6 GB |
| `Panda-Models.zip` | 变声模型 | ~1.7 GB |
| `Panda-Pack.zip` | 音色包导出工具（可选，不带环境） | 几 MB |

**三个应用包解压到同一个空文件夹**（会并排合并），然后双击 `launch.cmd`：

```text
新建空文件夹
  ├── Panda-1.0.0.zip   ─┐
  ├── Panda-runtime.zip  ├──► 全部解压到此 → panda_desktop.exe / launch.cmd
  └── Panda-Models.zip   ─┘                 python\  MeanVC2\  DeepFilterNet\
                                                 │
                                          双击 launch.cmd
```

启动脚本自动定位所有组件，不需要设置任何环境变量，盘符和路径随意。

### 让游戏 / 直播软件听到你

Discord、游戏、OBS 只认"麦克风"，需要一块虚拟声卡当桥（一次性安装）：

1. 下载安装 [VB-CABLE](https://www.vb-cable.com/)（解压 → 右键管理员运行 → 重启）
2. 熊猫变声器的「输出」选 `CABLE Input`（带虚拟声卡标记）
3. 对方软件的「麦克风」选 `CABLE Output`

自己想听见自己：「监听输出」选耳机即可（独立一路，不互相抢占）。

## 音色包

- 界面内「安装音色包」支持单个安装、多选批量安装，带进度与失败原因。
- 已装音色只存在本机 `voices\` 目录：**不进任何仓库、不随 Release 分发**、升级不丢。
- 自己制作：下载 `Panda-Pack.zip`，解压后按其中 `README.txt` 用一段干净人声
  导出标准音色包（支持 WAV/MP3/FLAC/OGG 等输入）。

## 文档

| 文档 | 内容 |
| --- | --- |
| [CHANGELOG](CHANGELOG.md) | 版本更新日志 |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | 开发：环境搭建、架构、测试、打包与发布全流程 |

源码构建、贡献流程、音色包格式规范、训练指南都在 DEVELOPMENT 里。

## 许可

Apache License 2.0，见 [LICENSE](LICENSE)。第三方声明见
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

---

## 界面截图

**主界面**：音色卡片网格、搜索、批量安装、三主题切换、底部控制条

![主界面](docs/images/after_main_window.png)

**设置 · 音频**：输出/输入/监听设备、音量、噪声门、降噪、延迟档位

![设置-音频](docs/images/after_settings_audio.png)

**设备选择**：WASAPI 过滤、虚拟声卡标记

![设备选择](docs/images/after_device_dropdown.png)

**深色主题**

![深色主题](docs/images/after_settings_dark.png)
