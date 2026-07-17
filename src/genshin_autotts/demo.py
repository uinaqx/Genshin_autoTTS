from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import AppConfig, app_home
from .models import DialogueEvent
from .ocr import RapidOcrEngine
from .runtime import build_voice_pipeline
from .text import DialogueStabilizer


def run_demo(speaker: str, text: str, provider: str = "edge", play: bool = False):
    config = AppConfig(tts_provider=provider, play_audio=play)
    pipeline = build_voice_pipeline(config, play_audio=play)
    event = DialogueEvent(speaker, text, datetime.now(timezone.utc))
    return pipeline.process(event)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "msyh.ttc",
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "simhei.ttf",
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def _render_text(text: str, size: tuple[int, int]) -> Image.Image:
    image = Image.new("RGB", size, (24, 28, 36))
    draw = ImageDraw.Draw(image)
    font = _font(46)
    bbox = draw.textbbox((0, 0), text, font=font)
    x = max(10, (size[0] - (bbox[2] - bbox[0])) // 2)
    y = max(10, (size[1] - (bbox[3] - bbox[1])) // 2)
    draw.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0))
    draw.text((x, y), text, font=font, fill=(248, 248, 248))
    return image


def run_smoke() -> dict[str, str | bool | float]:
    """Exercise real OCR, stabilization, neural voice generation and cache."""
    speaker_expected = "派蒙"
    text_expected = "旅行者我们出发吧"
    ocr = RapidOcrEngine()
    speaker_result = ocr.recognize(_render_text(speaker_expected, (500, 120)))
    text_result = ocr.recognize(_render_text(text_expected, (900, 160)))
    if speaker_expected not in speaker_result.text:
        raise RuntimeError(f"OCR speaker mismatch: {speaker_result.text!r}")
    if text_expected not in text_result.text:
        raise RuntimeError(f"OCR dialogue mismatch: {text_result.text!r}")

    stabilizer = DialogueStabilizer(3, 0.94, 0, 1)
    event = None
    observation_time = 100.0
    from .models import DialogueObservation

    observation = DialogueObservation(speaker_result.text, text_result.text)
    for index in range(3):
        event = stabilizer.observe(observation, observation_time + index * 0.1)
    if event is None:
        raise RuntimeError("Dialogue stabilizer did not emit")

    config = AppConfig(tts_provider="edge", play_audio=False, cache_max_mb=64)
    pipeline = build_voice_pipeline(config, play_audio=False)
    artifact = pipeline.process(event)
    second = pipeline.process(event)
    if not Path(artifact.path).exists() or Path(artifact.path).stat().st_size == 0:
        raise RuntimeError("TTS artifact is missing")
    if not second.from_cache:
        raise RuntimeError("Second pipeline call did not hit cache")
    return {
        "speaker": speaker_result.text,
        "text": text_result.text,
        "speaker_confidence": round(speaker_result.confidence, 4),
        "text_confidence": round(text_result.confidence, 4),
        "audio_path": artifact.path,
        "codec": artifact.codec,
        "provider": artifact.provider,
        "cache_hit_verified": second.from_cache,
        "runtime_home": str(app_home()),
    }
