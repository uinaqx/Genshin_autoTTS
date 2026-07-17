from __future__ import annotations

from pathlib import Path

from .audio import NullAudioPlayer, PygameAudioPlayer
from .cache import AudioCache
from .capture import MssScreenCapture
from .config import AppConfig, app_home
from .ocr import DesktopObservationSource, RapidOcrEngine
from .pipeline import PipelineController, VoicePipeline
from .text import DialogueStabilizer
from .tts import EdgeTtsProvider, RecordedVoiceProvider
from .voice import VoiceRegistry


def build_voice_pipeline(config: AppConfig, play_audio: bool | None = None) -> VoicePipeline:
    home = app_home()
    registry = VoiceRegistry(home / "speaker_profiles.json", config.tts_provider)
    if config.tts_provider == "recorded":
        manifest = (
            Path(config.voice_pack_manifest).expanduser()
            if config.voice_pack_manifest
            else Path(__file__).with_name("sample_voicepack") / "manifest.json"
        )
        tts = RecordedVoiceProvider(manifest)
    else:
        tts = EdgeTtsProvider()
    cache = AudioCache(home / "cache", config.cache_max_mb * 1024 * 1024)
    should_play = config.play_audio if play_audio is None else play_audio
    player = PygameAudioPlayer() if should_play else NullAudioPlayer()
    return VoicePipeline(
        registry,
        tts,
        cache,
        player,
        play_audio=should_play,
        interrupt_audio=config.interrupt_audio,
    )


def build_controller(config: AppConfig, status=None) -> PipelineController:
    if config.speaker_region is None or config.dialogue_region is None:
        raise ValueError("请先设置角色名区域和字幕区域")
    source = DesktopObservationSource(
        MssScreenCapture(),
        RapidOcrEngine(),
        config.speaker_region,
        config.dialogue_region,
    )
    stabilizer = DialogueStabilizer(
        config.stability_frames,
        config.similarity_threshold,
        config.minimum_stable_ms,
        config.repeat_cooldown_seconds,
    )
    return PipelineController(
        source,
        stabilizer,
        build_voice_pipeline(config),
        config.ocr_interval_ms,
        status,
    )
