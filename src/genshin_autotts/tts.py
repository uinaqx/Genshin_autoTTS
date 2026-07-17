from __future__ import annotations

import asyncio
import subprocess
import wave
from hashlib import sha256
from pathlib import Path
from typing import Protocol

from .models import VoiceProfile


class TtsProvider(Protocol):
    name: str

    def synthesize(
        self, text: str, profile: VoiceProfile, target_base: Path
    ) -> tuple[Path, str, str]: ...


class OpusTranscoder:
    def __init__(self, bitrate_kbps: int = 32) -> None:
        self.bitrate_kbps = bitrate_kbps

    def transcode(self, source: Path, target: Path) -> bool:
        try:
            import imageio_ffmpeg

            executable = imageio_ffmpeg.get_ffmpeg_exe()
            subprocess.run(
                [
                    executable,
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    str(source),
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "24000",
                    "-c:a",
                    "libopus",
                    "-b:a",
                    f"{self.bitrate_kbps}k",
                    "-vbr",
                    "on",
                    str(target),
                ],
                check=True,
                capture_output=True,
            )
            return target.exists() and target.stat().st_size > 512
        except (OSError, subprocess.CalledProcessError):
            target.unlink(missing_ok=True)
            return False


class SapiTtsProvider:
    name = "sapi"

    def __init__(self, bitrate_kbps: int = 32) -> None:
        self.transcoder = OpusTranscoder(bitrate_kbps)

    def synthesize(
        self, text: str, profile: VoiceProfile, target_base: Path
    ) -> tuple[Path, str, str]:
        import pyttsx3

        wav_path = target_base.with_suffix(".wav")
        opus_path = target_base.with_suffix(".opus")
        wav_path.unlink(missing_ok=True)
        opus_path.unlink(missing_ok=True)

        engine = pyttsx3.init()
        voices = engine.getProperty("voices") or []
        if voices:
            digest = int.from_bytes(sha256(profile.profile_id.encode()).digest()[:4], "big")
            engine.setProperty("voice", voices[digest % len(voices)].id)
        base_rate = int(engine.getProperty("rate") or 180)
        engine.setProperty("rate", max(80, base_rate + profile.rate_percent * 2))
        engine.setProperty("volume", max(0.0, min(1.0, 1 + profile.volume_percent / 100)))
        engine.save_to_file(text, str(wav_path))
        engine.runAndWait()
        engine.stop()

        try:
            with wave.open(str(wav_path), "rb") as audio:
                frame_count = audio.getnframes()
        except (EOFError, OSError, wave.Error):
            frame_count = 0
        if frame_count <= 0:
            wav_path.unlink(missing_ok=True)
            raise RuntimeError("Windows SAPI did not produce a valid audio file")
        if self.transcoder.transcode(wav_path, opus_path):
            wav_path.unlink(missing_ok=True)
            return opus_path, "opus", self.name
        return wav_path, "wav", self.name


class EdgeTtsProvider:
    name = "edge"

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

        asyncio.run(create())
        if not mp3_path.exists() or mp3_path.stat().st_size == 0:
            raise RuntimeError("Edge TTS did not produce audio")
        return mp3_path, "mp3", self.name


class FallbackTtsProvider:
    def __init__(self, primary: TtsProvider, fallback: TtsProvider) -> None:
        self.primary = primary
        self.fallback = fallback
        self.name = primary.name

    def synthesize(
        self, text: str, profile: VoiceProfile, target_base: Path
    ) -> tuple[Path, str, str]:
        try:
            return self.primary.synthesize(text, profile, target_base)
        except Exception:
            fallback_profile = VoiceProfile(
                profile.profile_id,
                "sapi",
                "",
                profile.gender,
                profile.age,
                profile.temperament,
                profile.rate_percent,
                profile.volume_percent,
            )
            return self.fallback.synthesize(text, fallback_profile, target_base)
