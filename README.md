# Hermes ZenMux Video Generation Plugin

Hermes Agent 视频生成插件，通过 [ZenMux](https://zenmux.ai) Vertex AI Compatible API 接入多家视频生成模型。

## 支持的模型

| 模型 | 厂商 | 特点 | 价格档 |
|---|---|---|---|
| `google/veo-3.1-generate-001` | Google | 最高质量，支持音频 | Premium |
| `google/veo-3.1-fast-generate-001` | Google | 快速生成，支持音频 | Premium |
| `google/veo-3.1-lite-generate-001` | Google | 经济实惠 | Affordable |
| `bytedance/doubao-seedance-2.0` | 字节跳动 | 支持音频和负向提示词 | Premium |
| `alibaba/happyhorse-1.0` | 阿里巴巴 | 支持负向提示词 | Affordable |

所有模型均支持 **文本生成视频 (text-to-video)** 和 **图片生成视频 (image-to-video)**。

## 安装

```bash
hermes plugins install colin-chang/hermes-plugin-zenmux-video --enable
```

## 配置

### 1. 设置 API Key

```bash
# 在 ~/.hermes/.env 或环境变量中添加
ZENMUX_API_KEY=your_zenmux_api_key
```

在 [ZenMux](https://zenmux.ai/settings/api-keys) 获取 API Key。

### 2. 配置 config.yaml

在 `~/.hermes/config.yaml` 中添加：

```yaml
plugins:
  enabled:
    - zenmux-video

video_gen:
  provider: zenmux-video
  model: google/veo-3.1-fast-generate-001  # 可选，默认使用此模型
```

### 3. 安装 SDK 依赖

```bash
# 插件需要 google-genai SDK
uv pip install --python $(which hermes | xargs head -1 | sed 's|#!/usr/bin/env bash||') google-genai
# 或
pip install google-genai
```

> **注意：** 需要安装到 Hermes Agent 使用的 Python 环境中。

## 使用示例

### 文本生成视频

```
请用 Veo 3.1 生成一段视频：一只猫在花园里散步，电影级光影效果
```

### 图片生成视频

```
请把这张图片动画化：让海浪动起来，添加日落光影效果
```

### 指定模型

```
用 Seedance 2.0 生成一段视频：海浪拍打礁石，航拍视角
```

## 模型选择逻辑

优先级从高到低：

1. 工具调用中显式指定的 `model` 参数
2. 提示词中的关键词匹配（如 "veo"、"seedance"、"happy horse"）
3. `ZENMUX_VIDEO_MODEL` 环境变量
4. `video_gen.zenmux.model` 配置项
5. `video_gen.model` 配置项
6. 默认模型：`google/veo-3.1-fast-generate-001`

## 模型能力对比

| 能力 | Veo 3.1 | Veo 3.1 Fast | Veo 3.1 Lite | Seedance 2.0 | Happy Horse |
|---|---|---|---|---|---|
| Text-to-Video | ✅ | ✅ | ✅ | ✅ | ✅ |
| Image-to-Video | ✅ | ✅ | ✅ | ✅ | ✅ |
| 音频生成 | ✅ | ✅ | ❌ | ✅ | ❌ |
| 负向提示词 | ❌ | ❌ | ❌ | ✅ | ✅ |
| 分辨率 | 720p/1080p | 720p/1080p | 480p/720p | 720p/1080p | 480p/720p |
| 宽高比 | 16:9/9:16/1:1 | 16:9/9:16/1:1 | 16:9/9:16 | 16:9/9:16/1:1 | 16:9/9:16/1:1 |
| 时长范围 | 5-15s | 5-10s | 4-8s | 5-10s | 4-10s |

## 异步生成流程

视频生成采用异步轮询机制：

1. 提交生成请求 → 返回 Operation
2. 定期轮询 Operation 状态（默认 10 秒间隔）
3. 生成完成后下载视频并保存到本地缓存

最长等待时间默认 300 秒（5 分钟），可通过代码中的 `DEFAULT_MAX_POLL_TIME` 调整。

## 许可证

MIT License
