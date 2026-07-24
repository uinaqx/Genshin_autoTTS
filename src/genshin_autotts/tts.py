from __future__ import annotations

import asyncio
import base64
import json
import shutil
import time
import uuid
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
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


class CloudTtsError(RuntimeError):
    """Raised when a configured cloud speech service rejects synthesis."""


def _read_limited(response, maximum: int) -> bytes:
    content_length = response.headers.get("Content-Length")
    if content_length and int(content_length) > maximum:
        raise CloudTtsError("云端语音响应超过安全大小上限")
    payload = response.read(maximum + 1)
    if len(payload) > maximum:
        raise CloudTtsError("云端语音响应超过安全大小上限")
    return payload


def _write_audio(target: Path, payload: bytes) -> None:
    if len(payload) < 128:
        raise CloudTtsError("云端语音响应为空或不完整")
    temporary = target.with_suffix(target.suffix + ".part")
    target.unlink(missing_ok=True)
    temporary.unlink(missing_ok=True)
    try:
        temporary.write_bytes(payload)
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        raise


class VolcengineTtsProvider:
    """Synthesize one stabilized dialogue line with Volcengine's HTTP TTS API."""

    name = "volcengine"
    endpoint = "https://openspeech.bytedance.com/api/v1/tts"

    def __init__(
        self,
        app_id: str,
        access_token: str,
        *,
        cluster: str = "volcano_tts",
        timeout_seconds: int = 35,
        retries: int = 2,
        max_response_bytes: int = 16 * 1024 * 1024,
    ) -> None:
        if not app_id.strip() or not access_token.strip():
            raise ValueError("火山引擎 App ID 和 Access Token 不能为空")
        self.app_id = app_id.strip()
        self.access_token = access_token.strip()
        self.cluster = cluster.strip()
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.max_response_bytes = max_response_bytes
        app_digest = sha256(self.app_id.encode("utf-8")).hexdigest()[:12]
        self.cache_namespace = f"{self.name}:http-v1:{app_digest}:{self.cluster}"

    def synthesize(
        self, event: DialogueEvent, profile: VoiceProfile, target_base: Path
    ) -> tuple[Path, str, str]:
        text_bytes = event.text.encode("utf-8")
        if not text_bytes or len(text_bytes) > 1024:
            raise CloudTtsError("火山引擎单次合成文本必须为 1～1024 个 UTF-8 字节")
        if profile.provider != self.name:
            raise CloudTtsError("角色音色与火山引擎提供商不匹配")

        speed_ratio = max(0.5, min(2.0, 1 + profile.rate_percent / 100))
        volume_ratio = max(0.5, min(2.0, 1 + profile.volume_percent / 100))
        request_body = {
            "app": {
                "appid": self.app_id,
                "token": self.access_token,
                "cluster": self.cluster,
            },
            "user": {"uid": "genshin-autotts-local"},
            "audio": {
                "voice_type": profile.voice,
                "encoding": "mp3",
                "speed_ratio": speed_ratio,
                "volume_ratio": volume_ratio,
                "pitch_ratio": 1.0,
            },
            "request": {
                "reqid": str(uuid.uuid4()),
                "text": event.text,
                "text_type": "plain",
                "operation": "query",
            },
        }
        payload = json.dumps(request_body, ensure_ascii=False).encode("utf-8")
        request = Request(
            self.endpoint,
            data=payload,
            headers={
                "Authorization": f"Bearer;{self.access_token}",
                "Content-Type": "application/json",
                "User-Agent": "GenshinAutoTTS/0.4 (Volcengine cloud TTS)",
            },
            method="POST",
        )
        result = self._request_json(request)
        code = int(result.get("code", -1))
        if code != 3000:
            message = str(result.get("message") or "未知错误")
            raise CloudTtsError(f"火山引擎合成失败（{code}）：{message}")
        encoded_audio = result.get("data")
        if not isinstance(encoded_audio, str) or not encoded_audio:
            raise CloudTtsError("火山引擎响应缺少音频数据")
        try:
            audio = base64.b64decode(encoded_audio, validate=True)
        except ValueError as exc:
            raise CloudTtsError("火山引擎返回了无效的 Base64 音频") from exc
        target = target_base.with_suffix(".mp3")
        _write_audio(target, audio)
        return target, "mp3", self.name

    def _request_json(self, request: Request) -> dict:
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    raw = _read_limited(response, self.max_response_bytes)
                result = json.loads(raw.decode("utf-8"))
                if not isinstance(result, dict):
                    raise CloudTtsError("火山引擎返回格式无效")
                code = int(result.get("code", -1))
                if code in {3003, 3005, 3030, 3031, 3032, 3040} and attempt < self.retries:
                    time.sleep(0.25 * (2**attempt))
                    continue
                return result
            except (HTTPError, URLError, TimeoutError, OSError, UnicodeError, ValueError) as exc:
                last_error = exc
                retryable = not isinstance(exc, HTTPError) or exc.code == 429 or exc.code >= 500
                if attempt >= self.retries or not retryable:
                    break
                time.sleep(0.25 * (2**attempt))
        raise CloudTtsError(f"无法连接火山引擎语音服务：{last_error}") from last_error


