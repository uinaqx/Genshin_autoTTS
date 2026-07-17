from genshin_autotts.cache import AudioCache


def test_cache_put_get_and_clear(tmp_path) -> None:
    cache = AudioCache(tmp_path / "cache", 1024)
    source = cache.temporary_path("a" * 64, ".opus")
    source.write_bytes(b"voice")
    final = cache.put("a" * 64, source, "opus", "fake")
    assert final.exists()
    hit = cache.get("a" * 64)
    assert hit is not None
    assert hit[0] == final
    cache.clear()
    assert cache.get("a" * 64) is None


def test_cache_evicts_oldest(tmp_path) -> None:
    cache = AudioCache(tmp_path / "cache", 10)
    for key in ("a" * 64, "b" * 64):
        source = cache.temporary_path(key, ".opus")
        source.write_bytes(b"12345678")
        cache.put(key, source, "opus", "fake")
    assert cache.total_bytes() <= 10
    assert cache.get("b" * 64) is not None
