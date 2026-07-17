from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

from .capture import ScreenCapture
from .models import DialogueObservation, OcrResult, Region


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
