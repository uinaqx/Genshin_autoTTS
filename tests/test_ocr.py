from PIL import Image

from genshin_autotts.fixture import LINES, render_dialogue_scene
from genshin_autotts.models import OcrResult
from genshin_autotts.ocr import (
    RapidOcrEngine,
    ScriptedOcrEngine,
    STANDARD_DIALOGUE_LAYOUT,
    recognize_dialogue_frame,
)


def test_normalized_layout_crops_expected_pixels() -> None:
    image = Image.new("RGB", (1920, 1080))
    speaker = STANDARD_DIALOGUE_LAYOUT.speaker.crop(image)
    dialogue = STANDARD_DIALOGUE_LAYOUT.dialogue.crop(image)
    assert speaker.size == (576, 97)
    assert dialogue.size == (1152, 141)


def test_frame_diagnostics_selects_plausible_layout() -> None:
    engine = ScriptedOcrEngine(
        [
            OcrResult("派蒙", 0.99),
            OcrResult("前面好像有新的线索。", 0.98),
            OcrResult("", 0.0),
            OcrResult("按钮", 0.72),
        ]
    )
    result = recognize_dialogue_frame(Image.new("RGB", (1280, 720)), engine)
    assert result.layout == "标准底部对话"
    assert result.observation.speaker == "派蒙"
    assert result.observation.text == "前面好像有新的线索。"


def test_real_ocr_recognizes_every_production_like_fixture_line() -> None:
    engine = RapidOcrEngine()
    for line in LINES:
        result = recognize_dialogue_frame(render_dialogue_scene(line), engine)
        assert result.layout == "标准底部对话"
        assert result.observation.speaker == line.speaker
        assert result.observation.text == line.text
        assert result.observation.speaker_confidence >= 0.9
        assert result.observation.text_confidence >= 0.9
