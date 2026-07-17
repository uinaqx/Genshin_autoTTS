import json

from genshin_autotts.config import AppConfig, load_config


def test_default_uses_neural_voice_only() -> None:
    config = AppConfig()
    assert config.tts_provider == "edge"
    config.validate()


def test_legacy_sapi_config_is_migrated(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"tts_provider": "sapi"}), encoding="utf-8")
    assert load_config(path).tts_provider == "edge"
