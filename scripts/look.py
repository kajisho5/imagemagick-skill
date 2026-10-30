#!/usr/bin/env python3
"""look.py - make a preview sheet an agent can open to *see* images: every input shrunk
into a labelled tile (file name, size, format), transparency shown as a checkerboard.
--pair lays two images side by side as before/after. Inputs are only read.

The sheet is for inspection, not a deliverable - so it has defaults (tile size,
columns) where the editing tools deliberately have none.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (  # noqa: E402
    ImageSkillError,
    JSONArgumentParser,
    add_output_args,
    finish_output,
    identify_dims,
    magick_info,
    positive_int,
    prepare_output,
    require_input,
    run,
    select_backend,
    succeed,
    wants_json,
    find_fonts,
    run_tool,
    fail_error,
)
from _grid import grid_command, grid_shape, sheet_size  # noqa: E402

LABEL_HEIGHT = 22


def build_parser():
    parser = JSONArgumentParser(description="Make a labelled preview sheet of one or more images to look at")
    parser.add_argument("inputs", nargs="+", help="images to preview (only read; first frame of multi-frame files)")
    add_output_args(parser, output_help="sheet to write (e.g. look.png); must not be one of the inputs")
    parser.add_argument("--tile", type=positive_int, default=320, help="longest side of each preview tile in pixels (default 320)")
    parser.add_argument("--cols", type=positive_int, default=None, help="tiles per row (default: up to 4)")
    parser.add_argument("--pair", action="store_true", help="exactly two inputs shown side by side as before / after")
    parser.add_argument("--no-labels", action="store_true", help="omit the file name / size / format caption under each tile")
    return parser


def _describe(magick, path):
    width, height, fmt, alpha = magick_info(magick, path, "%w|%h|%m|%A").strip().split("|")
    return {
        "path": path,
        "width": int(width),
        "height": int(height),
        "format": fmt,
        "has_alpha": alpha.strip().lower() not in ("false", "undefined", ""),
    }


def run_look(args):
    for path in args.inputs:
        require_input(path)
    if args.pair and len(args.inputs) != 2:
        raise ImageSkillError(f"--pair needs exactly two inputs (before, after), got {len(args.inputs)}")
    prepare_output(args.inputs, args.output, args.overwrite)
    backend, magick = select_backend("sips cannot compose a preview sheet")

    infos = [_describe(magick, p) for p in args.inputs]
    cols = 2 if args.pair else (args.cols or min(len(infos), 4))
    cols, rows = grid_shape(len(infos), cols)

    note = None
    labels = None
    font = None
    if not args.no_labels:
        font = find_fonts()["default"]
        if font:
            labels = []
            for i, info in enumerate(infos):
                prefix = ("before: " if i == 0 else "after: ") if args.pair else ""
                alpha = " alpha" if info["has_alpha"] else ""
                labels.append(f"{prefix}{os.path.basename(info['path'])}  {info['width']}x{info['height']} {info['format']}{alpha}")
        else:
            note = "no font found, so tiles are unlabelled (doctor --json lists fonts)"
    label_h = LABEL_HEIGHT if labels else 0

    cmd = grid_command(magick, args.inputs, args.output, cols, args.tile, args.tile, "#e6e6e6", gap=8,
                       checker=True, shrink_only=True, labels=labels, font=font, label_h=label_h)
    run(cmd, dry_run=args.dry_run)
    if args.dry_run:
        return {"dry_run": True, "would_run": cmd}

    finish_output(args.output, backend)
    expected = sheet_size(len(infos), cols, args.tile, args.tile, 8, label_h)
    actual = identify_dims(args.output)
    if tuple(actual) != expected:
        raise ImageSkillError(f"sheet came out {actual[0]}x{actual[1]}, expected {expected[0]}x{expected[1]}")

    payload = {
        "output": args.output,
        "mode": "pair" if args.pair else "grid",
        "inputs": infos,
        "tile": args.tile,
        "cols": cols,
        "rows": rows,
        "labels": bool(labels),
        "actual": {"width": actual[0], "height": actual[1]},
        "backend": backend,
    }
    if note:
        payload["note"] = note
    return payload


def main(argv=None):
    as_json = wants_json(argv)
    try:
        args = build_parser().parse_args(argv)
        payload = run_tool(run_look, args)
    except ImageSkillError as e:
        fail_error(e, as_json)
        return
    succeed(payload, args.json)


if __name__ == "__main__":
    main()
