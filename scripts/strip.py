#!/usr/bin/env python3
"""strip.py - remove GPS and personal EXIF metadata. Applies orientation first so the
image doesn't end up sideways once the orientation tag is gone.

magick only: sips has no reliable blanket metadata-strip flag, so this tool
reports ok:false with a clear reason when only sips is available (see doctor).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (  # noqa: E402
    ImageSkillError,
    JSONArgumentParser,
    image_has_gps,
    wants_json,
    check_output_not_exists,
    check_output_not_input,
    run,
    succeed,
    verify_output_format,
    which_magick,
    add_timeout_arg,
    run_tool,
    fail_error,
)


def build_parser():
    parser = JSONArgumentParser(description="Strip GPS/EXIF metadata from an image")
    parser.add_argument("input", help="image file to read (never modified)")
    parser.add_argument("-o", "--output", required=True, help="file to write; must differ from the input, extension picks the format")
    parser.add_argument("--overwrite", action="store_true", help="allow replacing an existing output file")
    parser.add_argument("--json", action="store_true", help="print one JSON object (ok:true/false) instead of text")
    parser.add_argument("--dry-run", action="store_true", help="print the backend command that would run, write nothing")
    add_timeout_arg(parser)
    return parser


def run_strip(args):
    if not os.path.isfile(args.input):
        raise ImageSkillError(f"input not found: {args.input}")
    check_output_not_input(args.input, args.output)
    check_output_not_exists(args.output, allow_overwrite=args.overwrite)

    magick = which_magick()
    if not magick:
        raise ImageSkillError(
            "strip requires ImageMagick (magick); sips has no reliable blanket EXIF-strip flag"
        )

    cmd = [magick, args.input, "-auto-orient", "-strip", args.output]
    run(cmd, dry_run=args.dry_run)
    if args.dry_run:
        return {"dry_run": True, "would_run": cmd}

    if not os.path.isfile(args.output):
        raise ImageSkillError("strip reported success but output file is missing")
    verify_output_format(args.output, "magick")

    if image_has_gps(magick, args.output) is not False:
        os.remove(args.output)
        raise ImageSkillError("output still contains GPS data (or an unreadable EXIF block) after strip")

    return {"input": args.input, "output": args.output, "has_gps": False, "backend": "magick"}


def main(argv=None):
    as_json = wants_json(argv)
    try:
        args = build_parser().parse_args(argv)
        payload = run_tool(run_strip, args)
    except ImageSkillError as e:
        fail_error(e, as_json)
        return
    succeed(payload, args.json)


if __name__ == "__main__":
    main()
