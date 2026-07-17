from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from genshin_autotts.audio import NullAudioPlayer
from genshin_autotts.cache import AudioCache
from genshin_autotts.models import DialogueEvent, DialogueObservation
from genshin_autotts.pipeline import PipelineController, VoicePipeline
from genshin_autotts.voice import VoiceRegistry


class FakeTts:
    name = "fake"

    def synthesize(self, text, profile, target_base):
        path = target_base.with_suffix(".opus")
        path.write_bytes((profile.profile_id + text).encode("utf-8"))
        return path, "opus", self.name


def test_pipeline_generates_then_uses_cache(tmp_path) -> None:
    registry = VoiceRegistry(tmp_path / "profiles.json", "edge")
    cache = AudioCache(tmp_path / "cache", 1024 * 1024)
    player = NullAudioPlayer()
    pipeline = VoicePipeline(registry, FakeTts(), cache, player)
    event = DialogueEvent("派蒙", "出发吧", datetime.now(timezone.utc))
    first = pipeline.process(event)
    second = pipeline.process(event)
    assert not first.from_cache
    assert second.from_cache
    assert Path(first.path).exists()
    assert len(player.played) == 2


def test_controller_only_reports_unchanged_ocr_once() -> None:
    class RepeatingSource:
        def __init__(self) -> None:
            self.reads = 0
            self.stop_event = None

        def read(self) -> DialogueObservation:
            self.reads += 1
            if self.reads > 3:
                self.stop_event.set()
            return DialogueObservation("旁白", "风从山谷吹来。")

    source = RepeatingSource()
    messages: list[str] = []
    controller = PipelineController(
        source=source,
        stabilizer=SimpleNamespace(observe=lambda _observation: None),
        voice_pipeline=SimpleNamespace(
            play_audio=False,
            player=SimpleNamespace(stop=lambda: None),
        ),
        interval_ms=1,
        status=messages.append,
    )
    source.stop_event = controller._stop

    controller._capture_loop()

    assert messages == ["OCR：旁白｜风从山谷吹来。"]
