#!/usr/bin/env python3
"""thumb.py - create a thumbnail sized by its longest edge, preserving aspect ratio.
Never upscales past the source size."""
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
    which_sips,
    add_timeout_arg,
    run_tool,
    fail_error,
)


def build_parser():
    parser = JSONArgumentParser(description="Create a thumbnail sized by its longest edge")
    parser.add_argument("input", help="image file to read (never modified)")
    parser.add_argument("-o", "--output", required=True, help="file to write; must differ from the input, extension picks the format")
    parser.add_argument("--long-edge", type=int, required=True, help="target size of the longer side, in pixels")
    parser.add_argument("--quality", type=int, default=None, help="0-100 encoder quality for lossy formats (JPEG/WebP)")
    parser.add_argument("--overwrite", action="store_true", help="allow replacing an existing output file")
    parser.add_argument("--json", action="store_true", help="print one JSON object (ok:true/false) instead of text")
    parser.add_argument("--dry-run", action="store_true", help="print the backend command that would run, write nothing")
    add_timeout_arg(parser)
    return parser


def run_thumb(args):
    if not os.path.isfile(args.input):
        raise ImageSkillError(f"input not found: {args.input}")
    if args.long_edge <= 0:
        raise ImageSkillError("--long-edge must be positive")
    check_output_not_input(args.input, args.output)
    check_output_not_exists(args.output, allow_overwrite=args.overwrite)

    magick = which_magick()
    sips = which_sips()
    edge = str(args.long_edge)

    if magick:
        backend = "magick"
        cmd = [magick, args.input, "-auto-orient", "-resize", f"{edge}x{edge}>"]
        if args.quality is not None:
            cmd += ["-quality", str(args.quality)]
        cmd.append(args.output)
    elif sips:
        backend = "sips"
        cmd = [sips, "-Z", edge, args.input, "--out", args.output]
    else:
        raise ImageSkillError("no usable backend: install ImageMagick (magick) or, on macOS, use sips")

    run(cmd, dry_run=args.dry_run)
    if args.dry_run:
        return {"dry_run": True, "would_run": cmd}

    if not os.path.isfile(args.output):
        raise ImageSkillError("thumbnail reported success but output file is missing")
    verify_output_format(args.output, backend)

    out_w, out_h = identify_dims(args.output)
    if max(out_w, out_h) > args.long_edge:
        raise ImageSkillError(
            f"thumbnail exceeded requested long edge {args.long_edge}, got {out_w}x{out_h}"
        )

    return {
        "input": args.input,
        "output": args.output,
        "long_edge": args.long_edge,
        "actual": {"width": out_w, "height": out_h},
        "backend": backend,
    }


def main(argv=None):
    as_json = wants_json(argv)
    try:
        args = build_parser().parse_args(argv)
        payload = run_tool(run_thumb, args)
    except ImageSkillError as e:
        fail_error(e, as_json)
        return
    succeed(payload, args.json)


if __name__ == "__main__":
    main()
