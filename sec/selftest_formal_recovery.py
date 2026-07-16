from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .formal_recovery import _file_records, _sha256
from .resume_p3e_target import TARGET_CONDITION, target_config


def main() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        run = root / "runs" / "condition"
        run.mkdir(parents=True)
        (run / "result.json").write_text(
            json.dumps({"status": "complete"}),
            encoding="utf-8",
        )
        (run / "manifest.json").write_text(
            json.dumps({"condition": "condition"}),
            encoding="utf-8",
        )
        records = _file_records([run], root)
        assert len(records) == 2
        for record in records:
            path = root / record["path"]
            assert path.exists()
            assert record["sha256"] == _sha256(path)

    cfg, family, args = target_config(
        family="choose-list",
        seed=2,
        arm="consolidated",
    )
    assert family == "choose-list"
    assert args.phase == "gamma_p3_formal"
    assert cfg.seed == 2
    assert cfg.notes == ["consolidated"]
    from .config import condition_name

    assert condition_name(cfg) == TARGET_CONDITION
    print("selftest_formal_recovery OK")


if __name__ == "__main__":
    main()
