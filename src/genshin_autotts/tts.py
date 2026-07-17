from __future__ import annotations

import asyncio
import json
import shutil
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from rapidfuzz.fuzz import ratio

from .models import DialogueEvent, VoiceProfile
from .text import normalize_match_text, normalize_speaker, normalize_text


class TtsProvider(Protocol):
    name: str
    cache_namespace: str

    def synthesize(
        self, event: DialogueEvent, profile: VoiceProfile, target_base: Path
    ) -> tuple[Path, str, str]: ...


class RecordingNotFoundError(RuntimeError):
    """Raised when strict human-recording mode has no safe matching line."""


@dataclass(frozen=True)
class RecordingEntry:
    speaker: str
    text: str
    sha256: str
    codec: str
    path: str | None = None
    url: str | None = None
    recorded_by: str = ""
    source_url: str = ""


class RecordedVoiceProvider:
    """Resolve dialogue lines to verified recordings made by real people.

    Audio is copied or downloaded only after its SHA-256 digest matches the
    manifest. Missing entries are fatal by design: this provider never invokes
    a synthesizer and never falls back to a machine-generated voice. Matching
    is exact after normalization unless a long OCR line has one unique,
    extremely similar candidate for the same speaker.
    """

    name = "recorded-human"
    _allowed_codecs = {"wav", "mp3", "ogg", "opus"}

    def __init__(
        self,
        manifest_path: Path,
        *,
        timeout_seconds: int = 30,
        max_download_bytes: int = 20 * 1024 * 1024,
    ) -> None:
        self.manifest_path = manifest_path.resolve()
        self.timeout_seconds = timeout_seconds
        self.max_download_bytes = max_download_bytes
        raw_bytes = self.manifest_path.read_bytes()
        raw = json.loads(raw_bytes.decode("utf-8"))
        if raw.get("format_version") != 1:
            raise ValueError("真人录音包 format_version 必须为 1")
        self.pack_id = str(raw.get("pack_id", "")).strip()
        self.pack_version = str(raw.get("pack_version", "")).strip()
        self.license = str(raw.get("license", "")).strip()
        if not self.pack_id or not self.pack_version or not self.license:
            raise ValueError("真人录音包必须声明 pack_id、pack_version 和 license")
        self.cache_namespace = (
            f"{self.name}:{self.pack_id}:{self.pack_version}:"
            f"{sha256(raw_bytes).hexdigest()[:16]}"
        )
        self._entries: dict[tuple[str, str], RecordingEntry] = {}
        self._speaker_entries: dict[str, list[tuple[str, RecordingEntry]]] = {}
        for item in raw.get("entries", []):
            entry = self._parse_entry(item)
            key = self._key(entry.speaker, entry.text)
            if key in self._entries:
                raise ValueError(f"真人录音包存在重复台词：{entry.speaker}：{entry.text}")
            self._entries[key] = entry
            self._speaker_entries.setdefault(key[0], []).append((key[1], entry))
        if not self._entries:
            raise ValueError("真人录音包没有任何 entries")

    def _parse_entry(self, item: object) -> RecordingEntry:
        if not isinstance(item, dict):
            raise ValueError("真人录音包 entries 必须是对象数组")
        entry = RecordingEntry(
            speaker=str(item.get("speaker", "")).strip(),
            text=str(item.get("text", "")).strip(),
            sha256=str(item.get("sha256", "")).lower().strip(),
            codec=str(item.get("codec", "")).lower().lstrip(".").strip(),
            path=str(item["path"]).strip() if item.get("path") else None,
            url=str(item["url"]).strip() if item.get("url") else None,
            recorded_by=str(item.get("recorded_by", "")).strip(),
            source_url=str(item.get("source_url", "")).strip(),
        )
        if not entry.speaker or not entry.text:
            raise ValueError("真人录音条目必须声明 speaker 和 text")
        if len(entry.sha256) != 64 or any(c not in "0123456789abcdef" for c in entry.sha256):
            raise ValueError(f"真人录音 SHA-256 无效：{entry.speaker}：{entry.text}")
        if entry.codec not in self._allowed_codecs:
            raise ValueError(f"不支持的真人录音编码：{entry.codec}")
        if bool(entry.path) == bool(entry.url):
            raise ValueError("真人录音条目必须且只能提供 path 或 url")
        if entry.url and urlparse(entry.url).scheme != "https":
            raise ValueError("远程真人录音只允许 HTTPS URL")
        return entry

    @staticmethod
    def _key(speaker: str, text: str) -> tuple[str, str]:
        return normalize_speaker(speaker), normalize_text(text)

    def synthesize(
        self, event: DialogueEvent, profile: VoiceProfile, target_base: Path
    ) -> tuple[Path, str, str]:
        del profile
        entry = self._resolve_entry(event.speaker, event.text)
        if entry is None:
            raise RecordingNotFoundError(
                f"真人录音包中没有匹配台词：{event.speaker}：{event.text}。"
                "严格模式已拒绝使用任何合成语音替代。"
            )
        target = target_base.with_suffix(f".{entry.codec}")
        temporary = target.with_suffix(target.suffix + ".part")
        target.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)
        try:
            if entry.path:
                source = self._resolve_local(entry.path)
                if source.stat().st_size > self.max_download_bytes:
                    raise RuntimeError("真人录音超过单文件大小上限")
                shutil.copyfile(source, temporary)
            else:
                self._download(entry.url or "", temporary)
            actual_digest = sha256(temporary.read_bytes()).hexdigest()
            if actual_digest != entry.sha256:
                raise RuntimeError(
                    f"真人录音完整性校验失败：期望 {entry.sha256}，实际 {actual_digest}"
                )
            if temporary.stat().st_size < 44:
                raise RuntimeError("真人录音文件为空或损坏")
            temporary.replace(target)
            return target, entry.codec, self.name
        except Exception:
            temporary.unlink(missing_ok=True)
            target.unlink(missing_ok=True)
            raise

    def _resolve_entry(self, speaker: str, text: str) -> RecordingEntry | None:
        speaker_key, text_key = self._key(speaker, text)
        exact = self._entries.get((speaker_key, text_key))
        if exact is not None:
            return exact

        # Short lines and ambiguous alternatives are deliberately never guessed.
        # This narrow correction covers common OCR omissions in long subtitles
        # while preserving the strict no-wrong-line behavior.
        correction_text = normalize_match_text(text_key)
        if len(correction_text) < 16:
            return None
        candidates: list[tuple[float, RecordingEntry]] = []
        for expected_text, entry in self._speaker_entries.get(speaker_key, []):
            expected_correction_text = normalize_match_text(expected_text)
            if abs(len(expected_correction_text) - len(correction_text)) > 2:
                continue
            similarity = ratio(expected_correction_text, correction_text) / 100
            if similarity >= 0.98:
                candidates.append((similarity, entry))
        candidates.sort(key=lambda item: item[0], reverse=True)
        if not candidates:
            return None
        if len(candidates) > 1 and candidates[0][0] - candidates[1][0] < 0.015:
            return None
        return candidates[0][1]

    def _resolve_local(self, relative_path: str) -> Path:
        if Path(relative_path).is_absolute():
            raise ValueError("真人录音包中的 path 必须是相对路径")
        root = self.manifest_path.parent.resolve()
        source = (root / relative_path).resolve()
        if root != source and root not in source.parents:
            raise ValueError("真人录音路径越出了录音包目录")
        if not source.is_file():
            raise FileNotFoundError(f"真人录音文件不存在：{source}")
        return source

    def _download(self, url: str, target: Path) -> None:
        request = Request(
            url,
            headers={"User-Agent": "GenshinAutoTTS/0.3 (strict recorded-human mode)"},
        )
        with urlopen(request, timeout=self.timeout_seconds) as response, target.open("wb") as out:
            final_url = response.geturl()
            if urlparse(final_url).scheme != "https":
                raise RuntimeError("真人录音下载被重定向到非 HTTPS 地址")
            length = response.headers.get("Content-Length")
            if length and int(length) > self.max_download_bytes:
                raise RuntimeError("真人录音超过单文件下载上限")
            total = 0
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > self.max_download_bytes:
                    raise RuntimeError("真人录音超过单文件下载上限")
                out.write(chunk)


class EdgeTtsProvider:
    """Optional synthetic neural voice mode; never used by recorded mode."""

    name = "edge"
    cache_namespace = name

    def __init__(self, timeout_seconds: int = 35, retries: int = 2) -> None:
        self.timeout_seconds = timeout_seconds
        self.retries = retries

    def synthesize(
        self, event: DialogueEvent, profile: VoiceProfile, target_base: Path
    ) -> tuple[Path, str, str]:
        import edge_tts

        mp3_path = target_base.with_suffix(".mp3")
        mp3_path.unlink(missing_ok=True)

        async def create() -> None:
            rate = f"{profile.rate_percent:+d}%"
            volume = f"{profile.volume_percent:+d}%"
            communicate = edge_tts.Communicate(
                event.text, profile.voice, rate=rate, volume=volume
            )
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
            "神经合成语音生成失败，已拒绝回退到传统机器音。请检查网络后重试"
            f"{detail}"
        )
