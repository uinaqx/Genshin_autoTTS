from __future__ import annotations

import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Protocol


class AudioPlayer(Protocol):
    def play(self, path: Path, interrupt: bool = True) -> None: ...

    def stop(self) -> None: ...


class PygameAudioPlayer:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._initialized = False
        self._decoded_path: Path | None = None

    def _initialize(self) -> None:
        if self._initialized:
            return
        import pygame

        pygame.mixer.init(frequency=24000, channels=2, buffer=1024)
        self._initialized = True

    def _clear_decoded(self) -> None:
        if self._decoded_path is not None:
            self._decoded_path.unlink(missing_ok=True)
            self._decoded_path = None

    @staticmethod
    def _decode_for_playback(path: Path) -> Path:
        import imageio_ffmpeg

        handle = tempfile.NamedTemporaryFile(prefix="genshin-autotts-", suffix=".wav", delete=False)
        handle.close()
        target = Path(handle.name)
        try:
            subprocess.run(
                [
                    imageio_ffmpeg.get_ffmpeg_exe(),
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    str(path),
                    "-ac",
                    "2",
                    "-ar",
                    "24000",
                    "-c:a",
                    "pcm_s16le",
                    str(target),
                ],
                check=True,
                capture_output=True,
            )
            return target
        except (OSError, subprocess.CalledProcessError):
            target.unlink(missing_ok=True)
            raise RuntimeError(f"无法解码音频用于播放：{path.name}") from None

    def play(self, path: Path, interrupt: bool = True) -> None:
        import pygame

        with self._lock:
            self._initialize()
            if interrupt:
                pygame.mixer.music.stop()
            self._clear_decoded()
            try:
                pygame.mixer.music.load(str(path))
            except pygame.error:
                self._decoded_path = self._decode_for_playback(path)
                pygame.mixer.music.load(str(self._decoded_path))
            pygame.mixer.music.play()

    def stop(self) -> None:
        if not self._initialized:
            return
        import pygame

        with self._lock:
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
            self._clear_decoded()


class NullAudioPlayer:
    def __init__(self) -> None:
        self.played: list[Path] = []

    def play(self, path: Path, interrupt: bool = True) -> None:
        self.played.append(path)

    def stop(self) -> None:
        return
