# Hermes ZenMux Video Generation Plugin

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Hermes](https://img.shields.io/badge/Hermes-≥%200.7.0-blue)](https://github.com/nousresearch/hermes-agent)

English Version | [中文版本](./README.zh-CN.md)

Teach your Hermes AI assistant to generate videos — one API Key connects you to 5 video generation models from 3 providers. Turn text or images into video.

---

## 😵‍💫 What Is This?

**In one sentence:** This plugin lets Hermes generate videos. You say "shoot a clip of waves crashing on rocks" and it generates one.

Hermes itself only chats — it can't generate video. This plugin connects it to video generation via the [ZenMux](https://zenmux.ai/invite/1C3QLF) API gateway, giving you access to **5 models from Google, ByteDance, and Alibaba**. One ZenMux API Key covers everything — no need to sign up with each provider separately.

---

## ✨ Supported Models

| Model | Provider | Speed | Audio | Best For |
|-------|----------|-------|-------|----------|
| **Veo 3.1** | Google | ~60-120s | ✅ | Top quality, cinematic visuals |
| **Veo 3.1 Fast** | Google | ~30-60s | ✅ | Fast and high-quality — recommended for daily use |
| **Veo 3.1 Lite** | Google | ~20-45s | ❌ | Budget-friendly, quick output |
| **Seedance 2.0** | ByteDance | ~45-90s | ✅ | Supports negative prompts for precise control |
| **Happy Horse 1.0** | Alibaba | ~30-60s | ❌ | Budget-friendly, supports negative prompts |

### Two Generation Methods

- **Text-to-Video**: Write a description, get a video. All models support this.
- **Image-to-Video**: Give a static image and bring it to life. All models support this.

> For example: upload a photo of ocean waves and say "animate the waves, add sunset lighting."

> 📸 `[screenshot]` — Side-by-side comparison of all 5 models generating the same prompt (e.g., "a cat walking through a garden")

---

## 🚀 Quick Start (4 Steps)

### Prerequisites

- ✅ Running [Hermes Agent](https://github.com/nousresearch/hermes-agent) (≥ 0.7.0)
- ✅ A [ZenMux](https://zenmux.ai/invite/1C3QLF) account and API Key
- ✅ Python 3.11+

---

### Step 1: Install the Plugin

```bash
hermes plugins install colin-chang/hermes-plugin-zenmux-video --enable
```

### Step 2: Install SDK Dependency

This plugin requires Google's `google-genai` SDK (ZenMux uses Vertex AI protocol for video models):

```bash
pip install google-genai
```

> 💡 If you use Hermes' bundled Python environment, make sure it's installed to the right place.

### Step 3: Configure API Key

Open `~/.hermes/.env` and add:

```bash
ZENMUX_API_KEY=your-zenmux-api-key
```

### Step 4: Set the Video Generation Backend

Add to `~/.hermes/config.yaml`:

```yaml
video_gen:
  provider: zenmux-video
  model: google/veo-3.1-fast-generate-001   # default; change as needed
```

Restart Hermes to apply. Now try telling Hermes "Generate a video of waves crashing on rocks."

---

## 📖 Usage Guide

### Text-to-Video

Just describe what you want like a normal conversation:

> Generate a video: an orange cat strolling through a garden at sunset, cinematic lighting, 10 seconds

> Use Veo to shoot: a drone flyover of snow-capped mountains, swirling mist

### Image-to-Video

If Hermes previously generated an image for you, you can ask it to "turn that image into a video":

> Animate that ocean photo: make the waves crash, add sunset lighting

> Bring that city nightscape to life: traffic flowing, lights flickering

### Switching Models

**Method 1: Mention it in your prompt** (no config change needed)

- Say "Use **Veo** to generate..." → auto-selects Veo 3.1
- Say "Use **Seedance** to generate..." → auto-selects Seedance 2.0
- Say "Use **Happy Horse** to generate..." → auto-selects Happy Horse 1.0

**Method 2: Edit the config file**

```yaml
video_gen:
  zenmux:
    model: bytedance/doubao-seedance-2.0
```

**Method 3: Environment variable**

```bash
export ZENMUX_VIDEO_MODEL=alibaba/happyhorse-1.0
```

### Model Selection Priority

When multiple methods are active simultaneously, priority from highest to lowest:

1. Prompt keyword (e.g., "use Veo" → auto-selects Veo 3.1)
2. `ZENMUX_VIDEO_MODEL` environment variable
3. `video_gen.zenmux.model` config setting
4. `video_gen.model` config setting
5. Default model: `google/veo-3.1-fast-generate-001`

---

## 📊 Model Capability Comparison

| Capability | Veo 3.1 | Veo 3.1 Fast | Veo 3.1 Lite | Seedance 2.0 | Happy Horse |
|------------|---------|--------------|--------------|--------------|-------------|
| Text-to-Video | ✅ | ✅ | ✅ | ✅ | ✅ |
| Image-to-Video | ✅ | ✅ | ✅ | ✅ | ✅ |
| Audio | ✅ | ✅ | ❌ | ✅ | ❌ |
| Negative Prompts | ❌ | ❌ | ❌ | ✅ | ✅ |
| Resolution | 720p/1080p | 720p/1080p | 480p/720p | 720p/1080p | 480p/720p |
| Aspect Ratio | 16:9/9:16/1:1 | 16:9/9:16/1:1 | 16:9/9:16 | 16:9/9:16/1:1 | 16:9/9:16/1:1 |
| Duration | 5-15s | 5-10s | 4-8s | 5-10s | 4-10s |

---

## 🧱 How Does It Work?

```
You say "shoot a wave video" ──→ Hermes ──→ This plugin ──→ ZenMux API ──→ Google / ByteDance / Alibaba
                                         │
                                    ZenMux acts as a "translator":
                                    no matter which provider's model you choose,
                                    everything goes through one API Key
```

Video generation is much slower than image generation — you can't just "say it and get it" instantly. It works in three stages:

1. **Submit request**: The plugin sends your description to ZenMux
2. **Poll for completion**: Checks every 10 seconds "is it done yet?", waiting up to 5 minutes
3. **Download video**: Once generated, auto-downloads to local cache — plays directly in chat

The async polling mechanism:
- Submits a generation request → receives an Operation ID
- Polls the Operation status at regular intervals (default: every 10 seconds)
- Once complete, downloads the video and saves it to local cache

Maximum wait time defaults to 300 seconds (5 minutes).

---

## ❓ FAQ

**Q: Do I need separate accounts for Google, ByteDance, and Alibaba?**

A: No. One ZenMux account, one API Key, all models included.

**Q: Why is video generation so slow?**

A: Video generation is far more complex than image generation — it can take anywhere from seconds to 2 minutes, depending on the model and video length. For daily use, **Veo 3.1 Fast** (30-60s) offers the best value.

**Q: Which models generate video with audio?**

A: Veo 3.1, Veo 3.1 Fast, and Seedance 2.0 support audio. Veo 3.1 Lite and Happy Horse do not.

**Q: Can I control video duration and resolution?**

A: Yes. Just mention it in your prompt, e.g., "generate an 8-second 1080p video." But different models have different limits — Veo 3.1 Lite maxes out at 720p / 8 seconds. Check the capability comparison table above for details.

**Q: What are negative prompts?**

A: They tell the AI what **not** to include. For example: "Generate a city nightscape, **no fog**, **no people**." Seedance 2.0 and Happy Horse 1.0 support this feature.

**Q: Where are the generated videos saved?**

A: Hermes auto-saves them to local cache. You can play them directly in chat.

---

## 📁 Project Structure

```
zenmux-video/
├── plugin.yaml              # Plugin metadata
├── __init__.py              # Plugin entry point (VideoGenProvider implementation)
├── README.md                # This document
├── README.zh-CN.md          # Chinese documentation
├── LICENSE                  # MIT
└── .gitignore
```

---

## 📄 License

MIT — see [LICENSE](LICENSE)
