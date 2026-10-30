#!/usr/bin/env python3
"""probe.py - inspect an image and report width, height, format, colorspace, alpha,
and GPS presence as JSON.

magick is the primary backend and reports every field. sips (macOS) can only
report width/height/format; colorspace/has_alpha/has_gps come back as null
with a note.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (  # noqa: E402
    ImageSkillError,
    JSONArgumentParser,
    image_has_gps,
    wants_json,
    run,
    succeed,
    which_magick,
    which_sips,
    add_timeout_arg,
    run_tool,
    fail_error,
)


def build_parser():
    parser = JSONArgumentParser(
        description="Probe an image: dimensions, format, colorspace, alpha, GPS presence"
    )
    parser.add_argument("input", help="image file to read (never modified)")
    parser.add_argument("--json", action="store_true", help="print one JSON object (ok:true/false) instead of text")
    parser.add_argument("--dry-run", action="store_true", help="print the backend command that would run, write nothing")
    add_timeout_arg(parser)
    return parser


def _probe_with_magick(magick, path, dry_run):
    cmd = [magick, "identify", "-format", "%w|%h|%m|%[colorspace]|%A\n", path]
    if dry_run:
        return {"dry_run": True, "command": cmd}

    result = run(cmd)
    line = result["stdout"].strip().splitlines()[0]
    width, height, fmt, colorspace, alpha = line.split("|")

    has_gps = image_has_gps(magick, path)

    payload = {
        "width": int(width),
        "height": int(height),
        "format": fmt,
        "colorspace": colorspace,
        "has_alpha": alpha.strip() == "True",
        "has_gps": has_gps,
        "backend": "magick",
    }
    if has_gps is None:
        payload["note"] = "the file has an EXIF block this tool could not parse; GPS presence is unknown - strip it to be safe"
    return payload


def _probe_with_sips(sips, path, dry_run):
    cmd = [sips, "-g", "pixelWidth", "-g", "pixelHeight", "-g", "format", path]
    if dry_run:
        return {"dry_run": True, "command": cmd}

    result = run(cmd)
    width = height = fmt = None
    for line in result["stdout"].splitlines():
        line = line.strip()
        if line.startswith("pixelWidth:"):
            width = int(line.split(":", 1)[1].strip())
        elif line.startswith("pixelHeight:"):
            height = int(line.split(":", 1)[1].strip())
        elif line.startswith("format:"):
            fmt = line.split(":", 1)[1].strip()

    return {
        "width": width,
        "height": height,
        "format": fmt,
        "colorspace": None,
        "has_alpha": None,
        "has_gps": None,
        "backend": "sips",
        "note": "sips backend: colorspace/has_alpha/has_gps are unavailable; install ImageMagick for full probe",
    }


def run_probe(args):
    if not os.path.isfile(args.input):
        raise ImageSkillError(f"input not found: {args.input}")

    magick = which_magick()
    sips = which_sips()

    if magick:
        payload = _probe_with_magick(magick, args.input, args.dry_run)
    elif sips:
        payload = _probe_with_sips(sips, args.input, args.dry_run)
    else:
        raise ImageSkillError("no usable backend: install ImageMagick (magick) or, on macOS, use sips")

    if args.dry_run:
        return {"dry_run": True, "would_run": payload["command"]}

    payload["input"] = args.input
    return payload


def main(argv=None):
    as_json = wants_json(argv)
    try:
        args = build_parser().parse_args(argv)
        payload = run_tool(run_probe, args)
    except ImageSkillError as e:
        fail_error(e, as_json)
        return
    succeed(payload, args.json)


if __name__ == "__main__":
    main()
