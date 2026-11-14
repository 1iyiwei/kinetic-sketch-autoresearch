from pathlib import Path

from ksa.paths import relativize, resolve


def test_relativize_and_resolve_roundtrip(tmp_path):
    run = tmp_path / "run"
    data = {"gif": str(run / "fish/nodes/r0n0/render/anim.gif"), "frames": [str(run / "a.png")],
            "other": "/elsewhere/x.png", "n": 3}
    rel = relativize(data, run)
    assert rel["gif"] == "fish/nodes/r0n0/render/anim.gif" and rel["frames"] == ["a.png"]
    assert rel["other"] == "/elsewhere/x.png" and rel["n"] == 3
    assert resolve(rel["gif"], run) == run / "fish/nodes/r0n0/render/anim.gif"
    assert resolve("/abs/p.png", run) == Path("/abs/p.png")


def test_relativize_relative_base(tmp_path):
    assert relativize({"g": "runs/x/fish/a.gif"}, "runs/x") == {"g": "fish/a.gif"}
