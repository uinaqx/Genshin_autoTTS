from __future__ import annotations

import json
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

from .models import VoiceProfile


EDGE_PALETTE = [
    VoiceProfile("bright_female", "edge", "zh-CN-XiaoxiaoNeural", "female", "young", "bright", 4),
    VoiceProfile("calm_female", "edge", "zh-CN-XiaoyiNeural", "female", "adult", "calm", -2),
    VoiceProfile("young_male", "edge", "zh-CN-YunxiNeural", "male", "young", "lively", 3),
    VoiceProfile("steady_male", "edge", "zh-CN-YunyangNeural", "male", "adult", "steady", -4),
    VoiceProfile("passionate_male", "edge", "zh-CN-YunjianNeural", "male", "adult", "passionate", 2),
    VoiceProfile("cute_male", "edge", "zh-CN-YunxiaNeural", "male", "young", "cute", 6),
]

KNOWN_HINTS = {
    "派蒙": ("female", "young", "bright"),
    "旅行者": ("female", "young", "steady"),
    "荧": ("female", "young", "steady"),
    "空": ("male", "young", "steady"),
    "旁白": ("female", "adult", "calm"),
}


class VoiceRegistry:
    def __init__(self, path: Path, provider: str = "edge") -> None:
        self.path = path
        self.provider = provider
        self._profiles: dict[str, VoiceProfile] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        for speaker, profile in raw.items():
            self._profiles[speaker] = VoiceProfile(**profile)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {speaker: asdict(profile) for speaker, profile in sorted(self._profiles.items())}
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def resolve(self, speaker: str) -> VoiceProfile:
        if self.provider == "recorded":
            digest = sha256(speaker.encode("utf-8")).hexdigest()[:16]
            return VoiceProfile(
                f"recorded_{digest}",
                "recorded",
                speaker,
                "human",
                "unknown",
                "recorded",
            )
        current = self._profiles.get(speaker)
        if current is not None and current.provider == self.provider:
            return current

        palette = EDGE_PALETTE
        hint = KNOWN_HINTS.get(speaker)
        candidates = palette
        if hint:
            gender, age, temperament = hint
            scored = [
                profile
                for profile in palette
                if profile.gender == gender
                and (profile.age == age or profile.temperament == temperament)
            ]
            if scored:
                candidates = scored

        digest = int.from_bytes(sha256(speaker.encode("utf-8")).digest()[:8], "big")
        profile = candidates[digest % len(candidates)]
        self._profiles[speaker] = profile
        self._save()
        return profile

    def set_provider(self, provider: str) -> None:
        if provider not in {"recorded", "edge"}:
            raise ValueError(provider)
        self.provider = provider
