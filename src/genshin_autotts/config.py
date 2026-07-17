from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
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
    tts_provider: str = "sapi"
    cache_max_mb: int = 256
    opus_bitrate_kbps: int = 32
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
        if self.opus_bitrate_kbps not in range(16, 65):
            raise ValueError("opus_bitrate_kbps must be between 16 and 64")
        if self.tts_provider not in {"sapi", "edge"}:
            raise ValueError("tts_provider must be 'sapi' or 'edge'")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        return result

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> AppConfig:
        fields = cls.__dataclass_fields__
        filtered = {key: value for key, value in raw.items() if key in fields}
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
