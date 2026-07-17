from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .config import app_home, load_config
from .demo import run_demo, run_smoke
from .fixture import run_fixture
from .ui import run_gui


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="genshin-autotts")
    result.add_argument("--version", action="version", version=__version__)
    sub = result.add_subparsers(dest="command")
    sub.add_parser("gui", help="启动桌面界面")
    demo = sub.add_parser("demo", help="不截图，直接测试音色、TTS、缓存与播放")
    demo.add_argument("--speaker", default="真人示例")
    demo.add_argument("--text", default="zero")
    demo.add_argument("--provider", choices=["recorded", "edge"], default="recorded")
    demo.add_argument("--voice-pack", help="真人录音包 manifest.json 路径")
    demo.add_argument("--play", action="store_true")
    sub.add_parser("smoke", help="运行真实 OCR + 真人录音 + 缓存冒烟测试")
    sub.add_parser("fixture", help="启动可供屏幕框选的游戏字幕测试场景")
    sub.add_parser("config", help="显示运行时配置和数据目录")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    command = args.command or "gui"
    if command == "gui":
        run_gui()
        return 0
    if command == "demo":
        artifact = run_demo(
            args.speaker,
            args.text,
            args.provider,
            args.play,
            args.voice_pack,
        )
        print(json.dumps(artifact.__dict__, ensure_ascii=False, indent=2))
        return 0
    if command == "smoke":
        print(json.dumps(run_smoke(), ensure_ascii=False, indent=2))
        return 0
    if command == "fixture":
        run_fixture()
        return 0
    if command == "config":
        print(json.dumps(load_config().to_dict(), ensure_ascii=False, indent=2))
        print(f"runtime_home={app_home()}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
