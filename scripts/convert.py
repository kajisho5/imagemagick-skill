#!/usr/bin/env python3
"""convert.py - convert an image to another format (e.g. HEIC -> JPEG/PNG/WebP,
PNG -> WebP) without touching the input."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (  # noqa: E402
    ImageSkillError,
    JSONArgumentParser,
    wants_json,
    check_output_not_exists,
    check_output_not_input,
    run,
    succeed,
    verify_output_format,
    which_magick,
    which_sips,
    add_timeout_arg,
    run_tool,
    fail_error,
)

SIPS_FORMATS = {"jpeg", "jpg", "png", "tiff", "tif", "bmp", "gif", "heic"}
SIPS_FORMAT_ALIASES = {"jpg": "jpeg", "tif": "tiff"}


def build_parser():
    parser = JSONArgumentParser(description="Convert an image to another format")
    parser.add_argument("input", help="image file to read (never modified)")
    parser.add_argument("-o", "--output", required=True, help="file to write; must differ from the input, extension picks the format")
    parser.add_argument("--quality", type=int, default=None, help="0-100 encoder quality for lossy formats (JPEG/WebP)")
    parser.add_argument("--overwrite", action="store_true", help="allow replacing an existing output file")
    parser.add_argument("--json", action="store_true", help="print one JSON object (ok:true/false) instead of text")
    parser.add_argument("--dry-run", action="store_true", help="print the backend command that would run, write nothing")
    add_timeout_arg(parser)
    return parser


def _ext_of(path):
    return os.path.splitext(path)[1].lstrip(".").lower()


def run_convert(args):
    if not os.path.isfile(args.input):
        raise ImageSkillError(f"input not found: {args.input}")
    check_output_not_input(args.input, args.output)
    check_output_not_exists(args.output, allow_overwrite=args.overwrite)

    magick = which_magick()
    sips = which_sips()
    out_ext = _ext_of(args.output)

    if magick:
        backend = "magick"
        cmd = [magick, args.input, "-auto-orient"]
        if args.quality is not None:
            cmd += ["-quality", str(args.quality)]
        cmd.append(args.output)
    elif sips:
        backend = "sips"
        if out_ext not in SIPS_FORMATS:
            raise ImageSkillError(
                f"sips backend cannot produce .{out_ext}; install ImageMagick for this format"
            )
        sips_format = SIPS_FORMAT_ALIASES.get(out_ext, out_ext)
        cmd = [sips, "-s", "format", sips_format, args.input, "--out", args.output]
    else:
        raise ImageSkillError("no usable backend: install ImageMagick (magick) or, on macOS, use sips")

    run(cmd, dry_run=args.dry_run)
    if args.dry_run:
        return {"dry_run": True, "would_run": cmd}

    if not os.path.isfile(args.output):
        raise ImageSkillError("conversion reported success but output file is missing")
    verify_output_format(args.output, backend)

    return {"input": args.input, "output": args.output, "backend": backend}


def main(argv=None):
    as_json = wants_json(argv)
    try:
        args = build_parser().parse_args(argv)
        payload = run_tool(run_convert, args)
    except ImageSkillError as e:
        fail_error(e, as_json)
        return
    succeed(payload, args.json)


if __name__ == "__main__":
    main()
