import asyncio
from pathlib import Path

from ksa.render import Renderer

FIX = Path(__file__).parent / "fixtures"


def test_reference_animation_renders(tmp_path):
    async def go():
        async with Renderer() as r:
            ok = await r.render((FIX / "windmill_ref.html").read_text(), tmp_path / "ok", duration=1.0, fps=4)
            bad = await r.render("<html><body>no contract</body></html>", tmp_path / "bad")
            throws = await r.render("<script>window.ksaRender = t => { if (t > 0.5) nope(); }</script>",
                                    tmp_path / "throws", duration=1.0, fps=4)
        return ok, bad, throws

    ok, bad, throws = asyncio.run(go())
    assert ok.ok and len(ok.frames) == 5 and ok.gif.exists() and ok.sheet.exists()
    assert ok.frames[0].read_bytes() != ok.frames[-1].read_bytes()  # it actually moves
    assert not bad.ok and "ksaRender" in bad.errors[0]
    assert not throws.ok and "threw" in throws.errors[-1]
