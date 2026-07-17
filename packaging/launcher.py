from __future__ import annotations

import json
import sys
from pathlib import Path

from genshin_autotts.demo import run_smoke
from genshin_autotts.fixture import run_fixture
from genshin_autotts.ui import run_gui


def _run_self_test(output: Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = {"ok": True, **run_smoke()}
        exit_code = 0
    except Exception as exc:
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        exit_code = 1
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return exit_code


def main() -> int:
    args = sys.argv[1:]
    if "--self-test" in args:
        index = args.index("--self-test")
        if index + 1 >= len(args):
            return 2
        return _run_self_test(Path(args[index + 1]).resolve())
    if "--fixture" in args:
        run_fixture()
        return 0
    run_gui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
