import json

from genshin_autotts.config import AppConfig, load_config


def test_default_uses_strict_recorded_human_voice() -> None:
    config = AppConfig()
    assert config.tts_provider == "recorded"
    config.validate()


def test_legacy_sapi_config_is_migrated(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"tts_provider": "sapi"}), encoding="utf-8")
    assert load_config(path).tts_provider == "recorded"
