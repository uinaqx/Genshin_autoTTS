from genshin_autotts.models import DialogueObservation
from genshin_autotts.text import DialogueStabilizer, normalize_speaker, normalize_text


def test_normalization() -> None:
    assert normalize_text("  你 好… <color=x>旅行者</color> ") == "你好...旅行者"
    assert normalize_speaker("???") == "旁白"
    assert normalize_speaker(" 派蒙：") == "派蒙"


def test_stabilizer_emits_once_and_honors_cooldown() -> None:
    stabilizer = DialogueStabilizer(3, 0.94, 200, 5)
    observation = DialogueObservation("派蒙", "旅行者，我们出发吧！")
    assert stabilizer.observe(observation, 0.0) is None
    assert stabilizer.observe(observation, 0.1) is None
    event = stabilizer.observe(observation, 0.3)
    assert event is not None
    assert event.speaker == "派蒙"
    assert stabilizer.observe(observation, 0.5) is None
    assert stabilizer.observe(observation, 6.0) is None
    assert stabilizer.observe(DialogueObservation("", ""), 6.1) is None
    assert stabilizer.observe(observation, 6.2) is None
    assert stabilizer.observe(observation, 6.3) is None
    assert stabilizer.observe(observation, 6.5) is not None


def test_typewriter_growth_does_not_emit_old_prefix() -> None:
    stabilizer = DialogueStabilizer(2, 0.95, 100, 5)
    assert stabilizer.observe(DialogueObservation("派蒙", "旅行"), 0.0) is None
    assert stabilizer.observe(DialogueObservation("派蒙", "旅行者"), 0.1) is None
    assert stabilizer.observe(DialogueObservation("派蒙", "旅行者出发"), 0.2) is None
    event = stabilizer.observe(DialogueObservation("派蒙", "旅行者出发"), 0.4)
    assert event is not None
    assert event.text == "旅行者出发"
