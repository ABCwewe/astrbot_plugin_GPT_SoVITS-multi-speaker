<div align="center">

# astrbot_plugin_GPT_SoVITS-multi-speaker

_GPT-SoVITS 对接插件（TTS）- 多说话人版本_

[![License](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0.html)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-4.0%2B-orange.svg)](https://github.com/Soulter/AstrBot)
[![GitHub](https://img.shields.io/badge/原作者-Zhalslar-blue)](https://github.com/Zhalslar)
[![GitHub](https://img.shields.io/badge/作者-ABCwewe-blue)](https://github.com/ABCwewe)

</div>

---

## 1. 介绍

本插件基于[astrbot_plugin_GPT_SoVITS](https://github.com/Zhalslar/astrbot_plugin_GPT_SoVITS)修改，感谢[@Zhalslar](https://github.com/Zhalslar)

`astrbot_plugin_GPT_SoVITS-multi-speaker` 用于把 AstrBot 文本输出转换成语音输出，支持多说话人切换，底层调用 [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) 的 API。

**v3.2.0 新增功能**：
-  **多说话人支持**：每个说话人有独立的模型、服务器和情绪配置
-  **实时切换**：通过指令实时切换说话人和情绪
-  **情绪优先级**：指令指定情绪 > LLM 判断情绪 > 关键词匹配情绪

支持三种调用方式：
1. 指令转语音：手动输入命令立即合成语音。
2. 自动转语音：Bot 正常回复文本时，按概率自动转成语音发出。
3. 工具调用：LLM 工具调用时，GPT-SoVITS 会作为 LLM 工具的 TTS 接口。

此外还支持情绪参数切换（按关键词或 LLM 判别情绪），实现不同语气/语速的播报效果。

---

## 2. 安装

### 2.1 部署 GPT-SoVITS

请先完成 GPT-SoVITS 本体部署：

- 官方仓库：[RVC-Boss/GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS)
- 参考指南：[GPT_SoVITS 指南](https://www.yuque.com/baicaigongchang1145haoyuangong/ib3g1e)

### 2.2 安装 AstrBot 插件

```
cd AstrBot/data/plugins    #移动到插件目录
git clone https://github.com/ABCwewe/astrbot_plugin_GPT_SoVITS-multi-speaker.git
```

---

## 3. 快速开始

### 3.1 启动 GPT-SoVITS API

Windows 示例（在 GPT-SoVITS 根目录新建 `start_api.bat`）：

```bat
runtime\python.exe api_v2.py
pause
```

或直接命令行启动：

```bash
python api_v2.py
# 或
python3 api_v2.py
```

### 3.2 在 AstrBot 面板配置插件

路径：`插件管理 -> astrbot_plugin_GPT_SoVITS -> 操作 -> 插件配置`

**新增配置项**：
1. `default_speaker`：默认说话人名称
2. `speakers`：说话人列表，每个说话人包含：
   - `speaker_name`：说话人名称
   - `gpt_path`：GPT 模型路径
   - `sovits_path`：SoVITS 模型路径
   - `base_url`：API 地址
   - `emotions`：情绪列表

### 3.3 验证是否可用

在聊天中发送：

```text
说 你好，我是语音测试
```

若收到语音消息，说明链路已打通。

---

## 4. 命令与调用方式

### 4.1 基础指令

| 命令 | 别名 | 说明 |
| ----- | ----- | ----- |
| `说 <文本>` | `gsv <文本>`、`GSV <文本>` | 使用默认说话人合成语音 |
| `说 <说话人> <文本>` | - | 使用指定说话人合成语音 |
| `说 <说话人> <情绪> <文本>` | - | 使用指定说话人和情绪合成语音 |

**示例**：
```
说 你好                        # 使用默认说话人
说 B 你好                      # 使用说话人 B
说 B 开心 你好                 # 使用说话人 B 的开心情绪
说 开心 你好                   # 使用默认说话人的开心情绪（如果匹配到）
```

### 4.2 管理指令

| 命令 | 说明 |
| ----- | ----- |
| `设置默认说话人 <名称>` | 设置全局默认说话人 |
| `GSV 列表` | 列出所有可用说话人 |
| `GSV 当前` | 查看当前默认说话人 |
| `重启 GSV` | 请求 GPT-SoVITS 执行重启 |

### 4.3 自动调用与工具调用

- **概率调用**：Bot 回复阶段按概率自动转语音（配置见 `auto` 节）
- **工具调用**：LLM 可通过 `gsv_tts` 工具主动调用 TTS

---

## 5. 情绪功能说明

### 5.1 情绪匹配优先级

1. **指令指定情绪**（最高优先级）：`说 B 开心 XXX`
2. **LLM 判断情绪**：开启 `judge.enabled_llm` 后自动判断
3. **关键词匹配**：文本包含情绪关键词时匹配

### 5.2 情绪配置

每个说话人可配置多个情绪，每个情绪包含：
- `name`：情绪名称
- `keywords`：触发词列表
- `ref_audio_path`：参考音频路径
- `prompt_text`：参考音频文本
- `speed_factor`：语速倍数
- `fragment_interval`：片段间隔

---

## 6. 配置说明

### 6.1 基础配置

| 字段 | 说明 | 建议/取值 |
| --- | --- | --- |
| `enabled` | 插件总开关 | 部署完成后开启 |
| `default_speaker` | 默认说话人名称 | 必须存在于 speakers 列表中 |

### 6.2 说话人配置（`speakers`）

每个说话人包含：

| 字段 | 说明 | 建议/取值 |
| --- | --- | --- |
| `speaker_name` | 说话人名称（唯一标识） | 建议使用英文或拼音 |
| `gpt_path` | GPT 权重路径（`.ckpt`） | 可空，使用 GPT-SoVITS 默认模型 |
| `sovits_path` | SoVITS 权重路径（`.pth`） | 可空，使用 GPT-SoVITS 默认模型 |
| `base_url` | GPT-SoVITS API 地址 | 常见为 `http://127.0.0.1:9880` |
| `timeout` | API 请求超时时间（秒） | 网络慢或长文本可适当调大 |
| `emotions` | 情绪配置列表 | 至少配置一个情绪 |

### 6.3 自动转语音配置（`auto`）

| 字段 | 说明 | 建议/取值 |
| --- | --- | --- |
| `only_llm_result` | 只处理 LLM 生成的回复 | 建议 `true` |
| `tts_prob` | 自动转语音概率 | `0 ~ 1`，例如 `0.15` |
| `max_msg_len` | 自动转语音的最大文本长度 | 超过该值不转语音 |

### 6.4 情感判断配置（`judge`）

| 字段 | 说明 | 建议/取值 |
| --- | --- | --- |
| `enabled_llm` | 是否启用 LLM 判别情绪 | 不开则仅走关键词匹配 |
| `provider_id` | 用于情绪判别的模型提供商 ID | 留空时跟随当前会话模型 |

### 6.5 缓存配置（`cache`）

| 字段 | 说明 | 建议/取值 |
| --- | --- | --- |
| `enabled` | 是否启用参数级缓存 | 建议开启 |
| `expire_hours` | 缓存过期时间（小时） | `0` 表示永不过期 |
| `path` | 缓存目录 | 支持相对/绝对路径 |

## 7.生成配置文件
如果你的模型数量众多可以使用下面的目录结构放置模型文件和参考音频，运行本插件提供的python脚本生成配置文件
```
├─丹瑾_ZH
│  │  train.log
│  │  丹瑾_ZH-e10.ckpt
│  │  丹瑾_ZH_e10_s140_l32.pth
│  │
│  └─reference_audios
│      └─中文
│          └─emotions
│                  【默认】能开出龙须酥就好了…….wav
│
├─今汐_ZH
│  │  train.log
│  │  今汐_ZH-e10.ckpt
│  │  今汐_ZH_e10_s240_l32.pth
│  │
│  └─reference_audios
│      └─中文
│          └─emotions
│                  【默认】……到了那时，又怎么会有人甘愿为寰宇间的盈尺之地穷尽山海？.wav
│
├─卡提希娅_ZH
│  │  train.log
│  │  卡提希娅_ZH-e10.ckpt
│  │  卡提希娅_ZH_e10_s310_l32.pth
│  │
│  └─reference_audios
│      └─中文
│          └─emotions
│                  【默认】不过，我建议你现在最好去找坎特蕾拉聊聊，她应该已经安全离开索诺拉了，我能感觉到。.wav
```
然后在该目录下运行 `generate_speakers_config.py`
```
python3 generate_speakers_config.py
```

## 8. 常见问题与排查

### 8.1 提示"说话人不存在"
- 使用 `/GSV 列表` 查看可用说话人
- 检查说话人名称是否与配置一致

### 8.2 提示"合成失败"
优先检查：
1. GPT-SoVITS API 是否已启动；
2. `base_url` 是否正确；
3. 参考音频文件是否存在；
4. GPT-SoVITS 控制台是否有报错信息。

### 8.3 自动模式没有触发
常见原因：
1. `tts_prob` 太低；
2. 回复文本超过 `max_msg_len`；
3. 回复里包含图片/语音等非纯文本片段；
4. `only_llm_result=true` 且该消息不是 LLM 输出。

### 8.4 情绪没有切换
1. 若使用关键词模式，确认关键词确实出现在回复文本中；
2. 若使用 LLM 模式，确认 `judge.enabled_llm` 已开启；
3. 确认目标情绪条目存在于该说话人的 `emotions` 列表中。

---

## 9. 旧配置迁移

首次使用时会自动迁移旧配置格式：
- 原有 `client`、`model` 配置会合并为默认说话人
- 原有 `entry_storage` 会转换为默认说话人的情绪列表
- 原有 `default_params` 作为基础参数

**建议**：迁移完成后，通过 WebUI 重新检查配置。

---

## 👥 贡献指南

- 🌟 Star 这个项目！（点右上角的星星，感谢支持！）
- 🐛 提交 Issue 报告问题
- 💡 提出新功能建议
- 🔧 提交 Pull Request 改进代码

## 📌 注意事项

- 本插件优先兼容 GPT-SoVITS 官方实现与常见整合包。若使用第三方魔改版本，请以其 API 实际行为为准。

## 🙏 致谢

[GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS)，1 min voice data can also be used to train a good TTS model! (few shot voice cloning)

[astrbot_plugin_GPT_SoVITS](https://github.com/Zhalslar/astrbot_plugin_GPT_SoVITS)，astrbot_plugin_GPT_SoVITS 用于把 AstrBot 文本输出转换成语音输出，底层调用 GPT-SoVITS 的 API。
