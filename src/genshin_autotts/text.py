from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone

from rapidfuzz.fuzz import ratio

from .models import DialogueEvent, DialogueObservation


_TAG_PATTERN = re.compile(r"<[^>]+>|\{[^}]+\}")
_SPACE_PATTERN = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = _TAG_PATTERN.sub("", value)
    value = value.replace("…", "...").replace("—", "-")
    value = value.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    value = _SPACE_PATTERN.sub("", value)
    return value.strip("|丨_ ")


def normalize_speaker(value: str) -> str:
    value = normalize_text(value).strip(":：")
    if value in {"", "?", "??", "???", "未知", "..."}:
        return "旁白"
    return value


@dataclass
class DialogueStabilizer:
    stability_frames: int = 3
    similarity_threshold: float = 0.94
    minimum_stable_ms: int = 600
    repeat_cooldown_seconds: int = 8

    def __post_init__(self) -> None:
        self._speaker = ""
        self._text = ""
        self._count = 0
        self._candidate_since = 0.0
        self._candidate_emitted = False
        self._last_emitted: dict[str, float] = {}

    def observe(self, observation: DialogueObservation, now: float | None = None) -> DialogueEvent | None:
        now = time.monotonic() if now is None else now
        speaker = normalize_speaker(observation.speaker)
        text = normalize_text(observation.text)
        if not text:
            self._count = 0
            self._text = ""
            self._candidate_emitted = False
            return None

        exact = speaker == self._speaker and text == self._text
        similar = speaker == self._speaker and ratio(text, self._text) / 100 >= self.similarity_threshold

        if exact:
            self._count += 1
        elif similar and len(text) == len(self._text):
            self._text = text
            self._count += 1
        else:
            self._speaker = speaker
            self._text = text
            self._count = 1
            self._candidate_since = now
            self._candidate_emitted = False

        stable_ms = (now - self._candidate_since) * 1000
        if (
            self._candidate_emitted
            or self._count < self.stability_frames
            or stable_ms < self.minimum_stable_ms
        ):
            return None

        event = DialogueEvent(
            speaker=self._speaker,
            text=self._text,
            emitted_at=datetime.now(timezone.utc),
        )
        last_time = self._last_emitted.get(event.line_key)
        if last_time is not None and now - last_time < self.repeat_cooldown_seconds:
            return None
        self._last_emitted[event.line_key] = now
        self._candidate_emitted = True
        return event
