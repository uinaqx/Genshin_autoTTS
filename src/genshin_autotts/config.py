from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from platformdirs import user_data_path

from .models import Region


@dataclass
class AppConfig:
    ocr_interval_ms: int = 300
    stability_frames: int = 3
    similarity_threshold: float = 0.94
    minimum_stable_ms: int = 600
    repeat_cooldown_seconds: int = 8
    speaker_region: Region | None = None
    dialogue_region: Region | None = None
    tts_provider: str = "volcengine"
    voice_pack_manifest: str | None = None
    speaker_voice_overrides: dict[str, str] = field(default_factory=dict)
    cloud_timeout_seconds: int = 35
    cloud_retries: int = 2
    volcengine_cluster: str = "volcano_tts"
    aliyun_region: str = "auto"
    cache_max_mb: int = 256
    play_audio: bool = True
    interrupt_audio: bool = True

    def validate(self) -> None:
        if self.ocr_interval_ms < 100:
            raise ValueError("ocr_interval_ms must be at least 100")
        if self.stability_frames < 1:
            raise ValueError("stability_frames must be positive")
        if not 0.5 <= self.similarity_threshold <= 1.0:
            raise ValueError("similarity_threshold must be between 0.5 and 1.0")
        if self.minimum_stable_ms < 0:
            raise ValueError("minimum_stable_ms must be non-negative")
        if self.cache_max_mb < 32:
            raise ValueError("cache_max_mb must be at least 32")
        if self.tts_provider not in {"volcengine", "aliyun", "recorded", "edge"}:
            raise ValueError(
                "tts_provider must be 'volcengine', 'aliyun', 'recorded', or 'edge'"
            )
        if self.cloud_timeout_seconds < 5 or self.cloud_timeout_seconds > 120:
            raise ValueError("cloud_timeout_seconds must be between 5 and 120")
        if self.cloud_retries < 0 or self.cloud_retries > 5:
            raise ValueError("cloud_retries must be between 0 and 5")
        if not self.volcengine_cluster.strip():
            raise ValueError("volcengine_cluster must not be empty")
        if self.aliyun_region not in {"auto", "shanghai", "beijing", "shenzhen", "singapore"}:
            raise ValueError("unsupported aliyun_region")
        if not isinstance(self.speaker_voice_overrides, dict):
            raise ValueError("speaker_voice_overrides must be an object")
        for speaker, voice in self.speaker_voice_overrides.items():
            if not str(speaker).strip() or not str(voice).strip():
                raise ValueError("speaker_voice_overrides cannot contain empty names or voices")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        return result

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> AppConfig:
        fields = cls.__dataclass_fields__
        filtered = {key: value for key, value in raw.items() if key in fields}
        if filtered.get("tts_provider") == "sapi":
            filtered["tts_provider"] = "recorded"
        filtered["speaker_voice_overrides"] = {
            str(speaker): str(voice)
            for speaker, voice in (filtered.get("speaker_voice_overrides") or {}).items()
        }
        filtered["speaker_region"] = Region.from_value(filtered.get("speaker_region"))
        filtered["dialogue_region"] = Region.from_value(filtered.get("dialogue_region"))
        config = cls(**filtered)
        config.validate()
        return config


def app_home() -> Path:
    override = os.environ.get("GENSHIN_AUTOTTS_HOME")
    path = Path(override).expanduser() if override else Path(user_data_path("GenshinAutoTTS"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return app_home() / "config.json"


def load_config(path: Path | None = None) -> AppConfig:
    path = path or config_path()
    if not path.exists():
        config = AppConfig()
        save_config(config, path)
        return config
    raw = json.loads(path.read_text(encoding="utf-8"))
    return AppConfig.from_dict(raw)


def save_config(config: AppConfig, path: Path | None = None) -> None:
    config.validate()
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(config.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)
