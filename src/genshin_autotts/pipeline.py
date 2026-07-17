from __future__ import annotations

import queue
import threading
import time
from hashlib import sha256
from pathlib import Path
from typing import Callable, Protocol

from .audio import AudioPlayer
from .cache import AudioCache
from .models import AudioArtifact, DialogueEvent, DialogueObservation
from .text import DialogueStabilizer
from .tts import TtsProvider
from .voice import VoiceRegistry


StatusCallback = Callable[[str], None]


def audio_cache_key(event: DialogueEvent, profile_id: str, provider: str) -> str:
    payload = f"v1\0{event.speaker}\0{event.text}\0{profile_id}\0{provider}".encode("utf-8")
    return sha256(payload).hexdigest()


class VoicePipeline:
    def __init__(
        self,
        registry: VoiceRegistry,
        tts: TtsProvider,
        cache: AudioCache,
        player: AudioPlayer,
        play_audio: bool = True,
        interrupt_audio: bool = True,
    ) -> None:
        self.registry = registry
        self.tts = tts
        self.cache = cache
        self.player = player
        self.play_audio = play_audio
        self.interrupt_audio = interrupt_audio

    def process(self, event: DialogueEvent) -> AudioArtifact:
        profile = self.registry.resolve(event.speaker)
        provider_key = getattr(self.tts, "cache_namespace", self.tts.name)
        key = audio_cache_key(event, profile.profile_id, provider_key)
        cached = self.cache.get(key)
        if cached:
            path, codec, provider = cached
            artifact = AudioArtifact(str(path), codec, provider, key, True)
        else:
            target_base = self.cache.temporary_path(key, "")
            path, codec, actual_provider = self.tts.synthesize(event, profile, target_base)
            final_path = self.cache.put(key, path, codec, actual_provider)
            artifact = AudioArtifact(str(final_path), codec, actual_provider, key, False)
        if self.play_audio:
            self.player.play(Path(artifact.path), self.interrupt_audio)
        return artifact


class ObservationSource(Protocol):
    def read(self) -> DialogueObservation: ...


class PipelineController:
    def __init__(
        self,
        source: ObservationSource,
        stabilizer: DialogueStabilizer,
        voice_pipeline: VoicePipeline,
        interval_ms: int,
        status: StatusCallback | None = None,
    ) -> None:
        self.source = source
        self.stabilizer = stabilizer
        self.voice_pipeline = voice_pipeline
        self.interval = interval_ms / 1000
        self.status = status or (lambda _message: None)
        self._play_audio_configured = voice_pipeline.play_audio
        self._stop = threading.Event()
        self._capture_thread: threading.Thread | None = None
        self._speech_thread: threading.Thread | None = None
        self._queue: queue.Queue[DialogueEvent | None] = queue.Queue(maxsize=4)
        self._last_observation_summary: str | None = None

    @property
    def running(self) -> bool:
        return bool(self._capture_thread and self._capture_thread.is_alive())

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._last_observation_summary = None
        self.voice_pipeline.play_audio = self._play_audio_configured
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._speech_thread = threading.Thread(target=self._speech_loop, daemon=True)
        self._capture_thread.start()
        self._speech_thread.start()
        self.status("识别已启动")

    def stop(self) -> None:
        self._stop.set()
        self.voice_pipeline.play_audio = False
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        self.voice_pipeline.player.stop()
        current = threading.current_thread()
        for worker in (self._capture_thread, self._speech_thread):
            if worker is not None and worker is not current:
                worker.join(timeout=1.0)
        self._capture_thread = None
        self._speech_thread = None
        self.status("识别已停止")

    def _capture_loop(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                observation = self.source.read()
                if self._stop.is_set():
                    break
                summary = f"OCR：{observation.speaker}｜{observation.text[:40]}"
                if summary != self._last_observation_summary:
                    self.status(summary)
                    self._last_observation_summary = summary
                event = self.stabilizer.observe(observation)
                if event:
                    try:
                        self._queue.put_nowait(event)
                    except queue.Full:
                        try:
                            self._queue.get_nowait()
                        except queue.Empty:
                            pass
                        self._queue.put_nowait(event)
            except Exception as exc:
                self.status(f"识别错误：{exc}")
            remaining = self.interval - (time.monotonic() - started)
            self._stop.wait(max(0.01, remaining))

    def _speech_loop(self) -> None:
        while not self._stop.is_set():
            try:
                event = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if event is None:
                return
            if self._stop.is_set():
                return
            try:
                self.status(f"生成语音：{event.speaker}：{event.text}")
                artifact = self.voice_pipeline.process(event)
                origin = "缓存" if artifact.from_cache else artifact.provider
                self.status(f"正在播放（{origin}/{artifact.codec}）")
            except Exception as exc:
                self.status(f"语音错误：{exc}")
