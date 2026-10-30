#!/usr/bin/env python3
"""adjust.py - tone and detail adjustments with explicit values: --levels, --brightness,
--contrast, --saturation, --blur, --sharpen. Every value is an argument; nothing is
"auto" or "enhance" - how an image should look is the caller's decision.

Applied in a fixed order: levels, brightness/contrast, saturation, blur, sharpen.
Dimensions never change. ImageMagick only.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (  # noqa: E402
    ImageSkillError,
    JSONArgumentParser,
    add_output_args,
    finish_output,
    identify_dims,
    oriented_dims,
    prepare_output,
    require_input,
    run,
    select_backend,
    succeed,
    wants_json,
    run_tool,
    fail_error,
)


def build_parser():
    parser = JSONArgumentParser(description="Adjust levels, brightness, contrast, saturation, blur or sharpness")
    parser.add_argument("input", help="image file to read (never modified)")
    add_output_args(parser)
    parser.add_argument("--levels", help="BLACK,WHITE[,GAMMA]: input black and white points in percent (0-100) and "
                                          "optional gamma, e.g. 5,95 or 0,100,1.2")
    parser.add_argument("--brightness", type=float, help="-100 to 100 (0 = unchanged)")
    parser.add_argument("--contrast", type=float, help="-100 to 100 (0 = unchanged)")
    parser.add_argument("--saturation", type=float, help="percent of the current saturation, 0-400 (100 = unchanged, 0 = grey)")
    parser.add_argument("--blur", type=float, help="Gaussian blur sigma in pixels, 0.1-50")
    parser.add_argument("--sharpen", type=float, help="unsharp-mask sigma in pixels, 0.1-10")
    return parser


def _levels(value):
    m = re.fullmatch(r"\s*([0-9.]+)\s*,\s*([0-9.]+)\s*(?:,\s*([0-9.]+)\s*)?", value or "")
    if not m:
        raise ImageSkillError(f"--levels must be BLACK,WHITE[,GAMMA], got {value!r}")
    black, white = float(m.group(1)), float(m.group(2))
    gamma = float(m.group(3)) if m.group(3) else None
    if not (0 <= black < white <= 100):
        raise ImageSkillError("--levels needs 0 <= BLACK < WHITE <= 100")
    if gamma is not None and not (0.1 <= gamma <= 10):
        raise ImageSkillError("--levels gamma must be between 0.1 and 10")
    return black, white, gamma


def _check_range(name, value, low, high):
    if value is not None and not (low <= value <= high):
        raise ImageSkillError(f"--{name} must be between {low:g} and {high:g}, got {value:g}")


def run_adjust(args):
    require_input(args.input)
    prepare_output([args.input], args.output, args.overwrite)
    _check_range("brightness", args.brightness, -100, 100)
    _check_range("contrast", args.contrast, -100, 100)
    _check_range("saturation", args.saturation, 0, 400)
    _check_range("blur", args.blur, 0.1, 50)
    _check_range("sharpen", args.sharpen, 0.1, 10)
    if all(v is None for v in (args.levels, args.brightness, args.contrast, args.saturation, args.blur, args.sharpen)):
        raise ImageSkillError("nothing to do: give at least one of --levels --brightness --contrast --saturation --blur --sharpen")
    backend, magick = select_backend("sips has no tone or detail adjustments")

    ops = []
    cmd = [magick, args.input, "-auto-orient"]
    if args.levels:
        black, white, gamma = _levels(args.levels)
        cmd += ["-level", f"{black:g}%,{white:g}%" + (f",{gamma:g}" if gamma else "")]
        ops.append({"op": "levels", "black": black, "white": white, "gamma": gamma})
    if args.brightness is not None or args.contrast is not None:
        b, c = args.brightness or 0.0, args.contrast or 0.0
        cmd += ["-brightness-contrast", f"{b:g}x{c:g}"]
        ops.append({"op": "brightness-contrast", "brightness": b, "contrast": c})
    if args.saturation is not None:
        cmd += ["-modulate", f"100,{args.saturation:g},100"]
        ops.append({"op": "saturation", "percent": args.saturation})
    if args.blur is not None:
        cmd += ["-blur", f"0x{args.blur:g}"]
        ops.append({"op": "blur", "sigma": args.blur})
    if args.sharpen is not None:
        cmd += ["-unsharp", f"0x{args.sharpen:g}"]
        ops.append({"op": "sharpen", "sigma": args.sharpen})
    cmd.append(args.output)

    run(cmd, dry_run=args.dry_run)
    if args.dry_run:
        return {"dry_run": True, "would_run": cmd}
    finish_output(args.output, backend)
    in_dims, out_dims = oriented_dims(args.input), identify_dims(args.output)
    if tuple(out_dims) != tuple(in_dims):
        raise ImageSkillError(f"dimensions changed from {in_dims} to {out_dims}")
    return {
        "input": args.input,
        "output": args.output,
        "operations": ops,
        "actual": {"width": out_dims[0], "height": out_dims[1]},
        "backend": backend,
    }


def main(argv=None):
    as_json = wants_json(argv)
    try:
        args = build_parser().parse_args(argv)
        payload = run_tool(run_adjust, args)
    except ImageSkillError as e:
        fail_error(e, as_json)
        return
    succeed(payload, args.json)


if __name__ == "__main__":
    main()
