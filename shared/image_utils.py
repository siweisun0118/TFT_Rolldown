"""Utilities for recoloring set icons so they are visible in the GUI.

The trait icons that ship with the TFT data sets (e.g. ``TFT_Set_17/traits``)
are drawn white-on-transparent.  The GUI uses light/metallic backgrounds, so a
white icon is effectively invisible.  This module inverts the RGB channels of
those icons (keeping the alpha channel intact) so the artwork becomes dark and
shows up with high contrast against the board/bench backgrounds.

The conversion is performed *in place* but is made **idempotent** so it is safe
to run repeatedly and on future sets:

* A marker file ``<set_dir>/traits/.inverted_icons.json`` records which files
  have already been converted.
* As an extra safeguard a file is only inverted when its opaque pixels are
  predominantly light (near white).  This means an accidental double conversion
  (which would turn the icons back to white) cannot happen even if the marker
  file is deleted.
"""

# Standard libraries
import json
import sys
from pathlib import Path

# Third party libraries
from PIL import Image, ImageOps

# Name of the per-set marker file that tracks converted icons.
MARKER_NAME = ".inverted_icons.json"

# Opaque pixels brighter than this average luminance are considered "light".
# White icons average ~255; only light icons get inverted.
LIGHT_LUMINANCE_THRESHOLD = 160.0


def invert_rgb_keep_alpha(img):
    """Return a copy of ``img`` with RGB inverted and alpha preserved."""
    rgba = img.convert("RGBA")
    red, green, blue, alpha = rgba.split()

    # Invert only the colour channels; ImageOps.invert needs an RGB image.
    rgb = Image.merge("RGB", (red, green, blue))
    inverted_rgb = ImageOps.invert(rgb)
    inv_r, inv_g, inv_b = inverted_rgb.split()

    return Image.merge("RGBA", (inv_r, inv_g, inv_b, alpha))


def _mean_opaque_luminance(img):
    """Average luminance of the visible (non-transparent) pixels of ``img``."""
    rgba = img.convert("RGBA")
    total = 0.0
    count = 0
    for red, green, blue, alpha in rgba.getdata():
        # Ignore (almost) fully transparent pixels - they carry no colour.
        if alpha <= 10:
            continue
        # Rec. 601 luma.
        total += 0.299 * red + 0.587 * green + 0.114 * blue
        count += 1

    if count == 0:
        return 0.0
    return total / count


def _load_marker(traits_dir):
    """Load the set of already-converted file names for ``traits_dir``."""
    marker = traits_dir / MARKER_NAME
    if not marker.is_file():
        return set()
    try:
        with open(marker, encoding="utf-8") as handle:
            data = json.load(handle)
        return set(data.get("converted", []))
    except (json.JSONDecodeError, OSError):
        return set()


def _save_marker(traits_dir, converted):
    """Persist the set of converted file names for ``traits_dir``."""
    marker = traits_dir / MARKER_NAME
    with open(marker, mode="w", encoding="utf-8") as handle:
        json.dump({"converted": sorted(converted)}, handle, indent=2)


def invert_trait_icons(set_dir, force=False):
    """Invert every trait icon in ``<set_dir>/traits`` (in place, idempotent).

    Returns the list of file names that were converted by *this* call.
    Already-converted icons (recorded in the marker file) or icons that no
    longer look light are skipped, so the function is safe to call on every
    startup and on future sets.
    """
    set_dir = Path(set_dir)
    traits_dir = set_dir / "traits"
    if not traits_dir.is_dir():
        return []

    already = _load_marker(traits_dir)
    converted_now = []

    for png in sorted(traits_dir.glob("*.png")):
        name = png.name

        # Skip files we already converted unless explicitly forced.
        if name in already and not force:
            continue

        try:
            with Image.open(png) as img:
                img.load()

                # Safeguard: only invert genuinely light icons so a repeated
                # run (or a stale marker) cannot flip dark icons back to white.
                if not force and _mean_opaque_luminance(img) < LIGHT_LUMINANCE_THRESHOLD:
                    already.add(name)
                    continue

                inverted = invert_rgb_keep_alpha(img)

            inverted.save(png)
            converted_now.append(name)
            already.add(name)
        except OSError:
            # A single unreadable/corrupt icon should not break the GUI.
            continue

    _save_marker(traits_dir, already)
    return converted_now


def main(argv):
    """CLI entry point: ``python -m shared.image_utils <set_dir> [--force]``."""
    if len(argv) < 2:
        print("Usage: python -m shared.image_utils {set_dir} [--force]")
        return 1

    force = "--force" in argv[2:]
    converted = invert_trait_icons(argv[1], force=force)
    if converted:
        print(f"Inverted {len(converted)} trait icon(s) in {argv[1]}/traits")
    else:
        print(f"No trait icons needed inverting in {argv[1]}/traits")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
