#!/usr/bin/env python3
"""resize.py - resize an image using fit (default, no distortion), fill (crop to
cover), or exact (force size, may distort). Verifies the output dimensions against
what was promised before reporting success."""
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
    parser = JSONArgumentParser(description="Resize an image (fit, fill, or exact)")
    parser.add_argument("input", help="image file to read (never modified)")
    parser.add_argument("-o", "--output", required=True, help="file to write; must differ from the input, extension picks the format")
    parser.add_argument("--width", type=int, required=True, help="target width in pixels (the box width for fit)")
    parser.add_argument("--height", type=int, required=True, help="target height in pixels (the box height for fit)")
    parser.add_argument(
        "--mode",
        choices=["fit", "fill", "exact"],
        default="fit",
        help="fit: inside the box, no distortion; fill: cover the box and center-crop; exact: force the size",
    )
    parser.add_argument("--quality", type=int, default=None, help="0-100 encoder quality for lossy formats (JPEG/WebP)")
    parser.add_argument("--overwrite", action="store_true", help="allow replacing an existing output file")
    parser.add_argument("--json", action="store_true", help="print one JSON object (ok:true/false) instead of text")
    parser.add_argument("--dry-run", action="store_true", help="print the backend command that would run, write nothing")
    add_timeout_arg(parser)
    return parser


def _sips_fit_dims(in_w, in_h, box_w, box_h):
    """Compute the size that fits within box_w x box_h while preserving the source
    aspect ratio. sips has no single flag for a two-dimensional box fit - its `-Z`
    only constrains the longest edge, which overflows the other dimension whenever
    the box isn't square (e.g. a tall image into a wide box). The size is computed
    here instead, then sips is told to produce that exact size with `-z`."""
    scale = min(box_w / in_w, box_h / in_h)
    new_w = max(1, round(in_w * scale))
    new_h = max(1, round(in_h * scale))
    return new_w, new_h


def _build_cmd(backend, backend_bin, input_path, output_path, width, height, mode, quality):
    box = f"{width}x{height}"

    if backend == "magick":
        cmd = [backend_bin, input_path, "-auto-orient"]
        if mode == "fit":
            cmd += ["-resize", box]
        elif mode == "fill":
            cmd += ["-resize", f"{box}^", "-gravity", "center", "-extent", box]
        else:  # exact
            cmd += ["-resize", f"{box}!"]
        if quality is not None:
            cmd += ["-quality", str(quality)]
        cmd.append(output_path)
        return cmd

    # sips
    if mode != "fit":
        raise ImageSkillError(
            f"sips backend only supports resize mode 'fit' (got '{mode}'); install ImageMagick for fill/exact"
        )
    in_w, in_h = identify_dims(input_path)
    if not in_w or not in_h:
        raise ImageSkillError("could not read source dimensions for sips fit")
    new_w, new_h = _sips_fit_dims(in_w, in_h, width, height)
    return [backend_bin, "-z", str(new_h), str(new_w), input_path, "--out", output_path]


def _verify_dims(output_path, width, height, mode):
    out_w, out_h = identify_dims(output_path)
    if out_w is None or out_h is None:
        raise ImageSkillError("could not read dimensions of the output file")

    if mode in ("fill", "exact"):
        if (out_w, out_h) != (width, height):
            raise ImageSkillError(
                f"{mode} resize did not produce {width}x{height}, got {out_w}x{out_h}"
            )
    else:  # fit
        if out_w > width or out_h > height:
            raise ImageSkillError(
                f"fit resize exceeded {width}x{height} box, got {out_w}x{out_h}"
            )

    return out_w, out_h


def run_resize(args):
    if not os.path.isfile(args.input):
        raise ImageSkillError(f"input not found: {args.input}")
    if args.width <= 0 or args.height <= 0:
        raise ImageSkillError("--width and --height must be positive")
    check_output_not_input(args.input, args.output)
    check_output_not_exists(args.output, allow_overwrite=args.overwrite)

    magick = which_magick()
    sips = which_sips()
    if magick:
        backend, backend_bin = "magick", magick
    elif sips:
        backend, backend_bin = "sips", sips
    else:
        raise ImageSkillError("no usable backend: install ImageMagick (magick) or, on macOS, use sips")

    cmd = _build_cmd(backend, backend_bin, args.input, args.output, args.width, args.height, args.mode, args.quality)
    run(cmd, dry_run=args.dry_run)
    if args.dry_run:
        return {"dry_run": True, "would_run": cmd}

    if not os.path.isfile(args.output):
        raise ImageSkillError("resize reported success but output file is missing")
    verify_output_format(args.output, backend)

    out_w, out_h = _verify_dims(args.output, args.width, args.height, args.mode)

    return {
        "input": args.input,
        "output": args.output,
        "mode": args.mode,
        "requested": {"width": args.width, "height": args.height},
        "actual": {"width": out_w, "height": out_h},
        "backend": backend,
    }


def main(argv=None):
    as_json = wants_json(argv)
    try:
        args = build_parser().parse_args(argv)
        payload = run_tool(run_resize, args)
    except ImageSkillError as e:
        fail_error(e, as_json)
        return
    succeed(payload, args.json)


if __name__ == "__main__":
    main()
