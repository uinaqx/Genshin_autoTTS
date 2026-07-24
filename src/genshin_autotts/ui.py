from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from ctypes import windll
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image

from . import __version__
from .cache import AudioCache
from .capture import MssScreenCapture
from .config import app_home, load_config, save_config
from .credentials import CredentialStore
from .models import DialogueEvent, Region
from .ocr import RapidOcrEngine, STANDARD_DIALOGUE_LAYOUT, recognize_dialogue_frame
from .runtime import build_controller, build_voice_pipeline


COLORS = {
    "background": "#09111F",
    "sidebar": "#0D1728",
    "surface": "#111C2E",
    "card": "#152238",
    "card_alt": "#101B2D",
    "border": "#263752",
    "text": "#EEF4FF",
    "muted": "#91A3BD",
    "subtle": "#647894",
    "accent": "#5EEAD4",
    "accent_dark": "#123B3C",
    "blue": "#7DD3FC",
    "gold": "#F6C85F",
    "success": "#34D399",
    "danger": "#FB7185",
    "warning": "#FBBF24",
}

PROVIDER_LABELS = {
    "volcengine": "火山引擎",
    "aliyun": "阿里云",
    "recorded": "真人录音包（兼容）",
    "edge": "Microsoft Edge（实验）",
}
PROVIDER_KEYS = {label: key for key, label in PROVIDER_LABELS.items()}


def format_region(region: Region | None) -> str:
    if region is None:
        return "尚未设置"
    return f"X {region.left}  ·  Y {region.top}  ·  {region.width} × {region.height}"


def voice_pack_summary(manifest_value: str) -> str:
    if not manifest_value.strip():
        return "内置诊断包  ·  1 条授权真人录音"
    path = Path(manifest_value).expanduser()
    if not path.is_file():
        return "清单文件不存在"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        count = len(payload.get("entries", []))
        pack_id = payload.get("pack_id") or path.stem
        version = payload.get("pack_version") or "未标版本"
        return f"{pack_id}  ·  {version}  ·  {count} 条录音"
    except (OSError, ValueError, TypeError):
        return "清单格式无法读取"


def fixture_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--fixture"]
    return [sys.executable, "-m", "genshin_autotts", "fixture"]


