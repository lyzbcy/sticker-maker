import json
from pathlib import Path
from sticker_engine.story.library import LinkageLibrary, Script


def test_library_loads_scripts(tmp_path):
    data = {
        "scripts": [
            {"id": "s1", "name": "n1", "type": "t", "characters": ["星星布丁"],
             "panels": [{"cn": "c", "en": "e", "emotion": "x", "action": "a"}] * 4}
        ]
    }
    p = tmp_path / "lib.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    lib = LinkageLibrary.load(p)
    assert len(lib.scripts) == 1
    assert lib.scripts[0].id == "s1"
    assert len(lib.scripts[0].panels) == 4


def test_library_handles_missing_file(tmp_path):
    lib = LinkageLibrary.load(tmp_path / "nope.json")
    assert lib.scripts == []
