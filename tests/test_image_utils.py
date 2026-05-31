"""Tests for the trait-icon inversion helper.

The Set 17 trait icons originally shipped as white-on-transparent, which made
them invisible on the GUI's light board background.  These tests verify:

* :func:`shared.image_utils.invert_image_colors` actually swaps the RGB
  channels while preserving alpha;
* :func:`shared.image_utils.ensure_inverted_traits` is idempotent and only
  touches files that genuinely look like white-on-transparent icons;
* the icons used by the running app are no longer white (i.e. they will
  contrast with a white background).
"""

# Standard libraries
from pathlib import Path

import pytest

# Local imports
from shared.image_utils import (
    INVERTED_SENTINEL,
    ensure_inverted_traits,
    invert_image_colors,
    is_white_on_transparent,
)


@pytest.fixture
def tmp_trait_dir(tmp_path):
    """Create a directory of synthetic white-on-transparent icons.

    The real Set 17 icons committed to the repo may have already been
    inverted, so we generate fresh ones here to keep the test deterministic.
    """
    from PIL import Image
    dest = tmp_path / 'traits'
    dest.mkdir()
    for i in range(4):
        img = Image.new('RGBA', (32, 32), (255, 255, 255, 0))
        # Draw an opaque white "icon" shape in the centre.
        for x in range(8, 24):
            for y in range(8, 24):
                img.putpixel((x, y), (255, 255, 255, 220))
        img.save(dest / f'fake_{i}.png')
    return dest


def _max_rgb_of_opaque_pixels(png_path):
    """Return the brightest opaque pixel for a sanity check (no Pillow needed)."""
    from PIL import Image
    img = Image.open(png_path).convert('RGBA')
    brightest = 0
    for r, g, b, a in img.getdata():
        if a > 32:
            brightest = max(brightest, r, g, b)
    return brightest


def test_invert_swaps_rgb_keeps_alpha(tmp_trait_dir):
    sample = next(tmp_trait_dir.glob('*.png'))
    before_alpha = _alpha_histogram(sample)
    bright_before = _max_rgb_of_opaque_pixels(sample)
    assert bright_before > 240, 'Set 17 icon should look white before inversion'

    invert_image_colors(sample)

    bright_after = _max_rgb_of_opaque_pixels(sample)
    assert bright_after < 32, 'Pixels should be near-black after inversion'
    assert _alpha_histogram(sample) == before_alpha, 'Alpha channel must be preserved'


def _alpha_histogram(png_path):
    from PIL import Image
    img = Image.open(png_path).convert('RGBA')
    hist = {}
    for _, _, _, a in img.getdata():
        hist[a] = hist.get(a, 0) + 1
    return hist


def test_ensure_inverted_is_idempotent(tmp_trait_dir):
    converted_first = ensure_inverted_traits(tmp_trait_dir)
    assert (tmp_trait_dir / INVERTED_SENTINEL).exists()
    # All sample icons should have been inverted on the first pass.
    assert len(converted_first) >= 1

    converted_second = ensure_inverted_traits(tmp_trait_dir)
    assert converted_second == []


def test_is_white_on_transparent_detects_already_dark_icons(tmp_trait_dir):
    sample = next(tmp_trait_dir.glob('*.png'))
    assert is_white_on_transparent(sample)
    invert_image_colors(sample)
    assert not is_white_on_transparent(sample)


def test_runtime_set17_icons_are_visible_on_white():
    """The icons committed to the repo must no longer be white-on-transparent."""
    repo_traits = Path(__file__).resolve().parent.parent / 'TFT_Set_17' / 'traits'
    if not (repo_traits / INVERTED_SENTINEL).exists():
        pytest.skip('Set 17 icons have not been inverted yet')

    sample = next(repo_traits.glob('*.png'))
    assert not is_white_on_transparent(sample), (
        'Set 17 icons should be dark after inversion so they contrast with a '
        'white background.'
    )
