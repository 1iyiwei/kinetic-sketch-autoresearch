from PIL import Image, ImageDraw

from ksa.critic import fidelity_f1


def drawing(path, dx=0, scale=1.0, bg="white"):
    im = Image.new("RGB", (512, 512), bg)
    d = ImageDraw.Draw(im)
    r = 60 * scale
    d.ellipse([200 + dx - r, 256 - r, 200 + dx + r, 256 + r], outline="black", width=4)
    d.line([100 + dx, 400, 420 + dx, 400], fill="black", width=4)
    im.save(path)
    return path


def test_fidelity_identical_shifted_and_blank(tmp_path):
    a = drawing(tmp_path / "a.png")
    assert fidelity_f1(a, drawing(tmp_path / "same.png")) > 0.99
    assert fidelity_f1(a, drawing(tmp_path / "nudge.png", dx=1)) > 0.95  # within tolerance
    assert fidelity_f1(a, drawing(tmp_path / "moved.png", dx=40)) < 0.6
    assert fidelity_f1(a, drawing(tmp_path / "smaller.png", scale=0.6)) < 0.8
    Image.new("RGB", (512, 512), "white").save(tmp_path / "blank.png")
    assert fidelity_f1(a, tmp_path / "blank.png") == 0.0


def test_fidelity_on_colored_background(tmp_path):
    a = drawing(tmp_path / "a.png", bg="#fff8e7")
    assert fidelity_f1(a, drawing(tmp_path / "b.png", bg="#fff8e7")) > 0.99
