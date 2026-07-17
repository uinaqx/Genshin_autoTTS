from __future__ import annotations

import os
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageTk

from .ocr import STANDARD_DIALOGUE_LAYOUT


@dataclass(frozen=True)
class FixtureLine:
    speaker: str
    text: str
    palette: str


LINES = (
    FixtureLine("绮良良", "没来得及修好的房子，连我都不敢睡在里面呢。", "meadow"),
    FixtureLine("奥比奇", "山花开谢年复年，远道而来的旅人终于到了。", "ruins"),
    FixtureLine("赛芭", "村子北面的苗圃，需要有人帮忙照看新种下的花。", "sunset"),
    FixtureLine("派蒙", "前面好像有新的线索，我们过去仔细看看吧！", "night"),
)


PALETTES = {
    "meadow": ("#82c7dd", "#5a9b92", "#244c58", "#8dc876"),
    "ruins": ("#385a68", "#213c43", "#142a34", "#4d7567"),
    "sunset": ("#d59a7d", "#866979", "#3d4058", "#9c765f"),
    "night": ("#243f68", "#182847", "#101a31", "#315a5a"),
}


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    windows = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    names = ("msyhbd.ttc", "msyh.ttc") if bold else ("msyh.ttc", "simhei.ttf")
    for name in names:
        path = windows / name
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default(size=size)


def _gradient(image: Image.Image, top: str, bottom: str) -> None:
    draw = ImageDraw.Draw(image)
    start = _hex_to_rgb(top)
    end = _hex_to_rgb(bottom)
    for y in range(image.height):
        ratio = y / max(1, image.height - 1)
        color = tuple(round(a + (b - a) * ratio) for a, b in zip(start, end))
        draw.line((0, y, image.width, y), fill=color)


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    lines: list[str] = []
    current = ""
    for character in text:
        candidate = current + character
        if current and draw.textlength(candidate, font=font) > max_width:
            lines.append(current)
            current = character
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def _draw_scene_background(image: Image.Image, palette: str) -> None:
    sky, horizon, shadow, foliage = PALETTES[palette]
    _gradient(image, sky, shadow)
    draw = ImageDraw.Draw(image, "RGBA")
    width, height = image.size

    # Distant terrain and architecture. These are deliberately original shapes,
    # while matching the contrast and visual density of an in-game dialogue scene.
    draw.polygon(
        [(0, height * 0.43), (width * 0.17, height * 0.24), (width * 0.34, height * 0.44),
         (width * 0.53, height * 0.20), (width * 0.76, height * 0.43), (width, height * 0.26),
         (width, height * 0.66), (0, height * 0.66)],
        fill=(*_hex_to_rgb(horizon), 220),
    )
    draw.rectangle((0, height * 0.58, width, height), fill=(*_hex_to_rgb(foliage), 215))
    draw.polygon(
        [(0, height), (0, height * 0.72), (width * 0.27, height * 0.61),
         (width * 0.56, height * 0.69), (width, height * 0.58), (width, height)],
        fill=(24, 42, 48, 170),
    )

    # Stylised trees, a stone arch and two character silhouettes.
    for x, y, radius in ((0.08, 0.40, 0.10), (0.17, 0.34, 0.13), (0.86, 0.36, 0.12)):
        draw.ellipse(
            ((x - radius) * width, (y - radius) * height,
             (x + radius) * width, (y + radius) * height),
            fill=(26, 74, 69, 205),
        )
    draw.rectangle((width * 0.73, height * 0.25, width * 0.77, height * 0.64), fill=(58, 66, 72, 220))
    draw.rectangle((width * 0.89, height * 0.25, width * 0.93, height * 0.64), fill=(58, 66, 72, 220))
    draw.arc((width * 0.72, height * 0.16, width * 0.94, height * 0.55), 180, 360, fill=(185, 181, 158, 210), width=7)
    for center_x, body_color in ((0.36, (45, 72, 83, 235)), (0.66, (79, 63, 65, 235))):
        draw.ellipse((width * (center_x - 0.025), height * 0.35,
                      width * (center_x + 0.025), height * 0.44), fill=(211, 177, 151, 235))
        draw.polygon(
            [(width * center_x, height * 0.41), (width * (center_x - 0.07), height * 0.70),
             (width * (center_x + 0.07), height * 0.70)],
            fill=body_color,
        )

    # Small HUD-like shapes add realistic OCR distractions outside the selected regions.
    draw.ellipse((26, 24, 154, 152), outline=(238, 242, 235, 165), width=3)
    draw.ellipse((39, 37, 141, 139), fill=(33, 70, 76, 145))
    draw.text((28, 170), "◆ 追踪中的任务", font=_font(16, True), fill=(245, 241, 219, 220))
    draw.text((47, 196), "前往远处的遗迹", font=_font(14), fill=(245, 241, 219, 190))
    for index in range(5):
        x = width - 220 + index * 40
        draw.ellipse((x, 32, x + 25, 57), outline=(250, 250, 245, 185), width=2)

    # A soft bottom vignette preserves the game's transparent-subtitle behavior.
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    shade = ImageDraw.Draw(overlay)
    start_y = round(height * 0.64)
    for y in range(start_y, height):
        alpha = round(105 * ((y - start_y) / max(1, height - start_y)))
        shade.line((0, y, width, y), fill=(7, 12, 20, alpha))
    image.alpha_composite(overlay)


