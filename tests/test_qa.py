from genshin_autotts.fixture import LINES, render_dialogue_scene
from genshin_autotts.qa import collect_image_paths


def test_collect_image_paths_ignores_non_images(tmp_path) -> None:
    render_dialogue_scene(LINES[0]).save(tmp_path / "scene.png")
    (tmp_path / "notes.txt").write_text("not an image", encoding="utf-8")
    assert collect_image_paths([str(tmp_path)]) == [tmp_path / "scene.png"]
