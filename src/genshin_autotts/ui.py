from __future__ import annotations

import threading
import tkinter as tk
from ctypes import windll
from datetime import datetime, timezone
from tkinter import messagebox, ttk

from .cache import AudioCache
from .config import app_home, load_config, save_config
from .models import DialogueEvent, Region
from .runtime import build_controller, build_voice_pipeline


class RegionSelector:
    def __init__(self, root: tk.Tk, title: str) -> None:
        self.result: Region | None = None
        self.start_x = 0
        self.start_y = 0
        self.rect = None
        self.window = tk.Toplevel(root)
        self.window.title(title)
        self.window.attributes("-fullscreen", True)
        self.window.attributes("-topmost", True)
        self.window.attributes("-alpha", 0.35)
        self.window.configure(bg="black")
        self.canvas = tk.Canvas(self.window, cursor="crosshair", bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_text(
            20,
            20,
            anchor="nw",
            text=f"{title}：按住鼠标左键拖出区域；Esc 取消",
            fill="white",
            font=("Microsoft YaHei UI", 18, "bold"),
        )
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.window.bind("<Escape>", lambda _event: self.window.destroy())
        self.window.grab_set()
        self.window.wait_window()

    def _press(self, event) -> None:
        self.start_x, self.start_y = event.x, event.y
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, event.x, event.y, outline="#00ff88", width=3
        )

    def _drag(self, event) -> None:
        if self.rect:
            self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)

    def _release(self, event) -> None:
        left, right = sorted((self.start_x, event.x))
        top, bottom = sorted((self.start_y, event.y))
        if right - left >= 10 and bottom - top >= 10:
            self.result = Region(left, top, right - left, bottom - top)
        self.window.destroy()


