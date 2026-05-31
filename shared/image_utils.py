"""Helpers for converting / processing trait icon images.

Some trait icon PNGs (notably Set 17) ship as white-on-transparent which makes
them invisible on the light board background used by the GUI.  This module
exposes :func:`invert_image_colors` which inverts the RGB channels (leaving the
alpha channel untouched) and :func:`ensure_inverted_traits` which walks a
set's ``traits/`` directory and persists an inverted copy of each PNG so the
icon is visible on light backgrounds.

The conversion is idempotent – once an icon has been inverted a sentinel file
named ``.inverted`` is dropped in the directory so subsequent runs are a no-op.
"""

# Standard libraries
from pathlib import Path


# Sentinel filename that marks a traits/ directory as already inverted.
INVERTED_SENTINEL = '.inverted'


def _has_pil():
    """Return True if Pillow is importable.

    Pillow is the implementation we prefer.  When it's missing we fall back to
    a tiny pure-Python PNG handler so the GUI is still usable, but with
    diminished fidelity (and noticeably more memory use).
    """
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        return False


def invert_image_colors(input_path, output_path=None):
    """Invert the RGB channels of an image, preserving the alpha channel.

    If *output_path* is ``None`` the image is saved back over *input_path*.

    Returns the resolved output path.
    """
    input_path = Path(input_path)
    if output_path is None:
        output_path = input_path
    else:
        output_path = Path(output_path)

    if _has_pil():
        from PIL import Image, ImageOps  # pylint: disable=import-outside-toplevel
        img = Image.open(input_path).convert('RGBA')
        rgb = img.convert('RGB')
        inverted = ImageOps.invert(rgb)
        # Re-attach alpha channel from the original image.
        r, g, b = inverted.split()
        _, _, _, a = img.split()
        out = Image.merge('RGBA', (r, g, b, a))
        out.save(output_path)
    else:
        # Pure-Python fallback that handles PNGs by leveraging the standard
        # library.  It is much slower but keeps the package working without
        # Pillow.
        _invert_png_stdlib(input_path, output_path)

    return output_path


def _invert_png_stdlib(input_path, output_path):
    """Invert RGBA PNGs using only the standard library.

    The implementation relies on ``zlib`` for decompression and a manual
    parser for the PNG chunks.  We only support 8-bit RGBA PNGs which is the
    format used by every trait icon in the repository.
    """
    # pylint: disable=import-outside-toplevel
    import struct
    import zlib

    with open(input_path, 'rb') as in_file:
        data = in_file.read()

    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError(f'{input_path} is not a PNG file')

    # Split the file into chunks ----------------------------------------------------
    chunks = []
    idx = 8
    while idx < len(data):
        length = struct.unpack('!I', data[idx:idx + 4])[0]
        chunk_type = data[idx + 4:idx + 8]
        chunk_data = data[idx + 8:idx + 8 + length]
        chunks.append([chunk_type, chunk_data])
        idx += 8 + length + 4  # 4 bytes CRC

    header = next(c for c in chunks if c[0] == b'IHDR')[1]
    width, height, bit_depth, color_type = struct.unpack('!IIBB', header[:10])
    if bit_depth != 8 or color_type != 6:
        raise ValueError(
            f'Unsupported PNG: {input_path} (depth={bit_depth}, color_type={color_type}). '
            'Install Pillow to handle this image.'
        )

    raw = b''.join(c[1] for c in chunks if c[0] == b'IDAT')
    raw = zlib.decompress(raw)

    stride = width * 4
    rows = []
    prev_row = bytearray(stride)
    pos = 0
    for _ in range(height):
        filter_byte = raw[pos]
        row = bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        rows.append(_defilter_row(filter_byte, row, prev_row, 4))
        prev_row = rows[-1]

    # Invert RGB; keep alpha.
    new_rows = []
    for row in rows:
        inverted = bytearray(row)
        for i in range(0, stride, 4):
            inverted[i] = 255 - row[i]
            inverted[i + 1] = 255 - row[i + 1]
            inverted[i + 2] = 255 - row[i + 2]
        new_rows.append(inverted)

    payload = bytearray()
    for row in new_rows:
        payload.append(0)  # filter type "None"
        payload.extend(row)

    compressed = zlib.compress(bytes(payload), level=9)

    # Re-emit the PNG with the new IDAT.
    new_chunks = [c for c in chunks if c[0] != b'IDAT']
    iend_idx = next(i for i, c in enumerate(new_chunks) if c[0] == b'IEND')
    new_chunks.insert(iend_idx, [b'IDAT', compressed])

    out = bytearray(b'\x89PNG\r\n\x1a\n')
    for chunk_type, chunk_data in new_chunks:
        out += struct.pack('!I', len(chunk_data))
        out += chunk_type
        out += chunk_data
        crc = zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
        out += struct.pack('!I', crc)

    with open(output_path, 'wb') as out_file:
        out_file.write(out)


def _defilter_row(filter_type, row, prev_row, bpp):
    """Apply the inverse PNG filter to a row."""
    if filter_type == 0:
        return row
    out = bytearray(len(row))
    for i, byte in enumerate(row):
        left = out[i - bpp] if i >= bpp else 0
        up = prev_row[i] if prev_row else 0
        up_left = prev_row[i - bpp] if (prev_row and i >= bpp) else 0
        if filter_type == 1:
            value = byte + left
        elif filter_type == 2:
            value = byte + up
        elif filter_type == 3:
            value = byte + (left + up) // 2
        elif filter_type == 4:
            value = byte + _paeth(left, up, up_left)
        else:
            raise ValueError(f'Unknown filter type: {filter_type}')
        out[i] = value & 0xFF
    return out


def _paeth(a, b, c):
    """Standard PNG Paeth predictor."""
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def is_white_on_transparent(image_path, sample_size=64):
    """Return ``True`` if *image_path* looks like a white-on-transparent icon.

    We sample the image and check whether *every* opaque pixel is close to
    white (each channel >= 240).  This lets us avoid double-inverting icons
    that already look correct.
    """
    image_path = Path(image_path)
    if _has_pil():
        from PIL import Image  # pylint: disable=import-outside-toplevel
        img = Image.open(image_path).convert('RGBA')
        width, height = img.size
        step = max(1, min(width, height) // sample_size)
        for y in range(0, height, step):
            for x in range(0, width, step):
                r, g, b, a = img.getpixel((x, y))
                if a > 16 and (r < 240 or g < 240 or b < 240):
                    return False
        return True
    # Without Pillow we conservatively assume the image needs inversion.
    return True


def ensure_inverted_traits(traits_dir):
    """Invert every PNG in *traits_dir* if not already inverted.

    The directory is only inverted once – a sentinel file is created on
    success so subsequent calls are essentially free.  Set images that do not
    look like white-on-transparent icons are left alone so that pre-coloured
    art (e.g. earlier sets) is not damaged.
    """
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