def render_dialogue_scene(
    line: FixtureLine,
    size: tuple[int, int] = (1280, 720),
) -> Image.Image:
    """Render a copyright-safe scene with production-like dialogue placement."""

    image = Image.new("RGBA", size, "black")
    _draw_scene_background(image, line.palette)
    draw = ImageDraw.Draw(image, "RGBA")
    width, height = size
    speaker_font = _font(max(20, round(height * 0.035)), True)
    dialogue_font = _font(max(21, round(height * 0.034)))
    speaker_y = round(height * 0.755)
    dialogue_y = round(height * 0.805)
    center_x = width // 2

    draw.line((width * 0.28, speaker_y + 19, width * 0.43, speaker_y + 19), fill=(194, 153, 58, 145), width=2)
    draw.line((width * 0.57, speaker_y + 19, width * 0.72, speaker_y + 19), fill=(194, 153, 58, 145), width=2)
    draw.text(
        (center_x, speaker_y),
        line.speaker,
        font=speaker_font,
        anchor="ma",
        fill=(235, 178, 52, 255),
        stroke_width=2,
        stroke_fill=(54, 42, 29, 235),
    )

    lines = _wrap_text(draw, line.text, dialogue_font, round(width * 0.58))
    line_height = round(height * 0.048)
    for index, text in enumerate(lines):
        draw.text(
            (center_x, dialogue_y + index * line_height),
            text,
            font=dialogue_font,
            anchor="ma",
            fill=(250, 250, 246, 255),
            stroke_width=2,
            stroke_fill=(31, 35, 39, 245),
        )

    draw.polygon(
        [(center_x, height * 0.94), (center_x - 7, height * 0.925), (center_x + 7, height * 0.925)],
        fill=(232, 181, 53, 230),
    )
    draw.text(
        (width - 28, height - 22),
        "Space 下一句  ·  A 自动播放  ·  Esc 退出",
        font=_font(13),
        anchor="rs",
        fill=(248, 248, 244, 175),
        stroke_width=1,
        stroke_fill=(25, 28, 31, 220),
    )
    return image.convert("RGB")


def fixture_regions(size: tuple[int, int]) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    speaker = STANDARD_DIALOGUE_LAYOUT.speaker
    dialogue = STANDARD_DIALOGUE_LAYOUT.dialogue
    return (
        (round(size[0] * speaker.left), round(size[1] * speaker.top),
         round(size[0] * speaker.width), round(size[1] * speaker.height)),
        (round(size[0] * dialogue.left), round(size[1] * dialogue.top),
         round(size[0] * dialogue.width), round(size[1] * dialogue.height)),
    )


