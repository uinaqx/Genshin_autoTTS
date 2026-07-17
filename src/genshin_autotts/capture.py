from __future__ import annotations

from typing import Protocol

import mss
from PIL import Image

from .models import Region


class ScreenCapture(Protocol):
    def capture(self, region: Region) -> Image.Image: ...


class MssScreenCapture:
    """Read screen pixels through the operating system without touching game memory."""

    def capture(self, region: Region) -> Image.Image:
        with mss.mss() as session:
            frame = session.grab(region.as_mss())
            return Image.frombytes("RGB", frame.size, frame.bgra, "raw", "BGRX")


class StaticImageCapture:
    def __init__(self, images: dict[tuple[int, int, int, int], Image.Image]) -> None:
        self._images = images

    def capture(self, region: Region) -> Image.Image:
        key = (region.left, region.top, region.width, region.height)
        return self._images[key].copy()
