#!/usr/bin/env python3
"""trim.py - trim a solid-color border. Refuses the result if it looks over-trimmed
(more than --max-trim-percent of the original area removed), since that usually means
the image wasn't a simple bordered image and --fuzz needs adjusting.

magick only: sips has no border-detection/trim support.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (  # noqa: E402
    ImageSkillError,
    JSONArgumentParser,
    wants_json,
    check_output_not_exists,
    check_output_not_input,
    identify_dims,
    run,
    succeed,
    verify_output_format,
    which_magick,
    add_timeout_arg,
    run_tool,
    fail_error,
)


def build_parser():
    parser = JSONArgumentParser(description="Trim a solid-color border from an image")
    parser.add_argument("input", help="image file to read (never modified)")
    parser.add_argument("-o", "--output", required=True, help="file to write; must differ from the input, extension picks the format")
    parser.add_argument("--fuzz", type=float, default=2.0, help="color similarity tolerance, percent (default 2.0)")
    parser.add_argument(
        "--max-trim-percent",
        type=float,
        default=90.0,
        help="fail if more than this percent of the area is removed (default 90.0)",
    )
    parser.add_argument("--overwrite", action="store_true", help="allow replacing an existing output file")
    parser.add_argument("--json", action="store_true", help="print one JSON object (ok:true/false) instead of text")
    parser.add_argument("--dry-run", action="store_true", help="print the backend command that would run, write nothing")
    add_timeout_arg(parser)
    return parser


def run_trim(args):
    if not os.path.isfile(args.input):
        raise ImageSkillError(f"input not found: {args.input}")
    check_output_not_input(args.input, args.output)
    check_output_not_exists(args.output, allow_overwrite=args.overwrite)

    magick = which_magick()
    if not magick:
        raise ImageSkillError("trim requires ImageMagick (magick); sips has no trim/border-detection support")

    in_w, in_h = identify_dims(args.input)

    cmd = [magick, args.input, "-auto-orient", "-fuzz", f"{args.fuzz}%", "-trim", "+repage", args.output]
    run(cmd, dry_run=args.dry_run)
    if args.dry_run:
        return {"dry_run": True, "would_run": cmd}

    if not os.path.isfile(args.output):
        raise ImageSkillError("trim reported success but output file is missing")
    verify_output_format(args.output, "magick")

    out_w, out_h = identify_dims(args.output)
    in_area = in_w * in_h
    out_area = out_w * out_h
    removed_percent = 100.0 * (1 - (out_area / in_area)) if in_area else 0.0

    if removed_percent > args.max_trim_percent:
        os.remove(args.output)
        raise ImageSkillError(
            f"trim removed {removed_percent:.1f}% of the image area, over the {args.max_trim_percent}% limit "
            "(likely not a simple solid-color border; try a smaller --fuzz)"
        )
    if out_w <= 0 or out_h <= 0:
        raise ImageSkillError("trim produced an empty image")

    return {
        "input": args.input,
        "output": args.output,
        "original": {"width": in_w, "height": in_h},
        "trimmed": {"width": out_w, "height": out_h},
        "removed_percent": round(removed_percent, 1),
        "backend": "magick",
    }


def main(argv=None):
    as_json = wants_json(argv)
    try:
        args = build_parser().parse_args(argv)
        payload = run_tool(run_trim, args)
    except ImageSkillError as e:
        fail_error(e, as_json)
        return
    succeed(payload, args.json)


if __name__ == "__main__":
    main()
