from datetime import datetime, timezone
from pathlib import Path

from genshin_autotts.audio import NullAudioPlayer
from genshin_autotts.cache import AudioCache
from genshin_autotts.models import DialogueEvent
from genshin_autotts.pipeline import VoicePipeline
from genshin_autotts.voice import VoiceRegistry


class FakeTts:
    name = "fake"

    def synthesize(self, text, profile, target_base):
        path = target_base.with_suffix(".opus")
        path.write_bytes((profile.profile_id + text).encode("utf-8"))
        return path, "opus", self.name


def test_pipeline_generates_then_uses_cache(tmp_path) -> None:
    registry = VoiceRegistry(tmp_path / "profiles.json", "sapi")
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
