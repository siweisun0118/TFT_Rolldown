"""Helpers for converting / processing trait icon images."""

# Standard libraries
from pathlib import Path


# Third party libraries
from PIL import Image, ImageOps


# Local files
from shared.rolldown_enums import INVERTED_SENTINEL


def invert_image_colors(input_path, output_path=None):
    """Invert the RGB channels of an image, preserving the alpha channel."""
    input_path = Path(input_path)
    if output_path is None:
        output_path = input_path
    else:
        output_path = Path(output_path)

    img = Image.open(input_path).convert('RGBA')
    rgb = img.convert('RGB')
    inverted = ImageOps.invert(rgb)
    # Re-attach alpha channel from the original image.
    r, g, b = inverted.split()
    _, _, _, a = img.split()
    out = Image.merge('RGBA', (r, g, b, a))
    out.save(output_path)

    return output_path


def is_white_on_transparent(image_path, sample_size=64):
    """Return ``True`` if *image_path* looks like a white-on-transparent icon."""
    image_path = Path(image_path)
    img = Image.open(image_path).convert('RGBA')
    width, height = img.size
    step = max(1, min(width, height) // sample_size)
    for y in range(0, height, step):
        for x in range(0, width, step):
            r, g, b, a = img.getpixel((x, y))
            if a > 16 and (r < 240 or g < 240 or b < 240):
                return False
    return True


def ensure_inverted_traits(traits_dir):
    """Invert every PNG in *traits_dir* if not already inverted."""
    traits_dir = Path(traits_dir)
    if not traits_dir.is_dir():
        return []

    sentinel = traits_dir / INVERTED_SENTINEL
    if sentinel.exists():
        return []

    converted = []
    for png in sorted(traits_dir.glob('*.png')):
        try:
            if is_white_on_transparent(png):
                invert_image_colors(png)
                converted.append(png)
        except (OSError, ValueError) as err:
            # Don't let a single broken file stop us from processing the rest.
            print(f'Failed to invert {png}: {err}')

    sentinel.write_text('Trait icons have been inverted by image_utils.', encoding='utf-8')
    return converted
