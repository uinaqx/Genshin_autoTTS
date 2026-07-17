import json

from genshin_autotts.voice import VoiceRegistry


def test_voice_assignment_is_persistent(tmp_path) -> None:
    path = tmp_path / "profiles.json"
    first = VoiceRegistry(path, "sapi")
    profile = first.resolve("测试角色")
    second = VoiceRegistry(path, "sapi")
    assert second.resolve("测试角色") == profile
    assert "测试角色" in json.loads(path.read_text(encoding="utf-8"))


def test_provider_change_reassigns_profile(tmp_path) -> None:
    path = tmp_path / "profiles.json"
    registry = VoiceRegistry(path, "sapi")
    assert registry.resolve("派蒙").provider == "sapi"
    registry.set_provider("edge")
    assert registry.resolve("派蒙").provider == "edge"
