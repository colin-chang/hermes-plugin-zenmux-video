"""ZenMux video generation backend.

Supports video generation models hosted on ZenMux via the Vertex AI
Compatible API, using the ``google-genai`` Python SDK.

Supported models
----------------
- ``google/veo-3.1-generate-001`` — Google Veo 3.1 (premium, highest quality)
- ``google/veo-3.1-fast-generate-001`` — Veo 3.1 Fast (faster, premium)
- ``google/veo-3.1-lite-generate-001`` — Veo 3.1 Lite (affordable)
- ``bytedance/doubao-seedance-2.0`` — ByteDance Seedance 2.0
- ``alibaba/happyhorse-1.0`` — Alibaba Happy Horse 1.0

All models support text-to-video; models with image-to-video support
accept ``image_url`` for animation from a still frame.

Protocol
--------
ZenMux exposes video generation through the Vertex AI protocol at
``https://zenmux.ai/api/vertex-ai``. The workflow is asynchronous:

1. ``client.models.generate_videos()`` — submit request
2. ``client.operations.get()`` — poll until ``operation.done``
3. Extract video from ``operation.response.generated_videos``

Authentication via ``ZENMUX_API_KEY`` env var.

Selection precedence (first hit wins):
1. ``model=`` kwarg from tool call
2. ``ZENMUX_VIDEO_MODEL`` env var
3. ``video_gen.zenmux.model`` in ``config.yaml``
4. ``video_gen.model`` in ``config.yaml`` (when it matches a catalog entry)
5. :data:`DEFAULT_MODEL`
"""

from __future__ import annotations

