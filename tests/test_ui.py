import json
import sys

from genshin_autotts.models import Region
from genshin_autotts.ui import MainWindow, fixture_command, format_region, voice_pack_summary


def test_region_summary_is_readable() -> None:
    assert format_region(None) == "尚未设置"
    assert format_region(Region(10, 20, 300, 80)) == "X 10  ·  Y 20  ·  300 × 80"


def test_voice_pack_summary_reports_manifest(tmp_path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "pack_id": "world-quest-pack",
                "pack_version": "2026.07",
                "entries": [{"speaker": "派蒙"}, {"speaker": "赛芭"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    assert voice_pack_summary(str(manifest)) == "world-quest-pack  ·  2026.07  ·  2 条录音"


def test_fixture_command_supports_source_and_frozen_builds(monkeypatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert fixture_command() == [sys.executable, "-m", "genshin_autotts", "fixture"]

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert fixture_command() == [sys.executable, "--fixture"]


def test_formal_window_builds_without_clipped_controls(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GENSHIN_AUTOTTS_HOME", str(tmp_path / "runtime"))
    app = MainWindow()
    try:
        app.root.geometry("1180x760")
        app.root.update()
        root_width = app.root.winfo_width()
        root_height = app.root.winfo_height()
        root_x = app.root.winfo_rootx()
        root_y = app.root.winfo_rooty()
        overflows = []

        def inspect(widget) -> None:
            for child in widget.winfo_children():
                if child.winfo_ismapped():
                    x = child.winfo_rootx() - root_x
                    y = child.winfo_rooty() - root_y
                    if x < -2 or y < -2:
                        overflows.append(str(child))
                    if x + child.winfo_width() > root_width + 2:
                        overflows.append(str(child))
                    if y + child.winfo_height() > root_height + 2:
                        overflows.append(str(child))
                inspect(child)

        inspect(app.root)
        assert not overflows
        assert app.start_button.winfo_width() >= 120
        assert app.stop_button.winfo_height() >= 40
        assert app.log.winfo_height() >= 70
        assert app.provider_var.get() == "火山引擎"
        assert app.config.tts_provider == "volcengine"

        app._apply_fullscreen_preset()
        assert app.config.speaker_region is not None
        assert app.config.dialogue_region is not None
        assert app.status_var.get() == "准备就绪"
    finally:
        app.root.destroy()
