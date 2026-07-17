from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

from .capture import ScreenCapture
from .models import DialogueObservation, OcrResult, Region


@dataclass(frozen=True)
class NormalizedRegion:
    """A region expressed as fractions of a complete frame."""

    left: float
    top: float
    width: float
    height: float

    def crop(self, image: Image.Image) -> Image.Image:
        left = round(image.width * self.left)
        top = round(image.height * self.top)
        right = round(image.width * (self.left + self.width))
        bottom = round(image.height * (self.top + self.height))
        return image.crop((left, top, right, bottom))


@dataclass(frozen=True)
class DialogueLayout:
    name: str
    speaker: NormalizedRegion
    dialogue: NormalizedRegion


@dataclass(frozen=True)
class FrameOcrResult:
    layout: str
    observation: DialogueObservation
    score: float


# Real screenshots show two recurring arrangements. Normal dialogue sits near the
# bottom edge; dialogue choices and some ultrawide captures move the line upward.
STANDARD_DIALOGUE_LAYOUT = DialogueLayout(
    "标准底部对话",
    NormalizedRegion(0.35, 0.72, 0.30, 0.09),
    NormalizedRegion(0.20, 0.79, 0.60, 0.13),
)
RAISED_DIALOGUE_LAYOUT = DialogueLayout(
    "上移对话/选项",
    NormalizedRegion(0.35, 0.55, 0.30, 0.09),
    NormalizedRegion(0.20, 0.63, 0.60, 0.14),
)
GENSHIN_DIALOGUE_LAYOUTS = (STANDARD_DIALOGUE_LAYOUT, RAISED_DIALOGUE_LAYOUT)


class OcrEngine(Protocol):
    def recognize(self, image: Image.Image) -> OcrResult: ...


class RapidOcrEngine:
    def __init__(self) -> None:
        self._engine = None

    def _load(self):
        if self._engine is None:
            from rapidocr_onnxruntime import RapidOCR

            self._engine = RapidOCR()
        return self._engine

    @staticmethod
    def preprocess(image: Image.Image) -> Image.Image:
        image = image.convert("RGB")
        if image.width < 900:
            scale = min(2.0, 900 / max(1, image.width))
            image = image.resize(
                (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
                Image.Resampling.LANCZOS,
            )
        image = ImageEnhance.Contrast(image).enhance(1.25)
        return image.filter(ImageFilter.SHARPEN)

    def recognize(self, image: Image.Image) -> OcrResult:
        processed = self.preprocess(image)
        results, _elapsed = self._load()(np.asarray(processed))
        if not results:
            return OcrResult("", 0.0)

        def position(item) -> tuple[float, float]:
            box = item[0]
            return min(point[1] for point in box), min(point[0] for point in box)

        ordered = sorted(results, key=position)
        text = "".join(str(item[1]).strip() for item in ordered if str(item[1]).strip())
        scores = [float(item[2]) for item in ordered if len(item) > 2]
        confidence = sum(scores) / len(scores) if scores else 0.0
        return OcrResult(text, confidence)


def _frame_result_score(speaker: OcrResult, dialogue: OcrResult) -> float:
    """Prefer confident results shaped like one speaker plus a complete line."""

    speaker_length = len(speaker.text.strip())
    dialogue_length = len(dialogue.text.strip())
    score = speaker.confidence + dialogue.confidence * 1.25
    if 1 <= speaker_length <= 12:
        score += 0.7
    elif speaker_length > 20:
        score -= 0.8
    if dialogue_length >= 4:
        score += 1.0
    elif not dialogue_length:
        score -= 1.0
    if dialogue_length > speaker_length:
        score += 0.25
    return score


def recognize_dialogue_frame(
    image: Image.Image,
    ocr: OcrEngine | None = None,
    layouts: tuple[DialogueLayout, ...] = GENSHIN_DIALOGUE_LAYOUTS,
) -> FrameOcrResult:
    """Diagnose a complete screenshot using common Genshin dialogue layouts.

    Runtime capture still uses the user's exact screen regions. This helper is
    intentionally for imported screenshots, regression checks, and calibration.
    """

    if not layouts:
        raise ValueError("At least one dialogue layout is required")
    engine = ocr or RapidOcrEngine()
    candidates: list[FrameOcrResult] = []
    for layout in layouts:
        speaker = engine.recognize(layout.speaker.crop(image))
        dialogue = engine.recognize(layout.dialogue.crop(image))
        observation = DialogueObservation(
            speaker=speaker.text,
            text=dialogue.text,
            speaker_confidence=speaker.confidence,
            text_confidence=dialogue.confidence,
        ).with_timestamp()
        score = _frame_result_score(speaker, dialogue)
        aspect_ratio = image.width / max(1, image.height)
        if aspect_ratio >= 2.05 and layout == RAISED_DIALOGUE_LAYOUT:
            score += 0.35
        candidates.append(
            FrameOcrResult(
                layout=layout.name,
                observation=observation,
                score=score,
            )
        )
    return max(candidates, key=lambda item: item.score)


class ScriptedOcrEngine:
    def __init__(self, responses: list[OcrResult]) -> None:
        self._responses = iter(responses)

    def recognize(self, image: Image.Image) -> OcrResult:
        return next(self._responses)


@dataclass
class DesktopObservationSource:
    capture: ScreenCapture
    ocr: OcrEngine
    speaker_region: Region
    dialogue_region: Region

    def read(self) -> DialogueObservation:
        speaker_image = self.capture.capture(self.speaker_region)
        dialogue_image = self.capture.capture(self.dialogue_region)
        speaker = self.ocr.recognize(speaker_image)
        dialogue = self.ocr.recognize(dialogue_image)
        return DialogueObservation(
            speaker=speaker.text,
            text=dialogue.text,
            speaker_confidence=speaker.confidence,
            text_confidence=dialogue.confidence,
        ).with_timestamp()