class MainWindow:
    def __init__(self) -> None:
        self.config = load_config()
        self.root = tk.Tk()
        self.root.title("Genshin_autoTTS")
        self.root.geometry("760x580")
        self.root.minsize(680, 520)
        self.controller = None
        self.status_var = tk.StringVar(value="就绪：请设置角色名与字幕区域")
        self.cache_var = tk.StringVar(value=str(self.config.cache_max_mb))
        self.test_speaker = tk.StringVar(value="派蒙")
        self.test_text = tk.StringVar(value="旅行者，我们出发吧！")
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self) -> None:
        style = ttk.Style(self.root)
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 18, "bold"))
        style.configure("Hint.TLabel", foreground="#555555")
        container = ttk.Frame(self.root, padding=18)
        container.pack(fill="both", expand=True)

        ttk.Label(container, text="Genshin_autoTTS", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            container,
            text="外部屏幕识别 · 固定角色音色 · 高自然度神经人声 · 受限缓存",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(2, 14))

        regions = ttk.LabelFrame(container, text="1. 识别区域", padding=10)
        regions.pack(fill="x")
        ttk.Button(regions, text="框选角色名区域", command=self._select_speaker).grid(row=0, column=0, padx=4, pady=4)
        ttk.Button(regions, text="框选字幕区域", command=self._select_dialogue).grid(row=0, column=1, padx=4, pady=4)
        self.region_label = ttk.Label(regions, text=self._region_summary())
        self.region_label.grid(row=1, column=0, columnspan=3, sticky="w", padx=4)

        settings = ttk.LabelFrame(container, text="2. 语音与存储", padding=10)
        settings.pack(fill="x", pady=10)
        ttk.Label(settings, text="语音：").grid(row=0, column=0, sticky="e")
        ttk.Label(settings, text="高自然度神经人声（联网，失败不降级）").grid(
            row=0, column=1, sticky="w", padx=4
        )
        ttk.Label(settings, text="缓存上限 MB：").grid(row=0, column=2, sticky="e", padx=(20, 0))
        ttk.Entry(settings, textvariable=self.cache_var, width=9).grid(row=0, column=3, sticky="w", padx=4)
        ttk.Button(settings, text="保存设置", command=self._save_settings).grid(row=0, column=4, padx=8)
        ttk.Button(settings, text="清空语音缓存", command=self._clear_cache).grid(row=0, column=5, padx=4)

        controls = ttk.LabelFrame(container, text="3. 运行", padding=10)
        controls.pack(fill="x")
        self.start_button = ttk.Button(controls, text="开始自动配音", command=self._start)
        self.start_button.grid(row=0, column=0, padx=4, pady=4)
        ttk.Button(controls, text="停止", command=self._stop).grid(row=0, column=1, padx=4, pady=4)
        ttk.Label(controls, textvariable=self.status_var, wraplength=520).grid(row=1, column=0, columnspan=4, sticky="w", padx=4)

        demo = ttk.LabelFrame(container, text="4. 全流程测试", padding=10)
        demo.pack(fill="x", pady=10)
        ttk.Label(demo, text="角色：").grid(row=0, column=0)
        ttk.Entry(demo, textvariable=self.test_speaker, width=14).grid(row=0, column=1, padx=4)
        ttk.Label(demo, text="台词：").grid(row=0, column=2)
        ttk.Entry(demo, textvariable=self.test_text, width=42).grid(row=0, column=3, padx=4)
        ttk.Button(demo, text="生成并播放", command=self._test_pipeline).grid(row=0, column=4, padx=4)

        log_frame = ttk.LabelFrame(container, text="运行日志", padding=6)
        log_frame.pack(fill="both", expand=True)
        self.log = tk.Text(log_frame, height=10, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True)

    def _region_summary(self) -> str:
        return f"角色名：{self.config.speaker_region or '未设置'} ｜ 字幕：{self.config.dialogue_region or '未设置'}"

    def _select_speaker(self) -> None:
        selector = RegionSelector(self.root, "框选角色名")
        if selector.result:
            self.config.speaker_region = selector.result
            save_config(self.config)
            self.region_label.configure(text=self._region_summary())

    def _select_dialogue(self) -> None:
        selector = RegionSelector(self.root, "框选字幕")
        if selector.result:
            self.config.dialogue_region = selector.result
            save_config(self.config)
            self.region_label.configure(text=self._region_summary())

    def _save_settings(self) -> bool:
        try:
            self.config.tts_provider = "edge"
            self.config.cache_max_mb = int(self.cache_var.get())
            save_config(self.config)
            self._status("设置已保存")
            return True
        except Exception as exc:
            messagebox.showerror("设置错误", str(exc))
            return False

    def _start(self) -> None:
        try:
            if not self._save_settings():
                return
            if self.controller:
                self.controller.stop()
            self.controller = build_controller(self.config, self._status)
            self.controller.start()
        except Exception as exc:
            messagebox.showerror("无法启动", str(exc))

    def _stop(self) -> None:
        if self.controller:
            self.controller.stop()
            self.controller = None

    def _test_pipeline(self) -> None:
        speaker = self.test_speaker.get().strip() or "旁白"
        text = self.test_text.get().strip()
        if not text:
            return
        if not self._save_settings():
            return

        def work() -> None:
            try:
                pipeline = build_voice_pipeline(self.config)
                event = DialogueEvent(speaker, text, datetime.now(timezone.utc))
                artifact = pipeline.process(event)
                self._status(f"测试成功：{artifact.codec}｜{'缓存命中' if artifact.from_cache else artifact.provider}")
            except Exception as exc:
                self._status(f"测试失败：{exc}")

        threading.Thread(target=work, daemon=True).start()

    def _clear_cache(self) -> None:
        cache = AudioCache(app_home() / "cache", self.config.cache_max_mb * 1024 * 1024)
        cache.clear()
        self._status("语音缓存已清空")

    def _status(self, message: str) -> None:
        def update() -> None:
            self.status_var.set(message)
            self.log.configure(state="normal")
            self.log.insert("end", message + "\n")
            line_count = int(self.log.index("end-1c").split(".")[0])
            if line_count > 500:
                self.log.delete("1.0", f"{line_count - 500}.0")
            self.log.see("end")
            self.log.configure(state="disabled")

        self.root.after(0, update)

    def _close(self) -> None:
        self._stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def run_gui() -> None:
    try:
        windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass
    MainWindow().run()
