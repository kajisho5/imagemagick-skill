#!/usr/bin/env python3
"""pad.py - add margins so an image reaches an aspect ratio (--aspect W:H) or an exact
canvas (--width --height), filled with --color ("none" for transparent). The image is
never scaled or cropped: a canvas smaller than the image is refused - resize first.

--color is required (there is no default fill). A transparent fill into a format with
no alpha channel (JPEG, BMP) is refused instead of silently turning black or white.

sips covers --gravity center with a #RRGGBB colour; anything else needs ImageMagick.
"""
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (  # noqa: E402
    ALPHA_CAPABLE_EXTS,
    GRAVITIES,
    ImageSkillError,
    JSONArgumentParser,
    add_output_args,
    color_arg,
    color_is_transparent,
    ext_of,
    finish_output,
    gravity_offset,
    identify_dims,
    oriented_dims,
    positive_int,
    prepare_output,
    ratio_arg,
    require_input,
    run,
    select_backend,
    succeed,
    wants_json,
    run_tool,
    fail_error,
)


def build_parser():
    parser = JSONArgumentParser(description="Pad an image to an aspect ratio or canvas size without scaling it")
    parser.add_argument("input", help="image file to read (never modified)")
    add_output_args(parser)
    parser.add_argument("--aspect", type=ratio_arg, help="pad to the smallest W:H canvas that holds the image, e.g. 1:1 or 16:9")
    parser.add_argument("--width", type=positive_int, help="exact canvas width in pixels (with --height)")
    parser.add_argument("--height", type=positive_int, help="exact canvas height in pixels (with --width)")
    parser.add_argument("--color", type=color_arg, required=True,
                        help="fill colour: a name (white), #RRGGBB, #RRGGBBAA, rgb()/rgba(), or none for transparent")
    parser.add_argument("--gravity", choices=GRAVITIES, default="center", help="where the image sits on the canvas (default center)")
    return parser


def aspect_canvas(width, height, ratio_w, ratio_h):
    """Smallest canvas of ratio_w:ratio_h that holds width x height."""
    target = ratio_w / ratio_h
    if width / height < target:
        return max(width, math.ceil(height * target)), height
    return width, max(height, math.ceil(width / target))


def pad_command(backend, binary, input_path, output_path, in_dims, canvas, color, gravity):
    """(argv, (x, y)) that places an in_dims image on a canvas-sized fill."""
    (in_w, in_h), (canvas_w, canvas_h) = in_dims, canvas
    x, y = gravity_offset(gravity, canvas_w, canvas_h, in_w, in_h)
    if backend == "magick":
        # An explicit offset rather than -gravity: the position reported is then exactly
        # the one ImageMagick used.
        cmd = [binary, input_path, "-auto-orient", "-background", color, "-gravity", "northwest",
               "-extent", f"{canvas_w}x{canvas_h}-{x}-{y}", output_path]
    else:
        cmd = [binary, "--padToHeightWidth", str(canvas_h), str(canvas_w), "--padColor", color.lstrip("#").upper(),
               input_path, "--out", output_path]
    return cmd, (x, y)


def run_pad(args):
    require_input(args.input)
    prepare_output([args.input], args.output, args.overwrite)
    has_canvas = args.width is not None or args.height is not None
    if args.aspect and has_canvas:
        raise ImageSkillError("use either --aspect or --width/--height, not both")
    if not args.aspect and (args.width is None or args.height is None):
        raise ImageSkillError("give --aspect W:H, or both --width and --height")
    transparent = color_is_transparent(args.color)
    if transparent and ext_of(args.output) not in ALPHA_CAPABLE_EXTS:
        raise ImageSkillError(
            f".{ext_of(args.output)} has no alpha channel, so a transparent --color would not stay transparent; "
            "write PNG/WebP or pick an opaque colour"
        )

    sips_ok = True if args.gravity == "center" and re.fullmatch(r"#[0-9a-fA-F]{6}", args.color) else (
        "sips can only pad around the centre with a #RRGGBB colour"
    )
    backend, binary = select_backend(sips_ok)
    in_w, in_h = oriented_dims(args.input)
    if args.aspect:
        canvas_w, canvas_h = aspect_canvas(in_w, in_h, args.aspect[0], args.aspect[1])
    else:
        canvas_w, canvas_h = args.width, args.height
        if canvas_w < in_w or canvas_h < in_h:
            raise ImageSkillError(
                f"canvas {canvas_w}x{canvas_h} is smaller than the {in_w}x{in_h} image; pad never shrinks - resize first"
            )
    cmd, (x, y) = pad_command(backend, binary, args.input, args.output, (in_w, in_h), (canvas_w, canvas_h),
                              args.color, args.gravity)
    run(cmd, dry_run=args.dry_run)
    if args.dry_run:
        return {"dry_run": True, "would_run": cmd}

    finish_output(args.output, backend)
    out_w, out_h = identify_dims(args.output)
    if (out_w, out_h) != (canvas_w, canvas_h):
        raise ImageSkillError(f"pad produced {out_w}x{out_h}, expected {canvas_w}x{canvas_h}")
    return {
        "input": args.input,
        "output": args.output,
        "mode": "aspect" if args.aspect else "canvas",
        "color": args.color,
        "original": {"width": in_w, "height": in_h},
        "offset": {"x": x, "y": y} if backend == "magick" else None,
        "actual": {"width": out_w, "height": out_h},
        "backend": backend,
    }


def main(argv=None):
    as_json = wants_json(argv)
    try:
        args = build_parser().parse_args(argv)
        payload = run_tool(run_pad, args)
    except ImageSkillError as e:
        fail_error(e, as_json)
        return
    succeed(payload, args.json)


if __name__ == "__main__":
    main()
