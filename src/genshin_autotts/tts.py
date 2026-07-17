from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Protocol

from .models import VoiceProfile


class TtsProvider(Protocol):
    name: str

    def synthesize(
        self, text: str, profile: VoiceProfile, target_base: Path
    ) -> tuple[Path, str, str]: ...


class EdgeTtsProvider:
    name = "edge"

    def __init__(self, timeout_seconds: int = 35, retries: int = 2) -> None:
        self.timeout_seconds = timeout_seconds
        self.retries = retries

    def synthesize(
        self, text: str, profile: VoiceProfile, target_base: Path
    ) -> tuple[Path, str, str]:
        import edge_tts

        mp3_path = target_base.with_suffix(".mp3")
        mp3_path.unlink(missing_ok=True)

        async def create() -> None:
            rate = f"{profile.rate_percent:+d}%"
            volume = f"{profile.volume_percent:+d}%"
            communicate = edge_tts.Communicate(text, profile.voice, rate=rate, volume=volume)
            await communicate.save(str(mp3_path))

        last_error: Exception | None = None
        for _attempt in range(self.retries + 1):
            try:
                asyncio.run(asyncio.wait_for(create(), timeout=self.timeout_seconds))
                if mp3_path.exists() and mp3_path.stat().st_size > 512:
                    return mp3_path, "mp3", self.name
            except Exception as exc:
                last_error = exc
            mp3_path.unlink(missing_ok=True)

        detail = f"：{last_error}" if last_error else ""
        raise RuntimeError(
            "高自然度神经人声生成失败，已拒绝回退到传统机器音。请检查网络后重试"
            f"{detail}"
        )