import io
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from agent.video_gen_provider import (
    COMMON_ASPECT_RATIOS,
    VideoGenProvider,
    error_response,
    save_bytes_video,
    success_response,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ZENMUX_VERTEX_BASE = "https://zenmux.ai/api/vertex-ai"
DEFAULT_POLL_INTERVAL = 10  # seconds between polls
DEFAULT_MAX_POLL_TIME = 300  # 5 minutes max wait
API_VERSION = "v1"

# ---------------------------------------------------------------------------
# Model catalog
# ---------------------------------------------------------------------------
#
# Each entry declares capabilities that drive:
#   - which keys get added to GenerateVideosConfig
#   - what the tool schema advertises to the agent

_MODELS: Dict[str, Dict[str, Any]] = {
    "google/veo-3.1-generate-001": {
        "display": "Veo 3.1",
        "speed": "~60-120s",
        "price": "premium",
        "strengths": "Highest quality Google Veo 3.1; text-to-video & image-to-video; audio",
        "tier": "premium",
        "modalities": ["text", "image"],
        "aspect_ratios": ("16:9", "9:16", "1:1"),
        "resolutions": ("720p", "1080p"),
        "duration_range": (5, 15),
        "audio": True,
        "negative": False,
    },
    "google/veo-3.1-fast-generate-001": {
        "display": "Veo 3.1 Fast",
        "speed": "~30-60s",
        "price": "premium",
        "strengths": "Faster Veo 3.1 variant; text-to-video & image-to-video; audio",
        "tier": "premium",
        "modalities": ["text", "image"],
        "aspect_ratios": ("16:9", "9:16", "1:1"),
        "resolutions": ("720p", "1080p"),
        "duration_range": (5, 10),
        "audio": True,
        "negative": False,
    },
    "google/veo-3.1-lite-generate-001": {
        "display": "Veo 3.1 Lite",
        "speed": "~20-45s",
        "price": "affordable",
        "strengths": "Affordable Veo 3.1; text-to-video & image-to-video",
        "tier": "cheap",
        "modalities": ["text", "image"],
        "aspect_ratios": ("16:9", "9:16"),
        "resolutions": ("480p", "720p"),
        "duration_range": (5, 8),
        "audio": False,
        "negative": False,
    },
    "bytedance/doubao-seedance-2.0": {
        "display": "Seedance 2.0",
        "speed": "~45-90s",
        "price": "premium",
        "strengths": "ByteDance Seedance 2.0; text-to-video & image-to-video; audio",
        "tier": "premium",
        "modalities": ["text", "image"],
        "aspect_ratios": ("16:9", "9:16", "1:1"),
        "resolutions": ("720p", "1080p"),
        "duration_range": (5, 10),
        "audio": True,
        "negative": True,
    },
    "alibaba/happyhorse-1.0": {
        "display": "Happy Horse 1.0",
        "speed": "~30-60s",
        "price": "affordable",
        "strengths": "Alibaba Happy Horse; text-to-video & image-to-video",
        "tier": "cheap",
        "modalities": ["text", "image"],
        "aspect_ratios": ("16:9", "9:16", "1:1"),
        "resolutions": ("480p", "720p"),
        "duration_range": (4, 10),
        "audio": False,
        "negative": True,
    },
}

DEFAULT_MODEL = "google/veo-3.1-fast-generate-001"

# Aspect ratio mapping: Hermes convention → Vertex AI format
_ASPECT_RATIO_MAP = {
    "16:9": "16:9",
    "9:16": "9:16",
    "1:1": "1:1",
    "4:3": "4:3",
    "3:4": "3:4",
    "3:2": "3:2",
    "2:3": "2:3",
}


# ---------------------------------------------------------------------------
# Config readers
# ---------------------------------------------------------------------------


def _load_video_gen_section() -> Dict[str, Any]:
    """Read ``video_gen`` section from config.yaml."""
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        section = cfg.get("video_gen") if isinstance(cfg, dict) else None
        return section if isinstance(section, dict) else {}
    except Exception as exc:
        logger.debug("Could not load video_gen config: %s", exc)
        return {}


def _resolve_model(explicit: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
    """Decide which model to use. Returns ``(model_id, meta)``."""
    candidates: List[Optional[str]] = []
    candidates.append(explicit)
    candidates.append(os.environ.get("ZENMUX_VIDEO_MODEL"))

    cfg = _load_video_gen_section()
    zenmux_cfg = cfg.get("zenmux") if isinstance(cfg.get("zenmux"), dict) else {}
    if isinstance(zenmux_cfg, dict):
        candidates.append(zenmux_cfg.get("model"))
    top = cfg.get("model")
    if isinstance(top, str):
        candidates.append(top)

    for c in candidates:
        if isinstance(c, str) and c.strip() and c.strip() in _MODELS:
            return c.strip(), _MODELS[c.strip()]

    return DEFAULT_MODEL, _MODELS[DEFAULT_MODEL]


def _get_api_key() -> str:
    """Read the ZenMux API key from env."""
    return (os.environ.get("ZENMUX_API_KEY") or "").strip()


# ---------------------------------------------------------------------------
# Client management (lazy init)
# ---------------------------------------------------------------------------

_client: Any = None


def _get_client(api_key: str) -> Any:
    """Create or return a cached ``google.genai.Client`` for ZenMux."""
    global _client
    if _client is not None:
        return _client

    from google import genai
    from google.genai import types

    _client = genai.Client(
        api_key=api_key,
        vertexai=True,
        http_options=types.HttpOptions(
            api_version=API_VERSION,
            base_url=ZENMUX_VERTEX_BASE,
        ),
    )
    return _client


def _reset_client() -> None:
    """Reset the cached client (for tests or key rotation)."""
    global _client
    _client = None


# ---------------------------------------------------------------------------
# Image download helper (for image-to-video)
# ---------------------------------------------------------------------------


def _download_image_bytes(url: str, timeout: int = 30) -> Tuple[bytes, str]:
    """Download an image from a URL.

    Returns ``(image_bytes, mime_type)``.
    """
    resp = requests.get(url, timeout=timeout, stream=True)
    resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "image/png")
    # Normalize mime type
    if "jpeg" in content_type or "jpg" in content_type:
        mime_type = "image/jpeg"
    elif "png" in content_type:
        mime_type = "image/png"
    elif "webp" in content_type:
        mime_type = "image/webp"
    else:
        mime_type = content_type.split(";")[0].strip() or "image/png"

    return resp.content, mime_type


def _read_local_image(path: str) -> Tuple[bytes, str]:
    """Read image bytes from a local file path.

    Returns ``(image_bytes, mime_type)``.
    """
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Image file not found: {path}")

    ext = p.suffix.lower()
    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    mime_type = mime_map.get(ext, "image/png")
    return p.read_bytes(), mime_type


# ---------------------------------------------------------------------------
# Video download & save
# ---------------------------------------------------------------------------


def _download_and_save_video(url: str, prefix: str = "zenmux") -> str:
    """Download a video from a URL and save to Hermes cache.

    Returns the absolute file path.
    """
    resp = requests.get(url, timeout=120, stream=True)
    resp.raise_for_status()
    saved = save_bytes_video(resp.content, prefix=prefix, extension="mp4")
    return str(saved)


# ---------------------------------------------------------------------------
# Generation: submit → poll → retrieve
# ---------------------------------------------------------------------------


def _submit_generation(
    client: Any,
    model_id: str,
    prompt: str,
    image_url: Optional[str],
    config: Any,
) -> Any:
    """Submit a video generation request to ZenMux."""
    from google.genai import types

    source_kwargs: Dict[str, Any] = {"prompt": prompt}

    # Image-to-video: pass image as bytes
    if image_url:
        try:
            if image_url.startswith(("http://", "https://")):
                img_bytes, mime_type = _download_image_bytes(image_url)
            else:
                img_bytes, mime_type = _read_local_image(image_url)
            source_kwargs["image"] = types.Image(
                image_bytes=img_bytes,
                mime_type=mime_type,
            )
        except Exception as exc:
            logger.warning("Failed to download image for i2v: %s", exc)
            raise ValueError(f"Could not load image from {image_url}: {exc}") from exc

    operation = client.models.generate_videos(
        model=model_id,
        source=types.GenerateVideosSource(**source_kwargs),
        config=config,
    )
    return operation


def _poll_until_done(
    client: Any,
    operation: Any,
    poll_interval: int = DEFAULT_POLL_INTERVAL,
    max_wait: int = DEFAULT_MAX_POLL_TIME,
) -> Any:
    """Poll the operation until it completes or times out."""
    start = time.monotonic()
    # Note: SDK may return done=None initially (not False)
    while not getattr(operation, "done", False):
        elapsed = time.monotonic() - start
        if elapsed > max_wait:
            raise TimeoutError(
                f"Video generation did not complete within {max_wait}s"
            )
        time.sleep(poll_interval)
        operation = client.operations.get(operation)
    return operation


def _extract_video(operation: Any, model_id: str, prompt: str) -> Dict[str, Any]:
    """Extract and save the generated video from a completed operation."""
    # Check done status — SDK may return done=None on error
    done = getattr(operation, "done", None)
    if done is False or done is None:
        error = getattr(operation, "error", None)
        err_msg = str(error) if error else "Operation not yet completed"
        return error_response(
            error=f"ZenMux video generation failed: {err_msg}",
            error_type="generation_failed",
            provider="zenmux-video",
            model=model_id,
            prompt=prompt,
        )

    response = getattr(operation, "response", None)
    if response is None:
        # Check for error in operation
        error = getattr(operation, "error", None)
        err_msg = str(error) if error else "No response in completed operation"
        return error_response(
            error=f"ZenMux video generation failed: {err_msg}",
            error_type="generation_failed",
            provider="zenmux-video",
            model=model_id,
            prompt=prompt,
        )

    generated_videos = getattr(response, "generated_videos", [])
    if not generated_videos:
        return error_response(
            error="ZenMux returned no generated videos",
            error_type="empty_response",
            provider="zenmux-video",
            model=model_id,
            prompt=prompt,
        )

    first_video = generated_videos[0]
    video_obj = getattr(first_video, "video", None)

    if video_obj is None:
        return error_response(
            error="ZenMux generated video has no video object",
            error_type="empty_response",
            provider="zenmux-video",
            model=model_id,
            prompt=prompt,
        )

    # Try to get the video content
    video_ref: Optional[str] = None
    video_uri = getattr(video_obj, "uri", None)
    video_bytes = getattr(video_obj, "video_bytes", None)

    if video_uri:
        # Download from URL and save to cache
        try:
            video_ref = _download_and_save_video(video_uri, prefix="zenmux_video")
        except Exception as exc:
            logger.warning("Failed to download video from URI: %s", exc)
            # Fall back to returning the URI directly
            video_ref = video_uri
    elif video_bytes:
        # Save raw bytes to cache
        try:
            saved = save_bytes_video(video_bytes, prefix="zenmux_video", extension="mp4")
            video_ref = str(saved)
        except Exception as exc:
            return error_response(
                error=f"Could not save video to cache: {exc}",
                error_type="io_error",
                provider="zenmux-video",
                model=model_id,
                prompt=prompt,
            )
    else:
        return error_response(
            error="ZenMux video object has neither uri nor video_bytes",
            error_type="empty_response",
            provider="zenmux-video",
            model=model_id,
            prompt=prompt,
        )

    # Determine modality (we don't track it perfectly here, use heuristics)
    modality = "text"  # default

    extra: Dict[str, Any] = {}
    if video_uri:
        extra["source"] = "uri"
    if video_bytes:
        extra["source"] = "bytes"

    # Try to extract video metadata from the response
    video_meta = getattr(first_video, "video_metadata", None)
    if video_meta:
        fps = getattr(video_meta, "fps", None)
        if fps:
            extra["fps"] = fps

    return success_response(
        video=video_ref,
        model=model_id,
        prompt=prompt,
        modality=modality,
        provider="zenmux-video",
        extra=extra,
    )


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class ZenMuxVideoGenProvider(VideoGenProvider):
    """ZenMux video generation backend — Veo 3.1, Seedance 2.0, Happy Horse."""

    # Prompt-keyword → model mapping (case-insensitive substring match)
    _PROMPT_HINTS: Dict[str, str] = {
        "veo": "google/veo-3.1-generate-001",
        "seedance": "bytedance/doubao-seedance-2.0",
        "happy horse": "alibaba/happyhorse-1.0",
        "happyhorse": "alibaba/happyhorse-1.0",
    }

    @property
    def name(self) -> str:
        return "zenmux-video"

    @property
    def display_name(self) -> str:
        return "ZenMux Video"

    def is_available(self) -> bool:
        if not _get_api_key():
            return False
        try:
            from google import genai  # noqa: F401
        except ImportError:
            return False
        return True

    def list_models(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for mid, meta in _MODELS.items():
            out.append({
                "id": mid,
                "display": meta["display"],
                "speed": meta["speed"],
                "strengths": meta["strengths"],
                "price": meta["price"],
                "tier": meta.get("tier", "premium"),
                "modalities": meta.get("modalities", ["text"]),
            })
        return out

    def default_model(self) -> Optional[str]:
        return DEFAULT_MODEL

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "ZenMux Video",
            "badge": "paid",
            "tag": "Veo 3.1 / Seedance 2.0 / Happy Horse — text-to-video & image-to-video",
            "env_vars": [
                {
                    "key": "ZENMUX_API_KEY",
                    "prompt": "ZenMux API key",
                    "url": "https://zenmux.ai/settings/api-keys",
                },
            ],
        }

    def capabilities(self) -> Dict[str, Any]:
        # Merge capabilities across all models for the general surface
        all_aspect_ratios: set = set()
        all_resolutions: set = set()
        min_dur = 99
        max_dur = 0
        any_audio = False
        any_negative = False

        for meta in _MODELS.values():
            for ar in meta.get("aspect_ratios", []):
                all_aspect_ratios.add(ar)
            for res in meta.get("resolutions", []):
                all_resolutions.add(res)
            dur = meta.get("duration_range", (5, 15))
            min_dur = min(min_dur, dur[0])
            max_dur = max(max_dur, dur[1])
            if meta.get("audio"):
                any_audio = True
            if meta.get("negative"):
                any_negative = True

        return {
            "modalities": ["text", "image"],
            "aspect_ratios": sorted(all_aspect_ratios),
            "resolutions": sorted(all_resolutions),
            "max_duration": max_dur,
            "min_duration": min_dur,
            "supports_audio": any_audio,
            "supports_negative_prompt": any_negative,
            "max_reference_images": 0,
        }

    def _resolve_model_from_kwargs_or_prompt(
        self,
        prompt: str,
        kwargs: Dict[str, Any],
    ) -> Tuple[str, Dict[str, Any]]:
        """Resolve model with full fallback chain.

        Priority:
        1. Explicit ``model`` kwarg
        2. Prompt keyword hint
        3. ``ZENMUX_VIDEO_MODEL`` env var
        4. ``video_gen.zenmux.model`` / ``video_gen.model`` in config
        5. ``DEFAULT_MODEL``
        """
        # 1. Explicit kwarg
        model_override = kwargs.get("model")
        if model_override and isinstance(model_override, str) and model_override in _MODELS:
            return model_override, _MODELS[model_override]

        # 2. Prompt keyword hints
        prompt_lower = prompt.lower()
        for hint, model_id in self._PROMPT_HINTS.items():
            if hint in prompt_lower and model_id in _MODELS:
                logger.debug("Prompt hint '%s' matched model '%s'", hint, model_id)
                return model_id, _MODELS[model_id]

        # 3-5. Standard resolution chain
        return _resolve_model()

    def _build_config(
        self,
        model_id: str,
        meta: Dict[str, Any],
        *,
        duration: Optional[int],
        aspect_ratio: str,
        resolution: str,
        negative_prompt: Optional[str],
        audio: Optional[bool],
        seed: Optional[int],
    ) -> Any:
        """Build a ``GenerateVideosConfig`` from tool parameters."""
        from google.genai import types

        config_kwargs: Dict[str, Any] = {}

        # Aspect ratio
        if aspect_ratio and aspect_ratio in meta.get("aspect_ratios", []):
            config_kwargs["aspect_ratio"] = aspect_ratio

        # Resolution
        if resolution and resolution in meta.get("resolutions", []):
            config_kwargs["resolution"] = resolution

        # Duration
        if duration is not None:
            dur_range = meta.get("duration_range", (1, 15))
            clamped = max(dur_range[0], min(dur_range[1], duration))
            config_kwargs["duration_seconds"] = clamped

        # Audio
        if meta.get("audio") and audio is not None:
            config_kwargs["generate_audio"] = bool(audio)

        # Negative prompt
        if meta.get("negative") and negative_prompt:
            config_kwargs["negative_prompt"] = negative_prompt

        # Seed
        if seed is not None:
            config_kwargs["seed"] = seed

        return types.GenerateVideosConfig(**config_kwargs)

    def generate(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        image_url: Optional[str] = None,
        reference_image_urls: Optional[List[str]] = None,
        duration: Optional[int] = None,
        aspect_ratio: str = "16:9",
        resolution: str = "720p",
        negative_prompt: Optional[str] = None,
        audio: Optional[bool] = None,
        seed: Optional[int] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Generate a video via ZenMux Vertex AI API."""
        api_key = _get_api_key()
        if not api_key:
            return error_response(
                error=(
                    "ZENMUX_API_KEY not set. Get your key at "
                    "https://zenmux.ai/settings/api-keys"
                ),
                error_type="auth_required",
                provider="zenmux-video",
                prompt=prompt,
            )

        # Resolve model — pass explicit `model` arg AND remaining kwargs
        resolve_kwargs = dict(kwargs)
        if model is not None:
            resolve_kwargs["model"] = model
        model_id, meta = self._resolve_model_from_kwargs_or_prompt(prompt, resolve_kwargs)

        # Validate modality support
        image_url_norm = (image_url or "").strip() or None
        modalities = set(meta.get("modalities", ["text"]))
        if image_url_norm and "image" not in modalities:
            return error_response(
                error=(
                    f"Model {model_id} does not support image-to-video. "
                    f"Omit image_url for text-to-video, or pick a different model."
                ),
                error_type="modality_unsupported",
                provider="zenmux-video",
                model=model_id,
                prompt=prompt,
            )

        # Build config
        try:
            config = self._build_config(
                model_id,
                meta,
                duration=duration,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                negative_prompt=negative_prompt,
                audio=audio,
                seed=seed,
            )
        except Exception as exc:
            return error_response(
                error=f"Failed to build video generation config: {exc}",
                error_type="config_error",
                provider="zenmux-video",
                model=model_id,
                prompt=prompt,
            )

        # Get client
        try:
            client = _get_client(api_key)
        except Exception as exc:
            return error_response(
                error=f"Failed to initialize ZenMux client: {exc}",
                error_type="client_error",
                provider="zenmux-video",
                model=model_id,
                prompt=prompt,
            )

        # Submit
        try:
            operation = _submit_generation(
                client, model_id, prompt, image_url_norm, config
            )
        except ValueError as exc:
            return error_response(
                error=str(exc),
                error_type="input_error",
                provider="zenmux-video",
                model=model_id,
                prompt=prompt,
            )
        except Exception as exc:
            logger.warning(
                "ZenMux video submit failed (model=%s): %s",
                model_id, exc, exc_info=True,
            )
            return error_response(
                error=f"ZenMux video generation submit failed: {exc}",
                error_type="api_error",
                provider="zenmux-video",
                model=model_id,
                prompt=prompt,
            )

        # Poll
        try:
            operation = _poll_until_done(client, operation)
        except TimeoutError as exc:
            return error_response(
                error=str(exc),
                error_type="timeout",
                provider="zenmux-video",
                model=model_id,
                prompt=prompt,
            )
        except Exception as exc:
            logger.warning(
                "ZenMux video polling failed (model=%s): %s",
                model_id, exc, exc_info=True,
            )
            return error_response(
                error=f"ZenMux video generation polling failed: {exc}",
                error_type="polling_error",
                provider="zenmux-video",
                model=model_id,
                prompt=prompt,
            )

        # Check for operation-level error
        if hasattr(operation, "error") and operation.error:
            err = operation.error
            err_msg = getattr(err, "message", str(err))
            return error_response(
                error=f"ZenMux video generation error: {err_msg}",
                error_type="generation_error",
                provider="zenmux-video",
                model=model_id,
                prompt=prompt,
            )

        # Extract result
        result = _extract_video(operation, model_id, prompt)
        # Fix modality
        if result.get("success") and image_url_norm:
            result["modality"] = "image"

        # Fill in aspect_ratio and duration from our request params
        if result.get("success"):
            if aspect_ratio:
                result["aspect_ratio"] = aspect_ratio
            if duration is not None:
                result["duration"] = duration

        return result


# ---------------------------------------------------------------------------
# Plugin entry point
# ---------------------------------------------------------------------------


def register(ctx) -> None:
    """Plugin entry point — wire ``ZenMuxVideoGenProvider`` into the registry."""
    ctx.register_video_gen_provider(ZenMuxVideoGenProvider())
