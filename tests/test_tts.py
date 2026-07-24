import json
import sys
import wave
from datetime import datetime, timezone
from hashlib import sha256
from types import SimpleNamespace

import pytest

from genshin_autotts.models import DialogueEvent, VoiceProfile
from genshin_autotts.tts import (
    AliyunTtsProvider,
    EdgeTtsProvider,
    RecordedVoiceProvider,
    RecordingNotFoundError,
    VolcengineTtsProvider,
)


def _event(speaker: str = "真人示例", text: str = "测试") -> DialogueEvent:
    return DialogueEvent(speaker, text, datetime.now(timezone.utc))


def _profile(provider: str = "recorded") -> VoiceProfile:
    return VoiceProfile("profile", provider, "voice", "human", "adult", "recorded")


def _write_wav(path) -> str:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"\x00\x00" * 800)
    return sha256(path.read_bytes()).hexdigest()


def _write_manifest(tmp_path, digest: str, **entry_overrides):
    entry = {
        "speaker": "真人示例",
        "text": "测试",
        "path": "line.wav",
        "sha256": digest,
        "codec": "wav",
        "recorded_by": "Test Human",
    }
    entry.update(entry_overrides)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "format_version": 1,
                "pack_id": "test-human-pack",
                "pack_version": "1",
                "license": "CC0-1.0",
                "entries": [entry],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return manifest


def test_recorded_provider_copies_verified_human_recording(tmp_path) -> None:
    source = tmp_path / "line.wav"
    digest = _write_wav(source)
    provider = RecordedVoiceProvider(_write_manifest(tmp_path, digest))

    path, codec, origin = provider.synthesize(_event(), _profile(), tmp_path / "output")

    assert path.read_bytes() == source.read_bytes()
    assert codec == "wav"
    assert origin == "recorded-human"
    assert provider.cache_namespace.startswith("recorded-human:test-human-pack:1:")


def test_recorded_provider_refuses_missing_line_without_synthetic_fallback(tmp_path) -> None:
    source = tmp_path / "line.wav"
    digest = _write_wav(source)
    provider = RecordedVoiceProvider(_write_manifest(tmp_path, digest))

    with pytest.raises(RecordingNotFoundError, match="拒绝使用任何合成语音"):
        provider.synthesize(_event(text="未收录台词"), _profile(), tmp_path / "missing")

    assert not list(tmp_path.glob("missing.*"))


def test_recorded_provider_safely_corrects_one_ocr_omission_in_long_line(tmp_path) -> None:
    source = tmp_path / "line.wav"
    digest = _write_wav(source)
    manifest = _write_manifest(
        tmp_path,
        digest,
        speaker="绮良良",
        text="没来得及修缮的房子，连我都不敢睡在里面呢，一不留神塌下来可就糟了。",
    )
    provider = RecordedVoiceProvider(manifest)
    event = _event(
        speaker="绮良良",
        text="没来得及修的房子，连我都不敢睡在里面呢，一不留神塌下来可就糟了。",
    )

    path, codec, origin = provider.synthesize(event, _profile(), tmp_path / "corrected")

    assert path.read_bytes() == source.read_bytes()
    assert codec == "wav"
    assert origin == "recorded-human"


