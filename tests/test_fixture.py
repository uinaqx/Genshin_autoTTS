from genshin_autotts.fixture import LINES, fixture_regions, render_dialogue_scene


def test_fixture_renders_full_hd_compatible_scene() -> None:
    image = render_dialogue_scene(LINES[0], (1280, 720))
    assert image.mode == "RGB"
    assert image.size == (1280, 720)


def test_fixture_exposes_matching_screen_regions() -> None:
    speaker, dialogue = fixture_regions((1280, 720))
    assert speaker == (448, 518, 384, 65)
    assert dialogue == (256, 569, 768, 94)
