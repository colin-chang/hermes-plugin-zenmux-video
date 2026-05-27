# Hermes  ZenMux 视频生成插件

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Hermes](https://img.shields.io/badge/Hermes-≥%200.7.0-blue)](https://github.com/nousresearch/hermes-agent)

[English Version](./README.md) | 中文版本

让你的 Hermes AI 助手会拍视频——一个 API Key 接入 5 家视频生成模型，文字或图片都能变成视频。

---

## 😵‍💫 这是什么？

**一句话：** 这个插件让 Hermes 会生成视频。你对它说"拍一段海浪拍打礁石的视频"，它就能生成。

Hermes 本身只会聊天，不会生成视频。这个插件通过 [ZenMux](https://zenmux.ai/invite/1C3QLF) 的 API 网关，一口气接入了 **Google、字节跳动、阿里巴巴** 三家的 5 个视频生成模型。你只需要一个 ZenMux API Key，不用去每家分别注册。

---

## ✨ 它支持哪些模型？

| 模型 | 厂商 | 速度 | 音频 | 适合场景 |
|------|------|------|------|---------|
| **Veo 3.1** | Google | ~60-120 秒 | ✅ | 最高质量，电影级画面 |
| **Veo 3.1 Fast** | Google | ~30-60 秒 | ✅ | 速度快且质量高，推荐日常用 |
| **Veo 3.1 Lite** | Google | ~20-45 秒 | ❌ | 经济实惠，快速出片 |
| **Seedance 2.0** | 字节跳动 | ~45-90 秒 | ✅ | 支持负向提示词，精确控制画面 |
| **Happy Horse 1.0** | 阿里巴巴 | ~30-60 秒 | ❌ | 经济实惠，支持负向提示词 |

### 两种生成方式

- **文字生视频（Text-to-Video）**：写一段描述，生成视频。所有模型都支持。
- **图片生视频（Image-to-Video）**：给一张静态图片，让画面动起来。所有模型都支持。

> 比如上传一张海浪照片，说"让海浪动起来，添加日落光影"。
 
---

## 🚀 快速上手（4 步）

### 前提条件

- ✅ 已经在用 [Hermes Agent](https://github.com/nousresearch/hermes-agent)（版本 ≥ 0.7.0）
- ✅ 有一个 [ZenMux](https://zenmux.ai/invite/1C3QLF) 账号和 API Key
- ✅ Python 3.11+

---

### 第 1 步：安装插件

```bash
hermes plugins install colin-chang/hermes-plugin-zenmux-video --enable
```

### 第 2 步：安装 SDK 依赖

这个插件需要 Google 的 `google-genai` SDK（ZenMux 用 Vertex AI 协议对接视频模型）：

```bash
pip install google-genai
```

> 💡 如果用的是 Hermes 自带的 Python 环境，确认装到了正确的地方。

### 第 3 步：配置 API Key

打开 `~/.hermes/.env`，添加一行：

```bash
ZENMUX_API_KEY=你的ZenMux密钥
```

### 第 4 步：配置视频生成后端

在 `~/.hermes/config.yaml` 中添加：

```yaml
video_gen:
  provider: zenmux-video
  model: google/veo-3.1-fast-generate-001   # 默认模型，可改
```

重启 Hermes 后生效。现在对 Hermes 说"生成一段海浪拍打礁石的视频"试试。

---

## 📖 使用指南

### 文字生成视频

跟你平常聊天一样描述就好：

> 生成一段视频：一只橘猫在夕阳下的花园里漫步，电影级光影效果，10 秒

> 用 Veo 拍一段：无人机视角飞越雪山，云雾缭绕

### 图片生成视频

如果你之前让 Hermes 生成了一张图，可以让它"把这张图变成视频"：

> 把刚才那张海浪照片动画化：让海浪拍打起来，加上日落光影

> 让这张城市夜景的图动起来：车流穿梭，灯光闪烁

### 切换模型

**方式一：在提示词里直接说**（不用改配置）

- 说"用 **Veo** 生成……" → 自动选 Veo 3.1
- 说"用 **Seedance** 生成……" → 自动选 Seedance 2.0
- 说"用 **Happy Horse** 生成……" → 自动选 Happy Horse 1.0

**方式二：改配置文件**

```yaml
video_gen:
  zenmux:
    model: bytedance/doubao-seedance-2.0
```

**方式三：环境变量**

```bash
export ZENMUX_VIDEO_MODEL=alibaba/happyhorse-1.0
```

### 模型选择优先级

当多种方式同时存在时，优先级从高到低：

1. 提示词里的关键词（如"用 Veo 生成"→ 自动选 Veo 3.1）
2. `ZENMUX_VIDEO_MODEL` 环境变量
3. `video_gen.zenmux.model` 配置文件
4. `video_gen.model` 配置文件
5. 默认模型：`google/veo-3.1-fast-generate-001`

---

## 🧱 它是怎么工作的？

```
你说"拍一段海浪视频" ──→ Hermes ──→ 这个插件 ──→ ZenMux API ──→ Google / 字节跳动 / 阿里巴巴
                                         │
                                    ZenMux 充当"翻译官"：
                                    不管你选哪个厂商的模型，
                                    都用同一个 API Key 调用
```

视频生成比图片慢很多——不能像图片那样"说画就画"。它分成三步：

1. **提交请求**：插件把你要的画面描述发给 ZenMux
2. **排队等待**：每 10 秒检查一次"好了没"，最长等 5 分钟
3. **下载视频**：生成完成后自动下载到本地，聊天里直接播放

---

## ❓ 常见问题

**Q: 我需要分别注册 Google、字节跳动、阿里的账号吗？**

A: 不需要。你只需要一个 ZenMux 账号，一个 API Key 就能用所有模型。

**Q: 为什么生成视频这么慢？**

A: 视频生成比图片生成复杂得多，需要几秒到 2 分钟。具体取决于模型和视频时长。日常用推荐 **Veo 3.1 Fast**（30-60 秒，性价比最高）。

**Q: 有哪些模型能生成带声音的视频？**

A: Veo 3.1、Veo 3.1 Fast、Seedance 2.0 三个支持音频。Veo 3.1 Lite 和 Happy Horse 不支持。

**Q: 能控制视频的时长和分辨率吗？**

A: 可以。在提示词里说明就行，比如"生成一段 8 秒 1080p 的视频"。但不同模型的上限不同——比如 Veo 3.1 Lite 最高只有 720p，最长 8 秒。具体看上面的能力对比表。

**Q: 负向提示词是什么？**

A: 就是告诉 AI "不要什么"。比如"生成城市夜景，**不要有雾**，**不要有人**"。Seedance 2.0 和 Happy Horse 1.0 支持这个功能。

**Q: 视频保存在哪里？**

A: Hermes 自动保存到本地缓存，聊天里直接可以播放。

---

## 📁 项目结构

```
zenmux-video/
├── plugin.yaml              # 插件元数据
├── __init__.py              # 插件入口（VideoGenProvider 实现）
├── README.md                # 英文文档
├── README.zh-CN.md          # 本文档
├── LICENSE                  # MIT
└── .gitignore
```

---

## 📄 许可

MIT — 详见 [LICENSE](LICENSE)
