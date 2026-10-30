#!/usr/bin/env python3
"""montage.py - compose several images into one: a row (default), or a grid with --cols,
with an optional gap and captions. Each image sits centred in a cell; cells are the size
of the largest input, or --cell-width x --cell-height with larger images shrunk to fit
(never enlarged). --background (required) fills gaps and letterboxing; "none" keeps
them transparent (refused for JPEG). ImageMagick only.

Unlike look.py (a preview for the agent), this writes a deliverable - e.g. a README
comparison strip - so nothing about its look is defaulted except the layout.
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
    non_negative_int,
    oriented_dims,
    positive_int,
    prepare_output,
    require_input,
    resolve_font,
    run,
    select_backend,
    succeed,
    wants_json,
    run_tool,
    fail_error,
)
from _grid import grid_command, grid_shape, sheet_size  # noqa: E402

LABEL_HEIGHT = 28


def build_parser():
    parser = JSONArgumentParser(description="Compose several images into a row or a grid")
    parser.add_argument("inputs", nargs="+", help="images in reading order (only read; first frame of multi-frame files)")
    add_output_args(parser, output_help="composite to write; must not be one of the inputs")
    parser.add_argument("--cols", type=positive_int, help="images per row (default: all in one row)")
    parser.add_argument("--cell-width", type=positive_int, help="cell width in pixels (with --cell-height; default: widest input)")
    parser.add_argument("--cell-height", type=positive_int, help="cell height in pixels (with --cell-width; default: tallest input)")
    parser.add_argument("--gap", type=non_negative_int, default=0, help="space between cells in pixels (default 0)")
    parser.add_argument("--background", type=color_arg, required=True,
                        help="colour for gaps and letterboxing, or none for transparent")
    parser.add_argument("--labels", action="store_true", help="caption each cell with its file name")
    parser.add_argument("--font", help="--labels only: font file instead of the one doctor reports")
    return parser


def run_montage(args):
    for path in args.inputs:
        require_input(path)
    prepare_output(args.inputs, args.output, args.overwrite)
    if (args.cell_width is None) != (args.cell_height is None):
        raise ImageSkillError("give both --cell-width and --cell-height, or neither")
    if color_is_transparent(args.background) and ext_of(args.output) not in ALPHA_CAPABLE_EXTS:
        raise ImageSkillError(f".{ext_of(args.output)} has no alpha channel for a transparent --background")
    if args.font and not args.labels:
        raise ImageSkillError("--font applies to --labels only")
    backend, magick = select_backend("sips cannot compose images")

    dims = [oriented_dims(p) for p in args.inputs]
    cell_w = args.cell_width or max(w for w, _ in dims)
    cell_h = args.cell_height or max(h for _, h in dims)
    cols, rows = grid_shape(len(args.inputs), args.cols or len(args.inputs))
    labels = [os.path.basename(p) for p in args.inputs] if args.labels else None
    font = resolve_font(" ".join(labels), args.font) if labels else None
    label_h = LABEL_HEIGHT if labels else 0

    cmd = grid_command(magick, args.inputs, args.output, cols, cell_w, cell_h, args.background, gap=args.gap,
                       checker=False, shrink_only=True, labels=labels, font=font, label_h=label_h)
    run(cmd, dry_run=args.dry_run)
    if args.dry_run:
        return {"dry_run": True, "would_run": cmd}

    finish_output(args.output, backend)
    expected = sheet_size(len(args.inputs), cols, cell_w, cell_h, args.gap, label_h)
    actual = identify_dims(args.output)
    if tuple(actual) != expected:
        raise ImageSkillError(f"composite came out {actual[0]}x{actual[1]}, expected {expected[0]}x{expected[1]}")
    return {
        "inputs": [{"path": p, "width": w, "height": h} for p, (w, h) in zip(args.inputs, dims)],
        "output": args.output,
        "cols": cols,
        "rows": rows,
        "cell": {"width": cell_w, "height": cell_h},
        "gap": args.gap,
        "background": args.background,
        "labels": bool(labels),
        "font": font,
        "actual": {"width": actual[0], "height": actual[1]},
        "backend": backend,
    }


def main(argv=None):
    as_json = wants_json(argv)
    try:
        args = build_parser().parse_args(argv)
        payload = run_tool(run_montage, args)
    except ImageSkillError as e:
        fail_error(e, as_json)
        return
    succeed(payload, args.json)


if __name__ == "__main__":
    main()
