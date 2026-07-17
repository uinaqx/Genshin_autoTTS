from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from .config import AppConfig, app_home
from .fixture import LINES, render_dialogue_scene
from .models import DialogueEvent
from .ocr import RapidOcrEngine, recognize_dialogue_frame
from .runtime import build_voice_pipeline
from .text import DialogueStabilizer


def run_demo(
    speaker: str,
    text: str,
    provider: str = "recorded",
    play: bool = False,
    voice_pack_manifest: str | None = None,
):
    config = AppConfig(
        tts_provider=provider,
        play_audio=play,
        voice_pack_manifest=voice_pack_manifest,
    )
    pipeline = build_voice_pipeline(config, play_audio=play)
    event = DialogueEvent(speaker, text, datetime.now(timezone.utc))
    artifact = pipeline.process(event)
    if play:
        import pygame

        while pygame.mixer.music.get_busy():
            time.sleep(0.05)
    return artifact


def run_smoke() -> dict[str, str | bool | float]:
    """Exercise realistic OCR, stabilization, verified recording, and cache."""
    fixture_line = LINES[0]
    ocr = RapidOcrEngine()
    frame_result = recognize_dialogue_frame(render_dialogue_scene(fixture_line), ocr)
    observation = frame_result.observation
    if observation.speaker != fixture_line.speaker:
        raise RuntimeError(f"OCR speaker mismatch: {observation.speaker!r}")
    if observation.text != fixture_line.text:
        raise RuntimeError(f"OCR dialogue mismatch: {observation.text!r}")

    stabilizer = DialogueStabilizer(3, 0.94, 0, 1)
    event = None
    observation_time = 100.0
    for index in range(3):
        event = stabilizer.observe(observation, observation_time + index * 0.1)
    if event is None:
        raise RuntimeError("Dialogue stabilizer did not emit")

    config = AppConfig(tts_provider="recorded", play_audio=False, cache_max_mb=64)
    pipeline = build_voice_pipeline(config, play_audio=False)
    diagnostic_event = DialogueEvent("真人示例", "zero", datetime.now(timezone.utc))
    artifact = pipeline.process(diagnostic_event)
    second = pipeline.process(diagnostic_event)
    if not Path(artifact.path).exists() or Path(artifact.path).stat().st_size == 0:
        raise RuntimeError("TTS artifact is missing")
    if not second.from_cache:
        raise RuntimeError("Second pipeline call did not hit cache")
    return {
        "speaker": observation.speaker,
        "text": observation.text,
        "layout": frame_result.layout,
        "speaker_confidence": round(observation.speaker_confidence, 4),
        "text_confidence": round(observation.text_confidence, 4),
        "audio_path": artifact.path,
        "codec": artifact.codec,
        "provider": artifact.provider,
        "cache_hit_verified": second.from_cache,
        "runtime_home": str(app_home()),
    }