class RegionSelector:
    def __init__(self, root: tk.Tk, title: str) -> None:
        self.result: Region | None = None
        self.start_x = 0
        self.start_y = 0
        self.rect: int | None = None
        self.size_text: int | None = None
        self.window = tk.Toplevel(root)
        self.window.title(title)
        self.window.attributes("-fullscreen", True)
        self.window.attributes("-topmost", True)
        self.window.attributes("-alpha", 0.42)
        self.window.configure(bg="black")
        self.canvas = tk.Canvas(
            self.window,
            cursor="crosshair",
            bg="#06101C",
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_rectangle(24, 24, 590, 104, fill="#0D1728", outline="#5EEAD4", width=1)
        self.canvas.create_text(
            48,
            47,
            anchor="nw",
            text=title,
            fill="#EEF4FF",
            font=("Microsoft YaHei UI", 18, "bold"),
        )
        self.canvas.create_text(
            48,
            78,
            anchor="nw",
            text="按住鼠标左键拖出范围  ·  Esc 取消",
            fill="#A8B7CC",
            font=("Microsoft YaHei UI", 11),
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
        if self.size_text:
            self.canvas.delete(self.size_text)
        self.rect = self.canvas.create_rectangle(
            self.start_x,
            self.start_y,
            event.x,
            event.y,
            outline=COLORS["accent"],
            fill="#123B3C",
            stipple="gray50",
            width=3,
        )

    def _drag(self, event) -> None:
        if not self.rect:
            return
        self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)
        width = abs(event.x - self.start_x)
        height = abs(event.y - self.start_y)
        x = min(self.start_x, event.x) + 10
        y = min(self.start_y, event.y) + 10
        if self.size_text:
            self.canvas.delete(self.size_text)
        self.size_text = self.canvas.create_text(
            x,
            y,
            anchor="nw",
            text=f"{width} × {height}",
            fill="white",
            font=("Microsoft YaHei UI", 12, "bold"),
        )

    def _release(self, event) -> None:
        left, right = sorted((self.start_x, event.x))
        top, bottom = sorted((self.start_y, event.y))
        if right - left >= 10 and bottom - top >= 10:
            self.result = Region(left, top, right - left, bottom - top)
        self.window.destroy()


class MainWindow:
    def __init__(self) -> None:
        self.config = load_config()
        self.credential_store = CredentialStore(app_home() / "credentials.dat")
        self.controller = None
        self.root = tk.Tk()
        self.root.title(f"Genshin AutoVoice {__version__}")
        self.root.geometry("1180x760")
        self.root.minsize(1040, 700)
        self.root.configure(bg=COLORS["background"])

        self.cache_var = tk.StringVar(value=str(self.config.cache_max_mb))
        self.provider_var = tk.StringVar(
            value=PROVIDER_LABELS.get(self.config.tts_provider, PROVIDER_LABELS["volcengine"])
        )
        self.voice_pack_var = tk.StringVar(value=self.config.voice_pack_manifest or "")
        self.voice_pack_info_var = tk.StringVar(value="")
        self.speaker_region_var = tk.StringVar(value=format_region(self.config.speaker_region))
        self.dialogue_region_var = tk.StringVar(value=format_region(self.config.dialogue_region))
        self.status_var = tk.StringVar(value="等待配置")
        self.status_detail_var = tk.StringVar(value="设置识别区域后即可开始自动配音")
        self.test_speaker = tk.StringVar(value="派蒙")
        self.test_text = tk.StringVar(value="我们出发吧。")
        self._build_styles()
        self._build()
        self._refresh_region_state()
        self._refresh_provider_info()
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _build_styles(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            "Accent.TButton",
            font=("Microsoft YaHei UI", 10, "bold"),
            foreground="#06211E",
            background=COLORS["accent"],
            bordercolor=COLORS["accent"],
            padding=(18, 10),
        )
        style.map(
            "Accent.TButton",
            background=[("pressed", "#2DD4BF"), ("active", "#99F6E4"), ("disabled", "#274B50")],
            foreground=[("disabled", "#718A91")],
        )
        style.configure(
            "Secondary.TButton",
            font=("Microsoft YaHei UI", 10),
            foreground=COLORS["text"],
            background=COLORS["card_alt"],
            bordercolor=COLORS["border"],
            padding=(14, 9),
        )
        style.map(
            "Secondary.TButton",
            background=[("pressed", "#172841"), ("active", "#1B2C46")],
            bordercolor=[("active", COLORS["blue"])],
        )
        style.configure(
            "Danger.TButton",
            font=("Microsoft YaHei UI", 10, "bold"),
            foreground="#FFEFF2",
            background="#3C1C2A",
            bordercolor="#6E2D43",
            padding=(16, 10),
        )
        style.map("Danger.TButton", background=[("active", "#592238"), ("disabled", "#241825")])
        style.configure(
            "Dark.TEntry",
            fieldbackground="#0C1728",
            foreground=COLORS["text"],
            insertcolor=COLORS["accent"],
            bordercolor=COLORS["border"],
            lightcolor=COLORS["border"],
            darkcolor=COLORS["border"],
            padding=(9, 8),
        )
        style.map("Dark.TEntry", bordercolor=[("focus", COLORS["accent"])])
        style.configure(
            "Dark.TCombobox",
            fieldbackground="#0C1728",
            foreground=COLORS["text"],
            background=COLORS["card_alt"],
            bordercolor=COLORS["border"],
            arrowcolor=COLORS["accent"],
            padding=(9, 8),
        )

    def _build(self) -> None:
        shell = tk.Frame(self.root, bg=COLORS["background"])
        shell.pack(fill="both", expand=True)
        shell.grid_rowconfigure(0, weight=1)
        shell.grid_columnconfigure(1, weight=1)

        sidebar = tk.Frame(shell, bg=COLORS["sidebar"], width=240)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        self._build_sidebar(sidebar)

        main = tk.Frame(shell, bg=COLORS["background"], padx=26, pady=18)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(3, weight=1)
        self._build_header(main)
        self._build_setup_grid(main)
        self._build_control_card(main)
        self._build_log_card(main)

    def _build_sidebar(self, parent: tk.Frame) -> None:
        brand = tk.Frame(parent, bg=COLORS["sidebar"], padx=22, pady=24)
        brand.pack(fill="x")
        mark = tk.Canvas(brand, width=38, height=38, bg=COLORS["sidebar"], highlightthickness=0)
        mark.grid(row=0, column=0, rowspan=2, padx=(0, 12))
        mark.create_oval(2, 2, 36, 36, fill=COLORS["accent_dark"], outline=COLORS["accent"], width=1)
        mark.create_text(19, 19, text="◆", fill=COLORS["accent"], font=("Segoe UI Symbol", 14, "bold"))
        tk.Label(
            brand,
            text="Genshin AutoVoice",
            bg=COLORS["sidebar"],
            fg=COLORS["text"],
            font=("Microsoft YaHei UI", 13, "bold"),
        ).grid(row=0, column=1, sticky="w")
        tk.Label(
            brand,
            text=f"桌面剧情语音伴侣  ·  v{__version__}",
            bg=COLORS["sidebar"],
            fg=COLORS["muted"],
            font=("Microsoft YaHei UI", 9),
        ).grid(row=1, column=1, sticky="w", pady=(2, 0))

        divider = tk.Frame(parent, bg=COLORS["border"], height=1)
        divider.pack(fill="x", padx=20, pady=(0, 22))
        tk.Label(
            parent,
            text="启动检查",
            bg=COLORS["sidebar"],
            fg=COLORS["subtle"],
            font=("Microsoft YaHei UI", 9, "bold"),
        ).pack(anchor="w", padx=24, pady=(0, 10))
        self.sidebar_region_state = self._sidebar_step(parent, "1", "识别区域", "等待设置")
        self.sidebar_pack_state = self._sidebar_step(parent, "2", "语音服务", "等待配置")
        self.sidebar_run_state = self._sidebar_step(parent, "3", "自动配音", "尚未运行")

        privacy = tk.Frame(parent, bg=COLORS["card_alt"], padx=16, pady=14)
        privacy.pack(side="bottom", fill="x", padx=18, pady=18)
        tk.Label(
            privacy,
            text="●  本地识别 · 云端合成",
            bg=COLORS["card_alt"],
            fg=COLORS["success"],
            font=("Microsoft YaHei UI", 9, "bold"),
        ).pack(anchor="w")
        tk.Label(
            privacy,
            text="截图、OCR 与角色匹配在本机完成；\n仅将稳定台词和音色 ID 发给语音服务。",
            bg=COLORS["card_alt"],
            fg=COLORS["muted"],
            justify="left",
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", pady=(6, 0))

    def _sidebar_step(self, parent: tk.Frame, number: str, title: str, state: str) -> tk.Label:
        row = tk.Frame(parent, bg=COLORS["sidebar"], padx=22, pady=9)
        row.pack(fill="x")
        badge = tk.Label(
            row,
            text=number,
            width=2,
            height=1,
            bg=COLORS["card"],
            fg=COLORS["blue"],
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        badge.grid(row=0, column=0, rowspan=2, padx=(0, 12), sticky="n")
        tk.Label(
            row,
            text=title,
            bg=COLORS["sidebar"],
            fg=COLORS["text"],
            font=("Microsoft YaHei UI", 10, "bold"),
        ).grid(row=0, column=1, sticky="w")
        state_label = tk.Label(
            row,
            text=state,
            bg=COLORS["sidebar"],
            fg=COLORS["subtle"],
            font=("Microsoft YaHei UI", 9),
        )
        state_label.grid(row=1, column=1, sticky="w", pady=(2, 0))
        return state_label

    def _build_header(self, parent: tk.Frame) -> None:
        header = tk.Frame(parent, bg=COLORS["background"])
        header.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        header.grid_columnconfigure(0, weight=1)
        tk.Label(
            header,
            text="运行中心",
            bg=COLORS["background"],
            fg=COLORS["text"],
            font=("Microsoft YaHei UI", 22, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            header,
            text="本地识别角色与字幕，匹配固定音色后请求云端生成语音",
            bg=COLORS["background"],
            fg=COLORS["muted"],
            font=("Microsoft YaHei UI", 10),
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.status_pill = tk.Label(
            header,
            text="●  等待配置",
            bg="#1D2A3F",
            fg=COLORS["muted"],
            padx=15,
            pady=8,
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        self.status_pill.grid(row=0, column=1, rowspan=2, sticky="e")

    def _card(self, parent: tk.Frame, title: str, subtitle: str) -> tuple[tk.Frame, tk.Frame]:
        card = tk.Frame(
            parent,
            bg=COLORS["card"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=18,
            pady=16,
        )
        tk.Label(
            card,
            text=title,
            bg=COLORS["card"],
            fg=COLORS["text"],
            font=("Microsoft YaHei UI", 12, "bold"),
        ).pack(anchor="w")
        tk.Label(
            card,
            text=subtitle,
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", pady=(3, 13))
        body = tk.Frame(card, bg=COLORS["card"])
        body.pack(fill="both", expand=True)
        return card, body

    def _build_setup_grid(self, parent: tk.Frame) -> None:
        grid = tk.Frame(parent, bg=COLORS["background"])
        grid.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        grid.grid_columnconfigure(0, weight=1, uniform="setup")
        grid.grid_columnconfigure(1, weight=1, uniform="setup")

        region_card, region = self._card(grid, "屏幕识别区域", "框选范围越紧，复杂背景下的识别越稳定")
        region_card.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        self._region_row(region, 0, "角色名", self.speaker_region_var, self._select_speaker)
        self._region_row(region, 1, "字幕正文", self.dialogue_region_var, self._select_dialogue)
        actions = tk.Frame(region, bg=COLORS["card"])
        actions.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        ttk.Button(
            actions,
            text="套用全屏 16:9 预设",
            command=self._apply_fullscreen_preset,
            style="Secondary.TButton",
        ).pack(side="left")
        ttk.Button(
            actions,
            text="截屏识别测试",
            command=self._diagnose_regions,
            style="Secondary.TButton",
        ).pack(side="left", padx=(8, 0))

        pack_card, pack = self._card(
            grid,
            "云端语音服务",
            "选择开放平台；同一角色会复用本地保存的固定音色",
        )
        pack_card.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        mode = tk.Frame(pack, bg=COLORS["card_alt"], padx=11, pady=8)
        mode.pack(fill="x")
        provider_box = ttk.Combobox(
            mode,
            textvariable=self.provider_var,
            values=list(PROVIDER_LABELS.values()),
            state="readonly",
            width=22,
            style="Dark.TCombobox",
        )
        provider_box.pack(side="left", fill="x", expand=True)
        provider_box.bind("<<ComboboxSelected>>", lambda _event: self._refresh_provider_info())
        ttk.Button(
            mode,
            text="配置 API",
            command=self._open_cloud_settings,
            style="Secondary.TButton",
        ).pack(side="right", padx=(8, 0))
        manifest_row = tk.Frame(pack, bg=COLORS["card"])
        manifest_row.pack(fill="x", pady=(10, 4))
        tk.Label(
            manifest_row,
            text="兼容录音包",
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Microsoft YaHei UI", 9),
        ).pack(side="left", padx=(0, 7))
        entry = ttk.Entry(manifest_row, textvariable=self.voice_pack_var, style="Dark.TEntry")
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<FocusOut>", lambda _event: self._refresh_provider_info())
        ttk.Button(
            manifest_row,
            text="选择清单",
            command=self._select_voice_pack,
            style="Secondary.TButton",
        ).pack(side="left", padx=(8, 0))
        tk.Label(
            pack,
            textvariable=self.voice_pack_info_var,
            bg=COLORS["card"],
            fg=COLORS["gold"],
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w")
        cache_row = tk.Frame(pack, bg=COLORS["card"])
        cache_row.pack(fill="x", pady=(10, 0))
        tk.Label(
            cache_row,
            text="缓存上限",
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=("Microsoft YaHei UI", 9),
        ).pack(side="left")
        ttk.Entry(cache_row, textvariable=self.cache_var, width=7, style="Dark.TEntry").pack(side="left", padx=(8, 5))
        tk.Label(cache_row, text="MB", bg=COLORS["card"], fg=COLORS["muted"]).pack(side="left")
        ttk.Button(cache_row, text="清空缓存", command=self._clear_cache, style="Secondary.TButton").pack(side="right")
        ttk.Button(cache_row, text="保存设置", command=self._save_settings, style="Secondary.TButton").pack(side="right", padx=(0, 8))

    def _region_row(
        self,
        parent: tk.Frame,
        row: int,
        label: str,
        value: tk.StringVar,
        command,
    ) -> None:
        parent.grid_columnconfigure(1, weight=1)
        tk.Label(
            parent,
            text=label,
            bg=COLORS["card"],
            fg=COLORS["muted"],
            width=9,
            anchor="w",
            font=("Microsoft YaHei UI", 9),
        ).grid(row=row, column=0, sticky="w", pady=4)
        tk.Label(
            parent,
            textvariable=value,
            bg=COLORS["card_alt"],
            fg=COLORS["text"],
            padx=10,
            pady=8,
            anchor="w",
            font=("Cascadia Mono", 9),
        ).grid(row=row, column=1, sticky="ew", padx=(4, 8), pady=4)
        ttk.Button(parent, text="框选", command=command, style="Secondary.TButton").grid(
            row=row, column=2, sticky="e", pady=4
        )

    def _build_control_card(self, parent: tk.Frame) -> None:
        card = tk.Frame(
            parent,
            bg=COLORS["surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=18,
            pady=14,
        )
        card.grid(row=2, column=0, sticky="ew", pady=(0, 14))
        card.grid_columnconfigure(2, weight=1)
        self.start_button = ttk.Button(card, text="▶  开始自动配音", command=self._start, style="Accent.TButton")
        self.start_button.grid(row=0, column=0, rowspan=2, sticky="nsw")
        self.stop_button = ttk.Button(card, text="■  停止", command=self._stop, style="Danger.TButton")
        self.stop_button.grid(row=0, column=1, rowspan=2, sticky="nsw", padx=(9, 18))
        self.stop_button.state(["disabled"])
        tk.Label(
            card,
            textvariable=self.status_var,
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=("Microsoft YaHei UI", 10, "bold"),
        ).grid(row=0, column=2, sticky="sw")
        tk.Label(
            card,
            textvariable=self.status_detail_var,
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=("Microsoft YaHei UI", 9),
        ).grid(row=1, column=2, sticky="nw", pady=(3, 0))

        test = tk.Frame(card, bg=COLORS["surface"])
        test.grid(row=0, column=3, rowspan=2, sticky="e")
        ttk.Entry(test, textvariable=self.test_speaker, width=11, style="Dark.TEntry").pack(side="left")
        ttk.Entry(test, textvariable=self.test_text, width=23, style="Dark.TEntry").pack(side="left", padx=7)
        ttk.Button(
            test,
            text="测试语音",
            command=self._test_pipeline,
            style="Secondary.TButton",
        ).pack(side="left")

    def _build_log_card(self, parent: tk.Frame) -> None:
        card, body = self._card(
            parent,
            "运行与诊断日志",
            "OCR、音色匹配、云端生成、缓存和播放状态会按时间记录",
        )
        card.grid(row=3, column=0, sticky="nsew")
        toolbar = tk.Frame(body, bg=COLORS["card"])
        toolbar.pack(fill="x", pady=(0, 9))
        ttk.Button(
            toolbar,
            text="导入真实截图诊断",
            command=self._diagnose_files,
            style="Secondary.TButton",
        ).pack(side="left")
        ttk.Button(
            toolbar,
            text="打开模拟剧情场景",
            command=self._open_fixture,
            style="Secondary.TButton",
        ).pack(side="left", padx=(8, 0))
        ttk.Button(toolbar, text="清空日志", command=self._clear_log, style="Secondary.TButton").pack(side="right")
        log_shell = tk.Frame(body, bg="#091422", highlightbackground=COLORS["border"], highlightthickness=1)
        log_shell.pack(fill="both", expand=True)
        self.log = tk.Text(
            log_shell,
            height=8,
            state="disabled",
            wrap="word",
            bg="#091422",
            fg="#C8D6E9",
            insertbackground=COLORS["accent"],
            selectbackground="#24405F",
            relief="flat",
            borderwidth=0,
            padx=12,
            pady=10,
            font=("Cascadia Mono", 9),
        )
        scrollbar = ttk.Scrollbar(log_shell, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scrollbar.set)
        self.log.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._append_log(
            "系统",
            "界面已就绪；截图与 OCR 在本机处理，稳定台词按需发送给所选云端语音服务。",
        )

    def _refresh_region_state(self) -> None:
        self.speaker_region_var.set(format_region(self.config.speaker_region))
        self.dialogue_region_var.set(format_region(self.config.dialogue_region))
        ready = self.config.speaker_region is not None and self.config.dialogue_region is not None
        self.sidebar_region_state.configure(
            text="两个区域已就绪" if ready else "等待设置",
            fg=COLORS["success"] if ready else COLORS["subtle"],
        )
        if not (self.controller and self.controller.running):
            self.status_var.set("准备就绪" if ready else "等待配置")
            self.status_detail_var.set(
                "可以开始自动配音，建议先运行截屏识别测试"
                if ready
                else "设置角色名和字幕区域后即可开始"
            )
            self.status_pill.configure(
                text="●  准备就绪" if ready else "●  等待配置",
                bg="#12352F" if ready else "#1D2A3F",
                fg=COLORS["success"] if ready else COLORS["muted"],
            )

    def _refresh_provider_info(self) -> None:
        provider = PROVIDER_KEYS.get(self.provider_var.get(), "volcengine")
        if provider == "recorded":
            summary = voice_pack_summary(self.voice_pack_var.get())
            healthy = summary not in {"清单文件不存在", "清单格式无法读取"}
        elif provider == "edge":
            summary = "无需 API 凭据 · 文本会发送至 Microsoft 在线语音服务"
            healthy = True
        else:
            try:
                healthy = self.credential_store.has_provider(provider)
                summary = (
                    "API 凭据已使用 Windows DPAPI 加密保存"
                    if healthy
                    else "尚未配置 API 凭据"
                )
            except Exception as exc:
                healthy = False
                summary = f"凭据读取失败：{exc}"
        self.voice_pack_info_var.set(summary)
        self.sidebar_pack_state.configure(
            text=f"{PROVIDER_LABELS[provider]}已就绪" if healthy else summary,
            fg=COLORS["success"] if healthy else COLORS["danger"],
        )

    def _open_cloud_settings(self) -> None:
        provider = PROVIDER_KEYS.get(self.provider_var.get(), "volcengine")
        if provider == "recorded":
            messagebox.showinfo(
                "真人录音兼容模式",
                "此模式仍使用下方 manifest.json 录音清单，不需要 API 凭据。",
                parent=self.root,
            )
            return
        if provider == "edge":
            messagebox.showinfo(
                "Edge 实验模式",
                "此模式不需要单独申请 API，但不属于本项目的主要云平台接入路径。",
                parent=self.root,
            )
            return

        try:
            current = self.credential_store.get_provider(provider)
        except Exception as exc:
            messagebox.showerror("无法读取凭据", str(exc), parent=self.root)
            return

        window = tk.Toplevel(self.root)
        window.title(f"配置 {PROVIDER_LABELS[provider]} API")
        window.geometry("520x330")
        window.resizable(False, False)
        window.transient(self.root)
        window.grab_set()
        window.configure(bg=COLORS["background"])

        shell = tk.Frame(window, bg=COLORS["background"], padx=24, pady=22)
        shell.pack(fill="both", expand=True)
        tk.Label(
            shell,
            text=f"{PROVIDER_LABELS[provider]} API 凭据",
            bg=COLORS["background"],
            fg=COLORS["text"],
            font=("Microsoft YaHei UI", 16, "bold"),
        ).pack(anchor="w")
        tk.Label(
            shell,
            text="凭据仅在当前 Windows 用户下加密保存，不会写入 config.json。",
            bg=COLORS["background"],
            fg=COLORS["muted"],
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", pady=(4, 16))

        definitions = (
            [("App ID", "app_id", False), ("Access Token", "access_token", True)]
            if provider == "volcengine"
            else [("AppKey", "app_key", False), ("Access Token", "access_token", True)]
        )
        variables: dict[str, tk.StringVar] = {}
        form = tk.Frame(shell, bg=COLORS["background"])
        form.pack(fill="x")
        form.grid_columnconfigure(1, weight=1)
        for row, (label, key, secret) in enumerate(definitions):
            tk.Label(
                form,
                text=label,
                bg=COLORS["background"],
                fg=COLORS["muted"],
                width=14,
                anchor="w",
                font=("Microsoft YaHei UI", 10),
            ).grid(row=row, column=0, sticky="w", pady=6)
            variable = tk.StringVar(value=current.get(key, ""))
            variables[key] = variable
            ttk.Entry(
                form,
                textvariable=variable,
                show="●" if secret else "",
                style="Dark.TEntry",
            ).grid(row=row, column=1, sticky="ew", pady=6)

        hint = (
            "火山引擎：在豆包语音控制台创建应用，并取得 APP ID 与 Access Token。"
            if provider == "volcengine"
            else "阿里云：在智能语音交互控制台创建项目，并取得 AppKey 与 Access Token。"
        )
        tk.Label(
            shell,
            text=hint,
            wraplength=465,
            justify="left",
            bg=COLORS["background"],
            fg=COLORS["gold"],
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", pady=(12, 0))

        actions = tk.Frame(shell, bg=COLORS["background"])
        actions.pack(side="bottom", fill="x")

        def save_credentials() -> None:
            try:
                self.credential_store.save_provider(
                    provider,
                    {key: variable.get() for key, variable in variables.items()},
                )
                self.config.tts_provider = provider
                save_config(self.config)
                self._refresh_provider_info()
                window.destroy()
                self._status(f"{PROVIDER_LABELS[provider]} API 凭据已安全保存")
            except Exception as exc:
                messagebox.showerror("保存失败", str(exc), parent=window)

        ttk.Button(
            actions,
            text="取消",
            command=window.destroy,
            style="Secondary.TButton",
        ).pack(side="right")
        ttk.Button(
            actions,
            text="加密保存",
            command=save_credentials,
            style="Accent.TButton",
        ).pack(side="right", padx=(0, 8))

    def _select_speaker(self) -> None:
        selector = RegionSelector(self.root, "框选角色名区域")
        if selector.result:
            self.config.speaker_region = selector.result
            save_config(self.config)
            self._refresh_region_state()
            self._status("角色名区域已更新")

    def _select_dialogue(self) -> None:
        selector = RegionSelector(self.root, "框选字幕正文区域")
        if selector.result:
            self.config.dialogue_region = selector.result
            save_config(self.config)
            self._refresh_region_state()
            self._status("字幕区域已更新")

    def _apply_fullscreen_preset(self) -> None:
        width = self.root.winfo_screenwidth()
        height = self.root.winfo_screenheight()
        speaker = STANDARD_DIALOGUE_LAYOUT.speaker
        dialogue = STANDARD_DIALOGUE_LAYOUT.dialogue
        self.config.speaker_region = Region(
            round(width * speaker.left),
            round(height * speaker.top),
            round(width * speaker.width),
            round(height * speaker.height),
        )
        self.config.dialogue_region = Region(
            round(width * dialogue.left),
            round(height * dialogue.top),
            round(width * dialogue.width),
            round(height * dialogue.height),
        )
        save_config(self.config)
        self._refresh_region_state()
        self._status(f"已套用 {width}×{height} 全屏标准对话预设")

    def _save_settings(self, show_status: bool = True) -> bool:
        try:
            self.config.tts_provider = PROVIDER_KEYS.get(
                self.provider_var.get(),
                "volcengine",
            )
            self.config.voice_pack_manifest = self.voice_pack_var.get().strip() or None
            self.config.cache_max_mb = int(self.cache_var.get())
            save_config(self.config)
            self._refresh_provider_info()
            if show_status:
                self._status("设置已保存")
            return True
        except Exception as exc:
            messagebox.showerror("设置错误", str(exc), parent=self.root)
            return False

    def _select_voice_pack(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.root,
            title="选择真人录音包清单",
            filetypes=[("JSON 清单", "*.json"), ("所有文件", "*.*")],
        )
        if selected:
            self.voice_pack_var.set(selected)
            self._refresh_provider_info()

    def _start(self) -> None:
        try:
            if not self._save_settings(show_status=False):
                return
            if self.controller:
                self.controller.stop()
            self.controller = build_controller(self.config, self._status)
            self.controller.start()
            self.start_button.state(["disabled"])
            self.stop_button.state(["!disabled"])
            self.sidebar_run_state.configure(text="正在监听屏幕", fg=COLORS["success"])
            self.status_pill.configure(text="●  运行中", bg="#12352F", fg=COLORS["success"])
            self.status_var.set("正在监听剧情字幕")
            self.status_detail_var.set("识别稳定后会匹配固定音色、请求云端生成并自动播放")
        except Exception as exc:
            messagebox.showerror("无法启动", str(exc), parent=self.root)

    def _stop(self) -> None:
        if self.controller:
            self.controller.stop()
            self.controller = None
        self.start_button.state(["!disabled"])
        self.stop_button.state(["disabled"])
        self.sidebar_run_state.configure(text="尚未运行", fg=COLORS["subtle"])
        self._refresh_region_state()

    def _test_pipeline(self) -> None:
        speaker = self.test_speaker.get().strip() or "旁白"
        text = self.test_text.get().strip()
        if not text or not self._save_settings(show_status=False):
            return

        def work() -> None:
            try:
                self._status(f"测试语音生成：{speaker}｜{text}")
                pipeline = build_voice_pipeline(self.config)
                event = DialogueEvent(speaker, text, datetime.now(timezone.utc))
                artifact = pipeline.process(event)
                origin = "缓存命中" if artifact.from_cache else artifact.provider
                self._status(f"测试成功：{origin} / {artifact.codec}")
            except Exception as exc:
                self._status(f"测试失败：{exc}")

        threading.Thread(target=work, daemon=True).start()

    def _diagnose_regions(self) -> None:
        if self.config.speaker_region is None or self.config.dialogue_region is None:
            messagebox.showinfo("需要识别区域", "请先框选角色名和字幕正文区域。", parent=self.root)
            return

        def work() -> None:
            try:
                self._status("正在截取当前识别区域…")
                capture = MssScreenCapture()
                ocr = RapidOcrEngine()
                speaker = ocr.recognize(capture.capture(self.config.speaker_region))
                dialogue = ocr.recognize(capture.capture(self.config.dialogue_region))
                self._status(
                    f"区域测试：角色={speaker.text or '未识别'} ({speaker.confidence:.1%})｜"
                    f"字幕={dialogue.text or '未识别'} ({dialogue.confidence:.1%})"
                )
            except Exception as exc:
                self._status(f"区域测试失败：{exc}")

        threading.Thread(target=work, daemon=True).start()

    def _diagnose_files(self) -> None:
        selected = filedialog.askopenfilenames(
            parent=self.root,
            title="选择剧情截图（文件不会被复制或上传）",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.webp *.bmp"), ("所有文件", "*.*")],
        )
        if not selected:
            return

        def work() -> None:
            passed = 0
            engine = RapidOcrEngine()
            self._status(f"开始诊断 {len(selected)} 张本地截图…")
            for filename in selected:
                try:
                    with Image.open(filename) as image:
                        result = recognize_dialogue_frame(image.convert("RGB"), engine)
                    observation = result.observation
                    valid = bool(observation.speaker.strip() and observation.text.strip())
                    passed += int(valid)
                    self._status(
                        f"截图诊断 {Path(filename).name} [{result.layout}]："
                        f"{observation.speaker or '未识别'}｜{observation.text or '未识别'}"
                    )
                except Exception as exc:
                    self._status(f"截图诊断 {Path(filename).name} 失败：{exc}")
            self._status(f"截图诊断完成：{passed}/{len(selected)} 张同时识别出角色与字幕")

        threading.Thread(target=work, daemon=True).start()

    def _open_fixture(self) -> None:
        try:
            command = fixture_command()
            kwargs = {"cwd": str(Path.cwd())}
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            subprocess.Popen(command, **kwargs)
            self._status("已打开真实布局模拟剧情场景")
        except Exception as exc:
            self._status(f"无法打开模拟场景：{exc}")

    def _clear_cache(self) -> None:
        try:
            limit = int(self.cache_var.get()) * 1024 * 1024
            AudioCache(app_home() / "cache", limit).clear()
            self._status("语音缓存已清空")
        except Exception as exc:
            messagebox.showerror("无法清空缓存", str(exc), parent=self.root)

    def _clear_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self._append_log("系统", "日志已清空")

    def _append_log(self, category: str, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log.configure(state="normal")
        self.log.insert("end", f"{timestamp}  {category:<4}  {message}\n")
        line_count = int(self.log.index("end-1c").split(".")[0])
        if line_count > 500:
            self.log.delete("1.0", f"{line_count - 500}.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _status(self, message: str) -> None:
        def update() -> None:
            if not self.root.winfo_exists():
                return
            self.status_detail_var.set(message)
            self._append_log("运行", message)

        try:
            self.root.after(0, update)
        except tk.TclError:
            pass

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
