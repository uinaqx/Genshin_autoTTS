import json

from genshin_autotts.config import AppConfig, load_config


def test_default_uses_cloud_voice_without_requiring_a_recording_pack() -> None:
    config = AppConfig()
    assert config.tts_provider == "volcengine"
    config.validate()


def test_legacy_sapi_config_is_migrated(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"tts_provider": "sapi"}), encoding="utf-8")
    assert load_config(path).tts_provider == "recorded"


def test_cloud_provider_settings_and_voice_overrides_round_trip(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "tts_provider": "aliyun",
                "aliyun_region": "beijing",
                "speaker_voice_overrides": {"派蒙": "zhimi_emo"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.tts_provider == "aliyun"
    assert config.aliyun_region == "beijing"
    assert config.speaker_voice_overrides == {"派蒙": "zhimi_emo"}
