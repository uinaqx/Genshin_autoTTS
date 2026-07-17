from __future__ import annotations

import tkinter as tk
from tkinter import ttk


LINES = [
    ("派蒙", "旅行者，我们出发吧！前面一定有新的宝藏。"),
    ("嘉明", "路虽远，行则将至；事虽难，做则必成。"),
    ("旁白", "风从山谷吹来，远处的灯火逐渐明亮。"),
]


class OcrFixtureWindow:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Genshin_autoTTS OCR 测试场景")
        self.root.geometry("1120x480+80+160")
        self.root.configure(bg="#171a24")
        self.index = 0
        self.speaker = tk.StringVar()
        self.dialogue = tk.StringVar()
        self._build()
        self._show_line()

    def _build(self) -> None:
        ttk.Label(
            self.root,
            text="屏幕 OCR 手动验收场景 · 请分别框选下方角色名与正文",
            font=("Microsoft YaHei UI", 14),
        ).pack(fill="x", padx=24, pady=(18, 4))
        ttk.Button(self.root, text="切换下一句", command=self._next).pack(anchor="e", padx=28)

        stage = tk.Frame(self.root, bg="#171a24", highlightbackground="#50586d", highlightthickness=1)
        stage.pack(fill="both", expand=True, padx=24, pady=16)
        tk.Label(
            stage,
            textvariable=self.speaker,
            bg="#171a24",
            fg="#f7d77d",
            font=("Microsoft YaHei UI", 27, "bold"),
        ).pack(pady=(72, 20))
        tk.Label(
            stage,
            textvariable=self.dialogue,
            bg="#171a24",
            fg="#ffffff",
            font=("Microsoft YaHei UI", 25),
            wraplength=1000,
        ).pack(padx=32)

    def _show_line(self) -> None:
        speaker, dialogue = LINES[self.index]
        self.speaker.set(speaker)
        self.dialogue.set(dialogue)

    def _next(self) -> None:
        self.index = (self.index + 1) % len(LINES)
        self._show_line()

    def run(self) -> None:
        self.root.mainloop()


def run_fixture() -> None:
    OcrFixtureWindow().run()
