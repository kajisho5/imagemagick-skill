#!/usr/bin/env python3
"""rotate.py - rotate (clockwise --degrees), mirror (--flip-horizontal / --flip-vertical),
or just bake the EXIF orientation into the pixels (no other flag). EXIF orientation is
always applied first; then the rotation, then the flips.

An angle that is not a multiple of 90 enlarges the canvas, so it needs --background
for the new corners (there is no default fill).

sips covers a single operation - one multiple-of-90 rotation, or one flip - on an
image without EXIF orientation handling; anything else needs ImageMagick.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (  # noqa: E402
    ALPHA_CAPABLE_EXTS,
    ImageSkillError,
    JSONArgumentParser,
    add_output_args,
    color_arg,
    color_is_transparent,
    ext_of,
    finish_output,
    identify_dims,
    magick_info,
    oriented_dims,
    prepare_output,
    require_input,
    run,
    select_backend,
    succeed,
    wants_json,
    which_magick,
    run_tool,
    fail_error,
)


def build_parser():
    parser = JSONArgumentParser(description="Rotate, mirror, or bake EXIF orientation into an image")
    parser.add_argument("input", help="image file to read (never modified)")
    add_output_args(parser)
    parser.add_argument("--degrees", type=float, default=0.0, help="clockwise rotation in degrees (default 0)")
    parser.add_argument("--flip-horizontal", action="store_true", help="mirror left-right (after rotating)")
    parser.add_argument("--flip-vertical", action="store_true", help="mirror top-bottom (after rotating)")
    parser.add_argument("--background", type=color_arg,
                        help="fill for the corners a non-multiple-of-90 rotation exposes (required then), or none")
    return parser


def run_rotate(args):
    require_input(args.input)
    prepare_output([args.input], args.output, args.overwrite)
    degrees = args.degrees % 360
    right_angle = degrees % 90 == 0
    if not right_angle and not args.background:
        raise ImageSkillError(f"rotating by {args.degrees} degrees exposes new corners: pass --background (or none)")
    if args.background and color_is_transparent(args.background) and ext_of(args.output) not in ALPHA_CAPABLE_EXTS:
        raise ImageSkillError(f".{ext_of(args.output)} has no alpha channel for a transparent --background")

    ops = int(degrees != 0) + int(args.flip_horizontal) + int(args.flip_vertical)
    sips_ok = True if right_angle and ops == 1 else "sips handles exactly one 90-degree rotation or one flip"
    backend, binary = select_backend(sips_ok)

    orientation = None
    if backend == "magick":
        orientation = magick_info(binary, args.input, "%[orientation]", auto_orient=False).strip() or None
    in_w, in_h = oriented_dims(args.input)

    if backend == "magick":
        cmd = [binary, args.input, "-auto-orient"]
        if degrees:
            if not right_angle:
                cmd += ["-background", args.background]
            cmd += ["-rotate", f"{degrees:g}"]
        if args.flip_horizontal:
            cmd.append("-flop")
        if args.flip_vertical:
            cmd.append("-flip")
        cmd += ["+repage", args.output]
    else:
        if degrees:
            cmd = [binary, "-r", f"{degrees:g}", args.input, "--out", args.output]
        else:
            cmd = [binary, "-f", "horizontal" if args.flip_horizontal else "vertical", args.input, "--out", args.output]
    run(cmd, dry_run=args.dry_run)
    if args.dry_run:
        return {"dry_run": True, "would_run": cmd}

    finish_output(args.output, backend)
    out_w, out_h = identify_dims(args.output)
    if right_angle:
        expected = (in_h, in_w) if degrees in (90, 270) else (in_w, in_h)
        if (out_w, out_h) != expected:
            raise ImageSkillError(f"rotation produced {out_w}x{out_h}, expected {expected[0]}x{expected[1]}")
    return {
        "input": args.input,
        "output": args.output,
        "degrees": args.degrees,
        "flip_horizontal": args.flip_horizontal,
        "flip_vertical": args.flip_vertical,
        "orientation_before": orientation,
        "original": {"width": in_w, "height": in_h},
        "actual": {"width": out_w, "height": out_h},
        "backend": backend,
    }


def main(argv=None):
    as_json = wants_json(argv)
    try:
        args = build_parser().parse_args(argv)
        payload = run_tool(run_rotate, args)
    except ImageSkillError as e:
        fail_error(e, as_json)
        return
    succeed(payload, args.json)


if __name__ == "__main__":
    main()
