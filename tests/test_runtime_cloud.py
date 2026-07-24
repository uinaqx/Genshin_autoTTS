import pytest

from genshin_autotts.config import AppConfig
from genshin_autotts.runtime import build_voice_pipeline
from genshin_autotts.tts import AliyunTtsProvider, VolcengineTtsProvider


def test_runtime_builds_volcengine_pipeline_from_environment(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GENSHIN_AUTOTTS_HOME", str(tmp_path / "runtime"))
    monkeypatch.setenv("GENSHIN_AUTOTTS_VOLCENGINE_APP_ID", "app-id")
    monkeypatch.setenv("GENSHIN_AUTOTTS_VOLCENGINE_ACCESS_TOKEN", "token")

    pipeline = build_voice_pipeline(AppConfig(tts_provider="volcengine"), play_audio=False)

    assert isinstance(pipeline.tts, VolcengineTtsProvider)
    assert pipeline.registry.provider == "volcengine"


def test_runtime_builds_aliyun_pipeline_from_environment(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GENSHIN_AUTOTTS_HOME", str(tmp_path / "runtime"))
    monkeypatch.setenv("GENSHIN_AUTOTTS_ALIYUN_APP_KEY", "app-key")
    monkeypatch.setenv("GENSHIN_AUTOTTS_ALIYUN_ACCESS_TOKEN", "token")

    pipeline = build_voice_pipeline(AppConfig(tts_provider="aliyun"), play_audio=False)

    assert isinstance(pipeline.tts, AliyunTtsProvider)
    assert pipeline.registry.provider == "aliyun"


def test_runtime_explains_missing_cloud_credentials(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GENSHIN_AUTOTTS_HOME", str(tmp_path / "runtime"))
    monkeypatch.delenv("GENSHIN_AUTOTTS_VOLCENGINE_APP_ID", raising=False)
    monkeypatch.delenv("GENSHIN_AUTOTTS_VOLCENGINE_ACCESS_TOKEN", raising=False)

    with pytest.raises(ValueError, match="尚未配置火山引擎 API"):
        build_voice_pipeline(AppConfig(tts_provider="volcengine"), play_audio=False)