class AliyunTtsProvider:
    """Synthesize one stabilized dialogue line with Alibaba Cloud NLS REST."""

    name = "aliyun"
    endpoints = {
        "auto": "https://nls-gateway.aliyuncs.com/stream/v1/tts",
        "shanghai": "https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/tts",
        "beijing": "https://nls-gateway-cn-beijing.aliyuncs.com/stream/v1/tts",
        "shenzhen": "https://nls-gateway-cn-shenzhen.aliyuncs.com/stream/v1/tts",
        "singapore": "https://nls-gateway-ap-southeast-1.aliyuncs.com/stream/v1/tts",
    }

    def __init__(
        self,
        app_key: str,
        access_token: str,
        *,
        region: str = "auto",
        timeout_seconds: int = 35,
        retries: int = 2,
        max_response_bytes: int = 16 * 1024 * 1024,
    ) -> None:
        if not app_key.strip() or not access_token.strip():
            raise ValueError("阿里云 AppKey 和 Access Token 不能为空")
        if region not in self.endpoints:
            raise ValueError(f"不支持的阿里云地域：{region}")
        self.app_key = app_key.strip()
        self.access_token = access_token.strip()
        self.endpoint = self.endpoints[region]
        self.region = region
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.max_response_bytes = max_response_bytes
        app_digest = sha256(self.app_key.encode("utf-8")).hexdigest()[:12]
        self.cache_namespace = f"{self.name}:nls-rest:{app_digest}:{region}"

    def synthesize(
        self, event: DialogueEvent, profile: VoiceProfile, target_base: Path
    ) -> tuple[Path, str, str]:
        if not event.text or len(event.text) > 300:
            raise CloudTtsError("阿里云 NLS 单次合成文本必须为 1～300 个字符")
        if profile.provider != self.name:
            raise CloudTtsError("角色音色与阿里云提供商不匹配")

        body = {
            "appkey": self.app_key,
            "token": self.access_token,
            "text": event.text,
            "format": "mp3",
            "sample_rate": 16000,
            "voice": profile.voice,
            "volume": max(0, min(100, 50 + profile.volume_percent)),
            "speech_rate": max(-500, min(500, profile.rate_percent * 5)),
            "pitch_rate": 0,
        }
        request = Request(
            self.endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "GenshinAutoTTS/0.4 (Aliyun NLS TTS)",
            },
            method="POST",
        )
        audio = self._request_audio(request)
        target = target_base.with_suffix(".mp3")
        _write_audio(target, audio)
        return target, "mp3", self.name

    def _request_audio(self, request: Request) -> bytes:
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    content_type = (response.headers.get("Content-Type") or "").lower()
                    payload = _read_limited(response, self.max_response_bytes)
                if content_type.startswith("audio/"):
                    return payload
                detail = self._error_detail(payload)
                raise CloudTtsError(f"阿里云合成失败：{detail}")
            except CloudTtsError:
                raise
            except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
                last_error = exc
                retryable = not isinstance(exc, HTTPError) or exc.code == 429 or exc.code >= 500
                if attempt >= self.retries or not retryable:
                    break
                time.sleep(0.25 * (2**attempt))
        raise CloudTtsError(f"无法连接阿里云语音服务：{last_error}") from last_error

    @staticmethod
    def _error_detail(payload: bytes) -> str:
        try:
            result = json.loads(payload.decode("utf-8"))
        except (UnicodeError, ValueError):
            return payload[:240].decode("utf-8", errors="replace") or "未知错误"
        if isinstance(result, dict):
            status = result.get("status")
            message = result.get("message") or result.get("result") or "未知错误"
            return f"{status} {message}".strip()
        return "未知错误"


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
