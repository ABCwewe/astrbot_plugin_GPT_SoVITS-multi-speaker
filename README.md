<div align="center">

# astrbot_plugin_GPT_SoVITS_multi_speaker

_GPT-SoVITS 对接插件（TTS）- 多说话人版本_

[![License](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0.html)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-4.0%2B-orange.svg)](https://github.com/Soulter/AstrBot)
[![Version](https://img.shields.io/badge/version-v3.3.0-blue.svg)](https://github.com/ABCwewe/astrbot_plugin_GPT_SoVITS_multi_speaker)
[![GitHub](https://img.shields.io/badge/原作者-Zhalslar-blue)](https://github.com/Zhalslar)
[![GitHub](https://img.shields.io/badge/作者-ABCwewe-blue)](https://github.com/ABCwewe)

</div>

---

## 1. 介绍

本插件基于[astrbot_plugin_GPT_SoVITS](https://github.com/Zhalslar/astrbot_plugin_GPT_SoVITS)修改，感谢[@Zhalslar](https://github.com/Zhalslar)

`astrbot_plugin_GPT_SoVITS_multi_speaker` 用于把 AstrBot 文本输出转换成语音输出，支持多说话人切换，底层调用 [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) 的 API。

**v3.3.0 新增功能**：
- **可视化配置页面（Plugin Pages）**：重构前端配置，提供简约美观的 WebUI 可视化页面，支持说话人管理、情绪可视化编辑、TTS 参数、自动触发、情感判断、缓存等全部配置项
- **情绪可视化编辑器**：情绪配置从 JSON 代码编辑器升级为卡片式可视化编辑器，支持关键词标签输入、滑块调节语速/间隔
- **自然语言触发语音合成**：「说」指令从注册指令改为 on-message hook，支持 `<说话人><情绪>说 <文本>` 自然语言结构，无需唤醒前缀
- **隐藏复杂配置**：`_conf_schema.json` 中除总开关外的配置项设为不可见，统一通过 Pages 页面管理

**v3.2.2 功能**：
- **修复模型加载**：现在不会只加载默认模型了
- **指令触发可以不调用情感识别**：增加了一个开关控制
- **只有一个情感预设跳过LLM**：避免LLM浪费

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
git clone https://github.com/ABCwewe/astrbot_plugin_GPT_SoVITS_multi_speaker.git
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

插件提供两种配置入口：

**方式一：可视化配置页面（推荐）**

路径：`插件管理 -> GPT_SoVITS-multi-speaker -> 操作 -> 插件页面 -> settings`

在配置页面中可以：
1. **基础设置**：开关插件、选择默认说话人
2. **说话人管理**：可视化增删改说话人，配置模型路径、API 地址、合成语言等
3. **情绪可视化编辑**：每个情绪以卡片形式展示，支持关键词标签式输入、滑块调节语速/间隔
4. **TTS 参数 / 自动触发 / 情感判断 / 缓存设置**：全功能可视化配置

**方式二：标准插件配置**

路径：`插件管理 -> GPT_SoVITS-multi-speaker -> 操作 -> 插件配置`

> 注意：v3.3.0 起标准配置面板仅显示「总开关」一项，其余配置请通过插件页面管理。

**配置项说明**：
1. `enabled`：插件总开关
2. `default_speaker`：默认说话人名称
3. `speakers`：说话人列表，每个说话人包含：
   - `speaker_name`：说话人名称
   - `alias`：说话人别名（逗号分隔）
   - `gpt_path`：GPT 模型路径
   - `sovits_path`：SoVITS 模型路径
   - `base_url`：API 地址
   - `timeout`：API 超时时间
   - `text_lang`：默认合成语言
   - `emotions`：情绪列表

### 3.3 验证是否可用

在聊天中发送（无需唤醒前缀）：

```text
说 你好，我是语音测试
```

也可以指定说话人和情绪：

```text
角色1说 你好，我是角色1
角色1开心说 今天真开心！
```

若收到语音消息，说明链路已打通。

---

## 4. 命令与调用方式

### 4.1 语音合成（on-message hook）

v3.3.0 起，「说」从注册指令改为 on-message hook，支持自然语言结构，**无需唤醒前缀**：

| 格式 | 说明 |
| ----- | ----- |
| `说 <文本>` | 使用默认说话人合成语音 |
| `<说话人>说 <文本>` | 使用指定说话人合成语音 |
| `<说话人><情绪>说 <文本>` | 使用指定说话人和情绪合成语音 |
| `<情绪>说 <文本>` | 使用默认说话人的指定情绪合成语音 |

**示例**：
```
说 你好                        # 使用默认说话人
丹瑾说 你好，我是丹瑾          # 使用说话人「丹瑾」
丹瑾生气说 不喜欢你             # 使用「丹瑾」的「生气」情绪
开心说 今天真开心              # 使用默认说话人的「开心」情绪
```

> 说话人名称支持别名匹配（在配置页面的「别名」字段设置）。情绪名称和说话人名称按长度优先匹配，避免短名称误匹配。

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

1. **指令指定情绪**（最高优先级）：`丹瑾生气说 XXX`
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

> v3.3.0 起推荐通过插件页面（Pages）进行可视化配置，以下为字段参考。

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
| `alias` | 说话人别名（逗号分隔） | 指令中可使用的别名 |
| `gpt_path` | GPT 权重路径（`.ckpt`） | 可空，使用 GPT-SoVITS 默认模型 |
| `sovits_path` | SoVITS 权重路径（`.pth`） | 可空，使用 GPT-SoVITS 默认模型 |
| `base_url` | GPT-SoVITS API 地址 | 常见为 `http://127.0.0.1:9880` |
| `timeout` | API 请求超时时间（秒） | 网络慢或长文本可适当调大 |
| `text_lang` | 默认合成语言 | `zh`/`en`/`ja`/`ko`/`zh_ja_auto` |
| `emotions` | 情绪配置列表 | 至少配置一个情绪 |

### 6.3 情绪配置（`emotions`）

每个情绪包含：

| 字段 | 说明 | 建议/取值 |
| --- | --- | --- |
| `name` | 情绪名称 | 用于指令中指定，如「开心」「生气」 |
| `keywords` | 触发关键词列表 | 文本包含时自动匹配此情绪 |
| `ref_audio_path` | 参考音频路径 | `.wav` 格式 |
| `prompt_text` | 参考音频对应文本 | 参考音频中说的话 |
| `prompt_lang` | 参考音频语言 | `zh`/`en`/`ja`/`ko` |
| `speed_factor` | 语速倍数 | `1.0` 为正常速度 |
| `fragment_interval` | 片段间隔 | 控制语音片段之间的停顿 |

### 6.4 TTS 全局参数（`tts_params`）

| 字段 | 说明 | 建议/取值 |
| --- | --- | --- |
| `media_type` | 输出音频格式 | `wav`/`mp3`/`ogg`，建议 `wav` |
| `text_split_method` | 文本切分方式 | `cut0`~`cut5`，默认 `cut3` |
| `batch_size` | 推理批大小 | 越大越快但越占显存 |
| `batch_threshold` | 批处理阈值 | 控制是否拆分批次 |
| `parallel_infer` | 启用并行推理 | 建议开启 |
| `split_bucket` | 启用分桶推理 | 建议开启 |

### 6.5 自动转语音配置（`auto`）

| 字段 | 说明 | 建议/取值 |
| --- | --- | --- |
| `only_llm_result` | 只处理 LLM 生成的回复 | 建议 `true` |
| `tts_prob` | 自动转语音概率 | `0 ~ 1`，例如 `0.15` |
| `max_msg_len` | 自动转语音的最大文本长度 | 超过该值不转语音 |

### 6.6 情感判断配置（`judge`）

| 字段 | 说明 | 建议/取值 |
| --- | --- | --- |
| `enabled_llm` | 是否启用 LLM 判别情绪 | 不开则仅走关键词匹配 |
| `enabled_command` | 指令触发时是否启用 LLM 情感判断 | 关闭时所有指令合成跳过 LLM 判断 |
| `provider_id` | 用于情绪判别的模型提供商 ID | 留空时跟随当前会话模型 |

### 6.7 缓存配置（`cache`）

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

**建议**：迁移完成后，通过插件页面（Pages）重新检查配置。

---

## 10. 可视化配置页面（Plugin Pages）

v3.3.0 新增可视化配置页面，提供比标准配置面板更友好的配置体验。

### 10.1 访问方式

`插件管理 -> GPT_SoVITS-multi-speaker -> 操作 -> 插件页面 -> settings`

### 10.2 功能概览

| 标签页 | 功能 |
| ----- | ----- |
| **基础设置** | 插件开关、默认说话人选择 |
| **说话人管理** | 左右分栏式说话人增删改，支持别名、模型路径、API 地址、合成语言 |
| **TTS 参数** | 音频格式、切分方式、批大小、并行推理等全局参数 |
| **自动触发** | 概率触发、文本长度限制、只处理 LLM 结果 |
| **情感判断** | LLM 情感判断开关、提供商选择 |
| **缓存设置** | 缓存开关、过期时间、缓存路径 |

### 10.3 情绪可视化编辑器

说话人管理页面内置情绪可视化编辑器：
- **卡片式展示**：每个情绪以可折叠卡片形式展示，头部显示名称和关键词标签
- **关键词标签输入**：输入关键词后回车添加，点击 × 删除
- **滑块调节**：语速、片段间隔使用滑块直观调节
- **实时预览**：修改即时反映到配置中，点击保存生效

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