class OcrFixtureWindow:
    def __init__(self, image_paths: list[Path] | None = None, autoplay_ms: int = 3500) -> None:
        self.root = tk.Tk()
        self.root.title("Genshin AutoVoice · 真实布局 OCR 验收场景")
        self.root.geometry("1280x720+40+60")
        self.root.minsize(960, 540)
        self.root.configure(bg="#080d16")
        self.index = 0
        self.autoplay_ms = max(1000, autoplay_ms)
        self.autoplay = False
        self.image_paths = image_paths or []
        self.photo: ImageTk.PhotoImage | None = None
        self.stage = tk.Label(self.root, bg="#080d16", borderwidth=0)
        self.stage.pack(fill="both", expand=True)
        self.root.bind("<space>", lambda _event: self.next())
        self.root.bind("<Right>", lambda _event: self.next())
        self.root.bind("<Left>", lambda _event: self.previous())
        self.root.bind("<a>", lambda _event: self.toggle_autoplay())
        self.root.bind("<A>", lambda _event: self.toggle_autoplay())
        self.root.bind("<Escape>", lambda _event: self.root.destroy())
        self.root.bind("<Configure>", self._resize)
        self._resize_after: str | None = None
        self.show()

    @property
    def item_count(self) -> int:
        return len(self.image_paths) if self.image_paths else len(LINES)

    def _source_image(self) -> Image.Image:
        if self.image_paths:
            return Image.open(self.image_paths[self.index]).convert("RGB")
        return render_dialogue_scene(LINES[self.index])

    def show(self) -> None:
        self.root.update_idletasks()
        width = max(1, self.stage.winfo_width())
        height = max(1, self.stage.winfo_height())
        if width <= 2 or height <= 2:
            width, height = 1280, 720
        with self._source_image() as source:
            frame = ImageOps.fit(source, (width, height), Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(frame)
        self.stage.configure(image=self.photo)
        source_name = self.image_paths[self.index].name if self.image_paths else LINES[self.index].speaker
        mode = "自动" if self.autoplay else "手动"
        self.root.title(
            f"Genshin AutoVoice · OCR 验收场景 · {self.index + 1}/{self.item_count} · {source_name} · {mode}"
        )

    def _resize(self, _event) -> None:
        if self._resize_after:
            self.root.after_cancel(self._resize_after)
        self._resize_after = self.root.after(120, self.show)

    def next(self) -> None:
        self.index = (self.index + 1) % self.item_count
        self.show()

    def previous(self) -> None:
        self.index = (self.index - 1) % self.item_count
        self.show()

    def toggle_autoplay(self) -> None:
        self.autoplay = not self.autoplay
        self.show()
        if self.autoplay:
            self.root.after(self.autoplay_ms, self._advance_if_autoplay)

    def _advance_if_autoplay(self) -> None:
        if self.autoplay:
            self.next()
            self.root.after(self.autoplay_ms, self._advance_if_autoplay)

    def run(self) -> None:
        self.root.mainloop()


def _collect_images(directory: str | None) -> list[Path]:
    if not directory:
        return []
    root = Path(directory).expanduser()
    if not root.is_dir():
        raise ValueError(f"截图目录不存在：{root}")
    extensions = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    images = sorted(path for path in root.iterdir() if path.suffix.lower() in extensions)
    if not images:
        raise ValueError(f"目录中没有支持的截图：{root}")
    return images


def run_fixture(image_dir: str | None = None, autoplay_ms: int = 3500) -> None:
    try:
        images = _collect_images(image_dir)
        OcrFixtureWindow(images, autoplay_ms).run()
    except ValueError as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("无法启动验收场景", str(exc))
        root.destroy()
