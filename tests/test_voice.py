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
