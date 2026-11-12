"""Tiny stdlib-only PNG writer for tests. No Pillow, no committed binaries -
fixtures are generated on the fly with struct + zlib."""
import struct
import zlib


def _chunk(tag, data):
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def write_png(path, width, height, pixel_fn):
    """pixel_fn(x, y) -> (r, g, b) for an 8-bit RGB, no-filter PNG."""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter type: none
        for x in range(width):
            raw.extend(pixel_fn(x, y))
    idat = zlib.compress(bytes(raw), 9)
    with open(path, "wb") as f:
        f.write(sig)
        f.write(_chunk(b"IHDR", ihdr))
        f.write(_chunk(b"IDAT", idat))
        f.write(_chunk(b"IEND", b""))


def write_solid_png(path, width, height, rgb=(200, 60, 60)):
    write_png(path, width, height, lambda x, y: rgb)


def write_bordered_png(path, width, height, border, border_rgb=(255, 255, 255), center_rgb=(20, 120, 200)):
    def pixel(x, y):
        if border <= x < width - border and border <= y < height - border:
            return center_rgb
        return border_rgb

    write_png(path, width, height, pixel)


def build_exif_gps_app1(lat_deg=40.0, lon_deg=10.0):
    """Build a minimal, spec-compliant JPEG APP1/EXIF segment carrying only a GPS
    IFD (GPSLatitude/Ref, GPSLongitude/Ref). Constructed by hand instead of relying
    on `magick -set exif:...`, which cannot synthesize a brand-new EXIF profile on
    a JPEG that doesn't already have one."""

    def rational(num, den=1):
        return struct.pack("<II", num, den)

    def dms(deg):
        d = int(deg)
        m_full = (deg - d) * 60
        m = int(m_full)
        s = (m_full - m) * 60
        return [(d, 1), (m, 1), (int(round(s * 100)), 100)]

    tiff_header_offset = 8
    ifd0_size = 2 + 1 * 12 + 4  # one entry: the GPS IFD pointer
    gps_ifd_offset = tiff_header_offset + ifd0_size
    gps_entry_count = 4
    gps_ifd_size = 2 + gps_entry_count * 12 + 4
    data_area_offset = gps_ifd_offset + gps_ifd_size

    data = bytearray()
    entries = []

    def add_ascii(tag, s):
        val = s.encode("ascii") + b"\x00"
        count = len(val)
        if count <= 4:
            entries.append(struct.pack("<HHI4s", tag, 2, count, val.ljust(4, b"\x00")))
        else:
            offset = data_area_offset + len(data)
            entries.append(struct.pack("<HHII", tag, 2, count, offset))
            data.extend(val)

    def add_rational3(tag, vals):
        offset = data_area_offset + len(data)
        for num, den in vals:
            data.extend(rational(num, den))
        entries.append(struct.pack("<HHII", tag, 5, 3, offset))

    add_ascii(1, "N" if lat_deg >= 0 else "S")  # GPSLatitudeRef
    add_rational3(2, dms(abs(lat_deg)))  # GPSLatitude
    add_ascii(3, "E" if lon_deg >= 0 else "W")  # GPSLongitudeRef
    add_rational3(4, dms(abs(lon_deg)))  # GPSLongitude

    gps_ifd = struct.pack("<H", gps_entry_count) + b"".join(entries) + struct.pack("<I", 0) + bytes(data)
    ifd0 = (
        struct.pack("<H", 1)
        + struct.pack("<HHII", 0x8825, 4, 1, gps_ifd_offset)
        + struct.pack("<I", 0)
    )
    tiff = b"II*\x00" + struct.pack("<I", 8) + ifd0 + gps_ifd

    payload = b"Exif\x00\x00" + tiff
    return b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload


def write_jpeg_with_gps(magick_bin, base_png_path, dest_jpg_path, lat_deg=40.0, lon_deg=10.0):
    """Convert base_png_path to a plain JPEG (no metadata) with `magick`, then splice
    in a hand-built EXIF/GPS APP1 segment right after the SOI marker."""
    import subprocess

    plain_jpg = dest_jpg_path + ".plain.jpg"
    subprocess.run([magick_bin, base_png_path, plain_jpg], check=True, capture_output=True)

    with open(plain_jpg, "rb") as f:
        jpeg_bytes = f.read()
    if jpeg_bytes[:2] != b"\xff\xd8":
        raise RuntimeError("expected a JPEG output (missing SOI marker)")

    app1 = build_exif_gps_app1(lat_deg, lon_deg)
    with open(dest_jpg_path, "wb") as f:
        f.write(jpeg_bytes[:2])
        f.write(app1)
        f.write(jpeg_bytes[2:])


def build_exif_orientation_app1(orientation):
    """A minimal JPEG APP1/EXIF segment whose IFD0 holds only the Orientation tag
    (0x0112, SHORT). Hand-built for the same reason as build_exif_gps_app1."""
    ifd0 = (
        struct.pack("<H", 1)
        + struct.pack("<HHIHH", 0x0112, 3, 1, orientation, 0)
        + struct.pack("<I", 0)
    )
    tiff = b"II*\x00" + struct.pack("<I", 8) + ifd0
    payload = b"Exif\x00\x00" + tiff
    return b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload


def write_jpeg_with_orientation(magick_bin, base_png_path, dest_jpg_path, orientation):
    """Plain JPEG from base_png_path, then splice in an EXIF Orientation tag."""
    import subprocess

    plain_jpg = dest_jpg_path + ".plain.jpg"
    subprocess.run([magick_bin, base_png_path, plain_jpg], check=True, capture_output=True)
    with open(plain_jpg, "rb") as f:
        jpeg_bytes = f.read()
    if jpeg_bytes[:2] != b"\xff\xd8":
        raise RuntimeError("expected a JPEG output (missing SOI marker)")
    with open(dest_jpg_path, "wb") as f:
        f.write(jpeg_bytes[:2])
        f.write(build_exif_orientation_app1(orientation))
        f.write(jpeg_bytes[2:])


def write_rgba_png(path, width, height, pixel_fn):
    """pixel_fn(x, y) -> (r, g, b, a) for an 8-bit RGBA, no-filter PNG."""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw.extend(pixel_fn(x, y))
    with open(path, "wb") as f:
        f.write(sig)
        f.write(_chunk(b"IHDR", ihdr))
        f.write(_chunk(b"IDAT", zlib.compress(bytes(raw), 9)))
        f.write(_chunk(b"IEND", b""))


def fringed_disc_alpha(x, y, cx, cy, radius):
    """Coverage 0..255 of a disc with a 3-pixel soft edge."""
    d = ((x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2) ** 0.5
    return max(0, min(255, int(round((radius - d) / 3 * 255))))


def write_fringed_logo_png(path, size=40, rgb=(200, 20, 40), matte=(255, 255, 255)):
    """A cut-out disc whose soft edge was blended with `matte` (the white fringe of a
    logo cut from a white background): straight alpha, colour = a*rgb + (1-a)*matte."""
    def pixel(x, y):
        a = fringed_disc_alpha(x, y, size / 2, size / 2, size / 2 - 4)
        if a == 0:
            return (0, 0, 0, 0)
        f = a / 255
        return tuple(int(round(f * c + (1 - f) * m)) for c, m in zip(rgb, matte)) + (a,)

    write_rgba_png(path, size, size, pixel)
