#!/usr/bin/env python3
"""crop.py - cut a region out of an image: an exact pixel rectangle (--x --y --width
--height), or the largest region of a given aspect ratio (--aspect W:H) placed by
--gravity. Coordinates refer to the image as displayed (EXIF orientation applied).
A rectangle that reaches outside the image is refused, never silently clipped.

sips covers --aspect with --gravity center (sips crops around the centre); anything
else needs ImageMagick.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (  # noqa: E402
    GRAVITIES,
    ImageSkillError,
    JSONArgumentParser,
    add_output_args,
    finish_output,
    gravity_offset,
    identify_dims,
    non_negative_int,
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
    parser = JSONArgumentParser(description="Crop an image to a pixel rectangle or to an aspect ratio")
    parser.add_argument("input", help="image file to read (never modified)")
    add_output_args(parser)
    parser.add_argument("--x", type=non_negative_int, help="rectangle: left edge in pixels (with --y --width --height)")
    parser.add_argument("--y", type=non_negative_int, help="rectangle: top edge in pixels")
    parser.add_argument("--width", type=positive_int, help="rectangle: width in pixels")
    parser.add_argument("--height", type=positive_int, help="rectangle: height in pixels")
    parser.add_argument("--aspect", type=ratio_arg, help="crop the largest W:H region instead of a rectangle, e.g. 1:1 or 16:9")
    parser.add_argument("--gravity", choices=GRAVITIES, default="center", help="where the --aspect region sits (default center)")
    return parser


def aspect_box(width, height, ratio_w, ratio_h, gravity):
    """Largest box of ratio_w:ratio_h inside width x height, positioned by gravity."""
    target = ratio_w / ratio_h
    if width / height > target:
        box_h, box_w = height, max(1, round(height * target))
    else:
        box_w, box_h = width, max(1, round(width / target))
    box_w, box_h = min(box_w, width), min(box_h, height)
    x, y = gravity_offset(gravity, width, height, box_w, box_h)
    return x, y, box_w, box_h


def run_crop(args):
    require_input(args.input)
    prepare_output([args.input], args.output, args.overwrite)
    rect = [args.x, args.y, args.width, args.height]
    if args.aspect and any(v is not None for v in rect):
        raise ImageSkillError("use either --aspect or --x/--y/--width/--height, not both")
    if not args.aspect and any(v is None for v in rect):
        raise ImageSkillError("give --aspect W:H, or all four of --x --y --width --height")

    sips_ok = True if args.aspect and args.gravity == "center" else (
        "sips can only crop an --aspect region around the centre"
    )
    backend, binary = select_backend(sips_ok)
    in_w, in_h = oriented_dims(args.input)

    if args.aspect:
        x, y, w, h = aspect_box(in_w, in_h, args.aspect[0], args.aspect[1], args.gravity)
    else:
        x, y, w, h = rect
        if x + w > in_w or y + h > in_h:
            raise ImageSkillError(
                f"rectangle {w}x{h}+{x}+{y} reaches outside the {in_w}x{in_h} image; crop never clips silently"
            )

    if backend == "magick":
        cmd = [binary, args.input, "-auto-orient", "-crop", f"{w}x{h}+{x}+{y}", "+repage", args.output]
    else:
        cmd = [binary, "--cropToHeightWidth", str(h), str(w), args.input, "--out", args.output]
    run(cmd, dry_run=args.dry_run)
    if args.dry_run:
        return {"dry_run": True, "would_run": cmd}

    finish_output(args.output, backend)
    out_w, out_h = identify_dims(args.output)
    if (out_w, out_h) != (w, h):
        raise ImageSkillError(f"crop produced {out_w}x{out_h}, expected {w}x{h}")
    return {
        "input": args.input,
        "output": args.output,
        "mode": "aspect" if args.aspect else "rect",
        "box": {"x": x, "y": y, "width": w, "height": h},
        "original": {"width": in_w, "height": in_h},
        "actual": {"width": out_w, "height": out_h},
        "backend": backend,
    }


def main(argv=None):
    as_json = wants_json(argv)
    try:
        args = build_parser().parse_args(argv)
        payload = run_tool(run_crop, args)
    except ImageSkillError as e:
        fail_error(e, as_json)
        return
    succeed(payload, args.json)


if __name__ == "__main__":
    main()
