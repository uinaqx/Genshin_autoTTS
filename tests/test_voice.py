import json

from genshin_autotts.voice import VoiceRegistry


def test_voice_assignment_is_persistent(tmp_path) -> None:
    path = tmp_path / "profiles.json"
    first = VoiceRegistry(path, "edge")
    profile = first.resolve("测试角色")
    second = VoiceRegistry(path, "edge")
    assert second.resolve("测试角色") == profile
    assert profile.provider == "edge"
    assert profile.voice.endswith("Neural")
    assert "测试角色" in json.loads(path.read_text(encoding="utf-8"))


def test_legacy_machine_profile_is_reassigned(tmp_path) -> None:
    path = tmp_path / "profiles.json"
    path.write_text(
        json.dumps(
            {
                "派蒙": {
                    "profile_id": "sapi_bright",
                    "provider": "sapi",
                    "voice": "",
                    "gender": "female",
                    "age": "young",
                    "temperament": "bright",
                    "rate_percent": 8,
                    "volume_percent": 0,
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    registry = VoiceRegistry(path, "edge")
    assert registry.resolve("派蒙").provider == "edge"


def test_recorded_mode_uses_human_profile_without_generating_voice_mapping(tmp_path) -> None:
    path = tmp_path / "profiles.json"
    profile = VoiceRegistry(path, "recorded").resolve("真人示例")
    assert profile.provider == "recorded"
    assert profile.voice == "真人示例"
    assert not path.exists()


def test_cloud_voice_assignment_is_fixed_per_speaker_and_provider(tmp_path) -> None:
    path = tmp_path / "profiles.json"
    first = VoiceRegistry(path, "aliyun")
    profile = first.resolve("派蒙")
    second = VoiceRegistry(path, "aliyun")

    assert second.resolve("派蒙") == profile
    assert profile.provider == "aliyun"
    assert profile.gender == "female"


def test_speaker_voice_override_replaces_previous_assignment(tmp_path) -> None:
    path = tmp_path / "profiles.json"
    original = VoiceRegistry(path, "volcengine").resolve("测试角色")
    overridden = VoiceRegistry(
        path,
        "volcengine",
        {"测试角色": "custom_voice_type"},
    ).resolve("测试角色")

    assert overridden.provider == "volcengine"
    assert overridden.voice == "custom_voice_type"
    assert overridden != original
