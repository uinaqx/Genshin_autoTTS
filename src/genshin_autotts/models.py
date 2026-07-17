from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


@dataclass(frozen=True)
class Region:
    left: int
    top: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Region width and height must be positive")

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    def as_bbox(self) -> tuple[int, int, int, int]:
        return self.left, self.top, self.right, self.bottom

    def as_mss(self) -> dict[str, int]:
        return asdict(self)

    @classmethod
    def from_value(cls, value: Any) -> Region | None:
        if value is None:
            return None
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            return cls(**{key: int(value[key]) for key in ("left", "top", "width", "height")})
        if isinstance(value, (list, tuple)) and len(value) == 4:
            return cls(*(int(item) for item in value))
        raise ValueError(f"Unsupported region value: {value!r}")


@dataclass(frozen=True)
class OcrResult:
    text: str
    confidence: float


@dataclass(frozen=True)
class DialogueObservation:
    speaker: str
    text: str
    speaker_confidence: float = 0.0
    text_confidence: float = 0.0
    captured_at: datetime | None = None

    def with_timestamp(self) -> DialogueObservation:
        if self.captured_at is not None:
            return self
        return DialogueObservation(
            speaker=self.speaker,
            text=self.text,
            speaker_confidence=self.speaker_confidence,
            text_confidence=self.text_confidence,
            captured_at=datetime.now(timezone.utc),
        )


@dataclass(frozen=True)
class DialogueEvent:
    speaker: str
    text: str
    emitted_at: datetime

    @property
    def line_key(self) -> str:
        payload = f"{self.speaker}\0{self.text}".encode("utf-8")
        return sha256(payload).hexdigest()


@dataclass(frozen=True)
class VoiceProfile:
    profile_id: str
    provider: str
    voice: str
    gender: str
    age: str
    temperament: str
    rate_percent: int = 0
    volume_percent: int = 0


@dataclass(frozen=True)
class AudioArtifact:
    path: str
    codec: str
    provider: str
    cache_key: str
    from_cache: bool = False
