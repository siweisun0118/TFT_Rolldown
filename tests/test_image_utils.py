"""Trait icon inversion: visibility, alpha preservation, idempotency."""

import shutil

from PIL import Image

from shared.image_utils import invert_trait_icons


def _make_white_icon(path):
    """A white-on-transparent icon similar to the shipped trait art."""
    img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    for x in range(8, 24):
        for y in range(8, 24):
            img.putpixel((x, y), (255, 255, 255, 255))
    img.save(path)


def _opaque_pixels(path):
    img = Image.open(path).convert("RGBA")
    return [p for p in img.getdata() if p[3] > 10]


def test_inversion_makes_icons_dark_and_keeps_alpha(tmp_path):
    traits = tmp_path / "traits"
    traits.mkdir()
    icon = traits / "Sample.png"
    _make_white_icon(icon)

    before = _opaque_pixels(icon)
    assert all(p[:3] == (255, 255, 255) for p in before)

    converted = invert_trait_icons(tmp_path)
    assert "Sample.png" in converted

    after = _opaque_pixels(icon)
    # Primary colour is no longer white -> high contrast vs light backgrounds.
    assert all(p[:3] == (0, 0, 0) for p in after)
    # Alpha channel (the shape) is untouched.
    assert [p[3] for p in before] == [p[3] for p in after]


def test_inversion_is_idempotent(tmp_path):
    traits = tmp_path / "traits"
    traits.mkdir()
    icon = traits / "Sample.png"
    _make_white_icon(icon)

    invert_trait_icons(tmp_path)
    first = _opaque_pixels(icon)

    # A second run must be a no-op (it must NOT flip the icon back to white).
    second_converted = invert_trait_icons(tmp_path)
    assert second_converted == []
    assert _opaque_pixels(icon) == first
    assert all(p[:3] == (0, 0, 0) for p in _opaque_pixels(icon))


def test_inversion_on_real_set_copy(tmp_path):
    """Invert a copy of the real Set 17 trait art and check contrast."""
    from conftest import SET_DIR

    src = SET_DIR / "traits"
    dst = tmp_path / "traits"
    dst.mkdir()
    sample = sorted(src.glob("*.png"))[0]
    shutil.copy(sample, dst / sample.name)

    invert_trait_icons(tmp_path)
    opaque = _opaque_pixels(dst / sample.name)
    assert opaque, "icon should still have visible pixels"
    avg = sum(0.299 * r + 0.587 * g + 0.114 * b for r, g, b, _ in opaque) / len(opaque)
    # Dark icons contrast strongly with the light board/bench backgrounds.
    assert avg < 96
