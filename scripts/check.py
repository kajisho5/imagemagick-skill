#!/usr/bin/env python3
"""check.py - verify a produced image actually opens, matches the promised dimensions/
format, and did not silently overwrite the original input."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (  # noqa: E402
    ImageSkillError,
    JSONArgumentParser,
    wants_json,
    identify_dims,
    run,
    succeed,
    which_magick,
    add_timeout_arg,
    run_tool,
    fail_error,
)


def build_parser():
    parser = JSONArgumentParser(description="Verify an image output file")
    parser.add_argument("output", help="the file to check")
    parser.add_argument("--input", help="original input path; fails if output resolves to this same path")
    parser.add_argument("--expect-width", type=int, help="fail unless the width is exactly this")
    parser.add_argument("--expect-height", type=int, help="fail unless the height is exactly this")
    parser.add_argument("--expect-max-width", type=int, help="fail if width exceeds this (for fit-mode results)")
    parser.add_argument("--expect-max-height", type=int, help="fail if height exceeds this (for fit-mode results)")
    parser.add_argument("--expect-format", help="expected format, e.g. WEBP, JPEG, PNG")
    parser.add_argument("--json", action="store_true", help="print one JSON object (ok:true/false) instead of text")
    add_timeout_arg(parser)
    return parser


def run_check(args):
    if not os.path.isfile(args.output):
        raise ImageSkillError(f"output not found: {args.output}")

    if args.input and os.path.realpath(args.input) == os.path.realpath(args.output):
        raise ImageSkillError("output path is the same file as --input: the original was overwritten")

    if os.path.getsize(args.output) == 0:
        raise ImageSkillError("output file is empty (0 bytes)")

    width, height = identify_dims(args.output)
    if width is None or height is None:
        raise ImageSkillError("output could not be opened/identified as an image")

    if args.expect_width is not None and width != args.expect_width:
        raise ImageSkillError(f"expected width {args.expect_width}, got {width}")
    if args.expect_height is not None and height != args.expect_height:
        raise ImageSkillError(f"expected height {args.expect_height}, got {height}")
    if args.expect_max_width is not None and width > args.expect_max_width:
        raise ImageSkillError(f"width {width} exceeds max {args.expect_max_width}")
    if args.expect_max_height is not None and height > args.expect_max_height:
        raise ImageSkillError(f"height {height} exceeds max {args.expect_max_height}")

    fmt = None
    if args.expect_format:
        magick = which_magick()
        if not magick:
            raise ImageSkillError(
                "--expect-format requires ImageMagick (magick) to read the format; sips fallback cannot verify it"
            )
        result = run([magick, "identify", "-format", "%m", args.output])
        fmt = result["stdout"].strip()
        if fmt.upper() != args.expect_format.upper():
            raise ImageSkillError(f"expected format {args.expect_format}, got {fmt}")

    return {"output": args.output, "width": width, "height": height, "format": fmt}


def main(argv=None):
    as_json = wants_json(argv)
    try:
        args = build_parser().parse_args(argv)
        payload = run_tool(run_check, args)
    except ImageSkillError as e:
        fail_error(e, as_json)
        return
    succeed(payload, args.json)


if __name__ == "__main__":
    main()
