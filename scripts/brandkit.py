#!/usr/bin/env python3
"""brandkit.py - logo variants for a brand kit from one cut-out logo: the logo as it is
(color), a greyscale version (mono), a white and a black silhouette, and the colour logo
with clear space around it - each at full size and at every --sizes long edge - plus
the logo's main colours as a palette with each colour's share of the logo.

Every value is an argument: --sizes (long edges in pixels, never larger than the logo),
--clear-space (transparent margin in pixels of the full-size logo, scaled with it) and
--palette (at most this many colours). The logo must have a transparent background: the
white and black versions are its shape, and a logo without alpha has no shape
(alpha.py --mode report says what a file carries). Writes PNG; ImageMagick only.

The palette counts pixels whose alpha is at least 50% (antialiased edges below that are
left out), quantised without dithering to 32 colours, and reports the --palette largest
of them; share is each colour's fraction of the counted pixels, so the shares add up to
less than 1 when the logo has more colours than --palette. Merging everything into
--palette colours instead would report averages that are not in the logo. It reports the
logo's colours; it never picks colours for the caller.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (  # noqa: E402
    ImageSkillError,
    JSONArgumentParser,
    add_timeout_arg,
    check_output_not_exists,
    check_output_not_input,
    fail_error,
    magick_info,
    non_negative_int,
    positive_int,
    require_input,
    run,
    run_tool,
    select_backend,
    succeed,
    verify_output_format,
    wants_json,
)

QUANTISE = 32  # colours the logo is reduced to before the largest --palette are reported
VARIANTS = ("color", "mono", "white", "black", "clearspace")
VARIANT_OPS = {
    "color": [],
    "mono": ["-colorspace", "gray"],
    "white": ["-channel", "RGB", "-evaluate", "set", "100%", "+channel"],
    "black": ["-channel", "RGB", "-evaluate", "set", "0", "+channel"],
}


def _sizes(value):
    if not re.fullmatch(r"\s*\d+(\s*,\s*\d+)*\s*", value or ""):
        raise ImageSkillError(f"--sizes must be a comma-separated list of pixel sizes, got {value!r}")
    sizes = sorted({int(v) for v in value.split(",")}, reverse=True)
    if any(s <= 0 for s in sizes):
        raise ImageSkillError("--sizes must be positive")
    return sizes


def build_parser():
    parser = JSONArgumentParser(
        description="Make colour, mono, white, black and clear-space logo variants at given sizes, plus a colour palette")
    parser.add_argument("input", help="logo with a transparent background (never modified)")
    parser.add_argument("-o", "--output-dir", required=True, help="folder to write the variants into (created if missing)")
    parser.add_argument("--sizes", required=True,
                        help="long edges in pixels to write every variant at, e.g. 1024,512,256 (never above the logo's)")
    parser.add_argument("--clear-space", type=non_negative_int, required=True,
                        help="transparent margin on every side of the clearspace variant, in pixels of the full-size logo")
    parser.add_argument("--palette", type=positive_int, required=True,
                        help="report at most this many main colours, largest share first (2-32)")
    parser.add_argument("--overwrite", action="store_true", help="allow replacing existing variant files")
    parser.add_argument("--json", action="store_true", help="print one JSON object (ok:true/false) instead of text")
    parser.add_argument("--dry-run", action="store_true", help="print the backend commands that would run, write nothing")
    add_timeout_arg(parser)
    return parser


def scaled(width, height, long_edge):
    """width x height scaled so its long edge is long_edge, rounded like ImageMagick."""
    factor = long_edge / max(width, height)
    return max(1, int(round(width * factor))), max(1, int(round(height * factor)))


def palette(magick, path, count):
    """Main colours of the pixels with alpha >= 50%: [{hex, share}], largest share first."""
    out = run([magick, f"{path}[0]", "-auto-orient", "-colorspace", "sRGB", "-alpha", "set", "-channel", "A", "-threshold", "50%", "+channel",
               "+dither", "-colors", str(QUANTISE + 1), "-depth", "8", "-format", "%c", "histogram:info:"])["stdout"]
    entries = []
    for line in out.splitlines():
        m = re.match(r"\s*(\d+):\s*\(([^)]*)\)\s*#([0-9A-Fa-f]{6})([0-9A-Fa-f]{2})?", line)
        if not m:
            continue
        values = [float(v) for v in m.group(2).split(",")]
        alpha = values[3] if len(values) == 4 else 255.0
        if alpha < 128:
            continue
        entries.append((int(m.group(1)), "#" + m.group(3).upper()))
    merged = {}
    for n, hex_ in entries:
        merged[hex_] = merged.get(hex_, 0) + n
    ranked = sorted(merged.items(), key=lambda kv: (-kv[1], kv[0]))[:count]
    total = sum(merged.values())
    if not total:
        raise ImageSkillError("the logo has no pixel with alpha of 50% or more, so it has no colours to report")
    return [{"hex": h, "share": round(n / total, 4)} for h, n in ranked], total


def run_brandkit(args):
    require_input(args.input)
    sizes = _sizes(args.sizes)
    if not 2 <= args.palette <= 32:
        raise ImageSkillError("--palette must be between 2 and 32 colours")
    backend, magick = select_backend("sips cannot make logo variants")
    width, height, alpha = magick_info(magick, args.input, "%w %h %A").split()
    width, height = int(width), int(height)
    if alpha.lower() in ("false", "undefined"):
        raise ImageSkillError(
            f"{args.input} has no alpha channel; the white, black and clear-space variants need a logo with a "
            "transparent background (cut it out first)")
    if max(sizes) > max(width, height):
        raise ImageSkillError(
            f"the logo is {width}x{height} but --sizes asks for a long edge of {max(sizes)}; variants are never "
            "upscaled - use a larger source or smaller sizes")

    out_dir = os.path.abspath(args.output_dir)
    parent = os.path.dirname(out_dir)
    if not os.path.isdir(parent):
        raise ImageSkillError(f"parent directory does not exist: {parent}")

    pad = args.clear_space
    full = {name: (width, height) for name in VARIANT_OPS}
    full["clearspace"] = (width + 2 * pad, height + 2 * pad)
    plan = []
    for name in VARIANTS:
        ops = VARIANT_OPS.get(name, ["-background", "none", "-gravity", "center",
                                     "-extent", f"{full['clearspace'][0]}x{full['clearspace'][1]}"])
        for size in [None] + sizes:
            w, h = full[name] if size is None else scaled(*full[name], size)
            resize = [] if size is None else ["-resize", f"{w}x{h}!"]
            fname = f"logo-{name}.png" if size is None else f"logo-{name}-{size}.png"
            path = os.path.join(out_dir, fname)
            check_output_not_input(args.input, path)
            check_output_not_exists(path, allow_overwrite=args.overwrite)
            cmd = [magick, f"{args.input}[0]", "-auto-orient", "-colorspace", "sRGB", "-alpha", "set"] + ops + resize + [f"PNG32:{path}"]
            plan.append({"variant": name, "long_edge": size or max(full[name]), "width": w, "height": h,
                         "path": path, "cmd": cmd})

    if args.dry_run:
        return {"dry_run": True, "would_run": [p["cmd"] for p in plan]}

    os.makedirs(out_dir, exist_ok=True)
    files = []
    for item in plan:
        run(item["cmd"])
        verify_output_format(item["path"], backend)
        got = tuple(int(v) for v in magick_info(magick, item["path"], "%w %h", auto_orient=False).split())
        if got != (item["width"], item["height"]):
            os.remove(item["path"])
            raise ImageSkillError(f"{item['path']} is {got[0]}x{got[1]}, expected {item['width']}x{item['height']}")
        files.append({k: item[k] for k in ("path", "variant", "long_edge", "width", "height")})

    colours, counted = palette(magick, args.input, args.palette)
    return {
        "input": args.input,
        "output_dir": out_dir,
        "original": {"width": width, "height": height},
        "clear_space": pad,
        "files": files,
        "palette": colours,
        "palette_pixels": counted,
        "backend": backend,
    }


def main(argv=None):
    as_json = wants_json(argv)
    try:
        args = build_parser().parse_args(argv)
        payload = run_tool(run_brandkit, args)
    except ImageSkillError as e:
        fail_error(e, as_json)
        return
    succeed(payload, args.json)


if __name__ == "__main__":
    main()
