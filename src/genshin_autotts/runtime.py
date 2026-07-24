from __future__ import annotations

from pathlib import Path

from .audio import NullAudioPlayer, PygameAudioPlayer
from .cache import AudioCache
from .capture import MssScreenCapture
from .config import AppConfig, app_home
from .credentials import CredentialStore
from .ocr import DesktopObservationSource, RapidOcrEngine
from .pipeline import PipelineController, VoicePipeline
from .text import DialogueStabilizer
from .tts import (
    AliyunTtsProvider,
    EdgeTtsProvider,
    RecordedVoiceProvider,
    VolcengineTtsProvider,
)
from .voice import VoiceRegistry


def build_voice_pipeline(config: AppConfig, play_audio: bool | None = None) -> VoicePipeline:
    home = app_home()
    registry = VoiceRegistry(
        home / "speaker_profiles.json",
        config.tts_provider,
        config.speaker_voice_overrides,
    )
    if config.tts_provider == "recorded":
        manifest = (
            Path(config.voice_pack_manifest).expanduser()
            if config.voice_pack_manifest
            else Path(__file__).with_name("sample_voicepack") / "manifest.json"
        )
        tts = RecordedVoiceProvider(manifest)
    elif config.tts_provider == "edge":
        tts = EdgeTtsProvider()
    else:
        credentials = CredentialStore(home / "credentials.dat").get_provider(
            config.tts_provider
        )
        if config.tts_provider == "volcengine":
            if not credentials.get("app_id") or not credentials.get("access_token"):
                raise ValueError(
                    "尚未配置火山引擎 API。请在“云端语音服务”中填写 App ID 和 Access Token。"
                )
            tts = VolcengineTtsProvider(
                credentials["app_id"],
                credentials["access_token"],
                cluster=config.volcengine_cluster,
                timeout_seconds=config.cloud_timeout_seconds,
                retries=config.cloud_retries,
            )
        elif config.tts_provider == "aliyun":
            if not credentials.get("app_key") or not credentials.get("access_token"):
                raise ValueError(
                    "尚未配置阿里云 API。请在“云端语音服务”中填写 AppKey 和 Access Token。"
                )
            tts = AliyunTtsProvider(
                credentials["app_key"],
                credentials["access_token"],
                region=config.aliyun_region,
                timeout_seconds=config.cloud_timeout_seconds,
                retries=config.cloud_retries,
            )
        else:
            raise ValueError(f"不支持的语音提供商：{config.tts_provider}")
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