def test_recorded_provider_refuses_ambiguous_ocr_correction(tmp_path) -> None:
    source = tmp_path / "line.wav"
    digest = _write_wav(source)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "format_version": 1,
                "pack_id": "ambiguous-pack",
                "pack_version": "1",
                "license": "CC0-1.0",
                "entries": [
                    {
                        "speaker": "赛芭",
                        "text": "村子北面的花圃需要一位热心的旅人帮忙照看",
                        "path": "line.wav",
                        "sha256": digest,
                        "codec": "wav",
                    },
                    {
                        "speaker": "赛芭",
                        "text": "村子北面的菜圃需要一位热心的旅人帮忙照看",
                        "path": "line.wav",
                        "sha256": digest,
                        "codec": "wav",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    provider = RecordedVoiceProvider(manifest)
    event = _event(
        speaker="赛芭",
        text="村子北面的苗圃需要一位热心的旅人帮忙照看",
    )

    with pytest.raises(RecordingNotFoundError):
        provider.synthesize(event, _profile(), tmp_path / "ambiguous")


def test_recorded_provider_rejects_tampered_audio(tmp_path) -> None:
    source = tmp_path / "line.wav"
    _write_wav(source)
    provider = RecordedVoiceProvider(_write_manifest(tmp_path, "0" * 64))

    with pytest.raises(RuntimeError, match="完整性校验失败"):
        provider.synthesize(_event(), _profile(), tmp_path / "tampered")

    assert not list(tmp_path.glob("tampered.*"))


def test_recorded_provider_downloads_https_entry_on_demand(tmp_path, monkeypatch) -> None:
    source = tmp_path / "source.wav"
    digest = _write_wav(source)
    payload = source.read_bytes()
    manifest = _write_manifest(
        tmp_path,
        digest,
        path=None,
        url="https://audio.example.test/line.wav",
    )

    class FakeResponse:
        headers = {"Content-Length": str(len(payload))}

        def __init__(self) -> None:
            self.offset = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def geturl(self) -> str:
            return "https://cdn.example.test/line.wav"

        def read(self, size: int) -> bytes:
            chunk = payload[self.offset : self.offset + size]
            self.offset += len(chunk)
            return chunk

    monkeypatch.setattr("genshin_autotts.tts.urlopen", lambda *_args, **_kwargs: FakeResponse())
    provider = RecordedVoiceProvider(manifest)

    path, codec, origin = provider.synthesize(_event(), _profile(), tmp_path / "remote")

    assert path.read_bytes() == payload
    assert codec == "wav"
    assert origin == "recorded-human"


def test_neural_voice_failure_never_falls_back_to_machine_voice(tmp_path, monkeypatch) -> None:
    class FailingCommunicate:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def save(self, _path: str) -> None:
            raise ConnectionError("offline")

    monkeypatch.setitem(sys.modules, "edge_tts", SimpleNamespace(Communicate=FailingCommunicate))
    profile = VoiceProfile(
        "calm_female",
        "edge",
        "zh-CN-XiaoyiNeural",
        "female",
        "adult",
        "calm",
    )
    provider = EdgeTtsProvider(timeout_seconds=1, retries=0)

    with pytest.raises(RuntimeError, match="拒绝回退到传统机器音"):
        provider.synthesize(_event(text="风从山谷吹来。"), profile, tmp_path / "line")

    assert not (tmp_path / "line.mp3").exists()


class _CloudResponse:
    def __init__(self, payload: bytes, content_type: str) -> None:
        self.payload = payload
        self.headers = {
            "Content-Length": str(len(payload)),
            "Content-Type": content_type,
        }

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self.payload if size < 0 else self.payload[:size]


def test_volcengine_provider_requests_selected_voice_and_decodes_audio(
    tmp_path, monkeypatch
) -> None:
    audio = b"ID3" + b"\x01" * 1024
    response = json.dumps(
        {
            "reqid": "request-id",
            "code": 3000,
            "message": "Success",
            "sequence": -1,
            "data": __import__("base64").b64encode(audio).decode("ascii"),
        }
    ).encode("utf-8")
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _CloudResponse(response, "application/json")

    monkeypatch.setattr("genshin_autotts.tts.urlopen", fake_urlopen)
    provider = VolcengineTtsProvider("app-id", "access-token", retries=0)
    profile = VoiceProfile(
        "volc_bright_female",
        "volcengine",
        "BV001_streaming",
        "female",
        "young",
        "bright",
        7,
    )

    path, codec, origin = provider.synthesize(
        _event(speaker="派蒙", text="我们出发吧。"),
        profile,
        tmp_path / "volc",
    )

    body = json.loads(captured["request"].data.decode("utf-8"))
    assert captured["request"].get_header("Authorization") == "Bearer;access-token"
    assert body["audio"]["voice_type"] == "BV001_streaming"
    assert body["request"]["text"] == "我们出发吧。"
    assert path.read_bytes() == audio
    assert (codec, origin) == ("mp3", "volcengine")


def test_aliyun_provider_posts_text_and_accepts_audio_response(tmp_path, monkeypatch) -> None:
    audio = b"ID3" + b"\x02" * 1024
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _CloudResponse(audio, "audio/mpeg")

    monkeypatch.setattr("genshin_autotts.tts.urlopen", fake_urlopen)
    provider = AliyunTtsProvider("app-key", "access-token", retries=0)
    profile = VoiceProfile(
        "aliyun_calm_female",
        "aliyun",
        "zhixiaobai",
        "female",
        "adult",
        "calm",
        -4,
    )

    path, codec, origin = provider.synthesize(
        _event(speaker="旁白", text="风从山谷吹来。"),
        profile,
        tmp_path / "aliyun",
    )

    body = json.loads(captured["request"].data.decode("utf-8"))
    assert body["appkey"] == "app-key"
    assert body["token"] == "access-token"
    assert body["voice"] == "zhixiaobai"
    assert body["text"] == "风从山谷吹来。"
    assert path.read_bytes() == audio
    assert (codec, origin) == ("mp3", "aliyun")
