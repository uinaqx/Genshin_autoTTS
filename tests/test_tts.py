import sys
from types import SimpleNamespace

import pytest

from genshin_autotts.models import VoiceProfile
from genshin_autotts.tts import EdgeTtsProvider


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
        provider.synthesize("风从山谷吹来。", profile, tmp_path / "line")

    assert not (tmp_path / "line.mp3").exists()
