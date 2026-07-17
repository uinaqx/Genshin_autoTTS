from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PIL import Image
from rapidfuzz.fuzz import ratio

from .ocr import RapidOcrEngine, recognize_dialogue_frame
from .text import normalize_match_text, normalize_speaker, normalize_text


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def collect_image_paths(values: Iterable[str]) -> list[Path]:
    images: list[Path] = []
    for value in values:
        path = Path(value).expanduser()
        if path.is_dir():
            images.extend(
                candidate
                for candidate in sorted(path.iterdir())
                if candidate.is_file() and candidate.suffix.lower() in IMAGE_EXTENSIONS
            )
        elif path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            images.append(path)
        else:
            raise ValueError(f"不是支持的截图或目录：{path}")
    if not images:
        raise ValueError("没有找到可诊断的截图")
    return images


def _load_expectations(path: str | None) -> dict[str, dict[str, str]]:
    if not path:
        return {}
    import json

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("截图期望文件必须是以文件名为键的 JSON 对象")
    return payload


def run_screenshot_qa(values: Iterable[str], expectations_path: str | None = None) -> dict:
    paths = collect_image_paths(values)
    expectations = _load_expectations(expectations_path)
    engine = RapidOcrEngine()
    results = []
    passed = 0
    matched = 0
    for path in paths:
        with Image.open(path) as image:
            result = recognize_dialogue_frame(image.convert("RGB"), engine)
        observation = result.observation
        valid = bool(observation.speaker.strip() and observation.text.strip())
        passed += int(valid)
        item = {
            "file": str(path),
            "layout": result.layout,
            "speaker": observation.speaker,
            "text": observation.text,
            "speaker_confidence": round(observation.speaker_confidence, 4),
            "text_confidence": round(observation.text_confidence, 4),
            "recognized": valid,
        }
        expected = expectations.get(path.name) or expectations.get(str(path))
        if expected:
            expected_speaker = str(expected.get("speaker", ""))
            expected_text = str(expected.get("text", ""))
            speaker_match = normalize_speaker(observation.speaker) == normalize_speaker(
                expected_speaker
            )
            observed_normalized = normalize_text(observation.text)
            expected_normalized = normalize_text(expected_text)
            if observed_normalized == expected_normalized:
                text_similarity = 1.0
            else:
                text_similarity = ratio(
                    normalize_match_text(observation.text),
                    normalize_match_text(expected_text),
                ) / 100
            safe_match = speaker_match and text_similarity >= 0.98
            matched += int(safe_match)
            item.update(
                {
                    "expected_speaker": expected_speaker,
                    "expected_text": expected_text,
                    "speaker_match": speaker_match,
                    "text_similarity": round(text_similarity, 4),
                    "safe_match": safe_match,
                }
            )
        results.append(item)
    report = {
        "total": len(results),
        "recognized": passed,
        "recognition_rate": round(passed / len(results), 4),
        "results": results,
    }
    if expectations:
        report["expected"] = len(expectations)
        report["safe_matches"] = matched
        report["safe_match_rate"] = round(matched / len(expectations), 4)
    return report
