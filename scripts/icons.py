#!/usr/bin/env python3
"""icons.py - make a site's icon set from one square image in one command: favicon.ico
holding several sizes, PNG icons (including the 192/512 a web app manifest needs) and
apple-touch-icon.png, plus the HTML <link> tags and manifest entries that use them.

Default sizes follow published guidance (see presets.json for the sources): ICO
16/32/48, PNG 32/192/512, apple-touch-icon 180. The source must be square (crop.py or
pad.py first) and at least as large as the largest icon - icons are never upscaled.
An apple-touch-icon keeps transparency unless --apple-background is given (iOS shows
transparent areas as black). ImageMagick only.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (  # noqa: E402
    ImageSkillError,
    JSONArgumentParser,
    check_output_not_exists,
    check_output_not_input,
    color_arg,
    magick_info,
    run,
    select_backend,
    succeed,
    verify_output_format,
    wants_json,
    require_input,
    add_timeout_arg,
    run_tool,
    fail_error,
)


def _sizes(value, name):
    if not re.fullmatch(r"\s*\d+(\s*,\s*\d+)*\s*", value or ""):
        raise ImageSkillError(f"{name} must be a comma-separated list of pixel sizes, got {value!r}")
    sizes = sorted({int(v) for v in value.split(",")}, reverse=True)
    if any(s <= 0 for s in sizes):
        raise ImageSkillError(f"{name} sizes must be positive")
    return sizes


def build_parser():
    parser = JSONArgumentParser(description="Make favicon.ico, PNG icons and apple-touch-icon.png from one square image")
    parser.add_argument("input", help="square source image (never modified), at least as large as the largest icon")
    parser.add_argument("-o", "--output-dir", required=True, help="folder to write the icon files into (created if missing)")
    parser.add_argument("--ico-sizes", default="16,32,48", help="sizes inside favicon.ico, max 256 (default 16,32,48)")
    parser.add_argument("--png-sizes", default="32,192,512", help="PNG icons to write as icon-NxN.png (default 32,192,512)")
    parser.add_argument("--apple-size", type=int, default=180, help="apple-touch-icon.png size, 0 to skip (default 180)")
    parser.add_argument("--apple-background", type=color_arg, help="flatten apple-touch-icon.png onto this colour")
    parser.add_argument("--overwrite", action="store_true", help="allow replacing existing icon files")
    parser.add_argument("--json", action="store_true", help="print one JSON object (ok:true/false) instead of text")
    parser.add_argument("--dry-run", action="store_true", help="print the backend commands that would run, write nothing")
    add_timeout_arg(parser)
    return parser


def run_icons(args):
    require_input(args.input)
    ico = _sizes(args.ico_sizes, "--ico-sizes")
    pngs = _sizes(args.png_sizes, "--png-sizes")
    if max(ico) > 256:
        raise ImageSkillError("an ICO entry cannot be larger than 256 pixels")
    if args.apple_size < 0:
        raise ImageSkillError("--apple-size must be 0 (skip) or positive")
    backend, magick = select_backend("sips cannot write ICO files or icon sets")

    width, height, alpha = magick_info(magick, args.input, "%w %h %A").split()
    width, height = int(width), int(height)
    has_alpha = alpha.lower() not in ("false", "undefined")
    if width != height:
        raise ImageSkillError(f"the source is {width}x{height}; icons need a square source - crop.py or pad.py --aspect 1:1 first")
    largest = max(ico + pngs + [args.apple_size])
    if largest > width:
        raise ImageSkillError(
            f"the source is {width}x{width} but the largest icon requested is {largest}; icons are never upscaled - "
            "use a larger source or smaller sizes"
        )

    out_dir = os.path.abspath(args.output_dir)
    parent = os.path.dirname(out_dir)
    if not os.path.isdir(parent):
        raise ImageSkillError(f"parent directory does not exist: {parent}")
    plan = [("favicon.ico", "favicon", ico,
             [magick, args.input, "-auto-orient", "-define", f"icon:auto-resize={','.join(map(str, ico))}"])]
    for size in pngs:
        plan.append((f"icon-{size}x{size}.png", "png icon", [size],
                     [magick, args.input, "-auto-orient", "-resize", f"{size}x{size}"]))
    if args.apple_size:
        flatten = ["-background", args.apple_background, "-alpha", "remove", "-alpha", "off"] if args.apple_background else []
        plan.append(("apple-touch-icon.png", "apple-touch-icon", [args.apple_size],
                     [magick, args.input, "-auto-orient", "-resize", f"{args.apple_size}x{args.apple_size}"] + flatten))
    for name, _, _, cmd in plan:
        path = os.path.join(out_dir, name)
        check_output_not_input(args.input, path)
        check_output_not_exists(path, allow_overwrite=args.overwrite)
        cmd.append(path)

    if args.dry_run:
        return {"dry_run": True, "would_run": [cmd for _, _, _, cmd in plan]}

    os.makedirs(out_dir, exist_ok=True)
    files = []
    for name, purpose, sizes, cmd in plan:
        path = cmd[-1]
        run(cmd)
        verify_output_format(path, backend)
        frames = run([magick, "identify", "-format", "%w %h\n", path])["stdout"].split("\n")
        got = sorted({tuple(int(v) for v in f.split()) for f in frames if f.strip()}, reverse=True)
        want = sorted({(s, s) for s in sizes}, reverse=True)
        if got != want:
            raise ImageSkillError(f"{name} holds sizes {got}, expected {want}")
        files.append({"path": path, "purpose": purpose, "sizes": sizes, "format": "ICO" if name.endswith(".ico") else "PNG"})

    notes = []
    if args.apple_size and has_alpha and not args.apple_background:
        notes.append("apple-touch-icon.png keeps the source's transparency; iOS shows it on black - "
                     "pass --apple-background to flatten it")
    html = ['<link rel="icon" href="/favicon.ico" sizes="{}">'.format(" ".join(f"{s}x{s}" for s in sorted(ico)))]
    html += [f'<link rel="icon" type="image/png" sizes="{s}x{s}" href="/icon-{s}x{s}.png">' for s in sorted(pngs) if s <= 96]
    if args.apple_size:
        html.append('<link rel="apple-touch-icon" href="/apple-touch-icon.png">')
    manifest = [{"src": f"/icon-{s}x{s}.png", "sizes": f"{s}x{s}", "type": "image/png"} for s in sorted(pngs) if s >= 192]
    payload = {
        "input": args.input,
        "output_dir": out_dir,
        "files": files,
        "html": html,
        "manifest_icons": manifest,
        "backend": backend,
    }
    if notes:
        payload["notes"] = notes
    return payload


def main(argv=None):
    as_json = wants_json(argv)
    try:
        args = build_parser().parse_args(argv)
        payload = run_tool(run_icons, args)
    except ImageSkillError as e:
        fail_error(e, as_json)
        return
    succeed(payload, args.json)


if __name__ == "__main__":
    main()
