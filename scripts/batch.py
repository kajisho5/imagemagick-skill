#!/usr/bin/env python3
"""batch.py - run one imagemagick-skill tool over every image in a folder, writing to a
separate output folder. Never overwrites inputs or existing outputs; a single bad file
is recorded as a failure and the rest of the batch still runs.

  per-file tools (convert, resize, thumb, strip, trim, crop, pad, rotate, optimize,
      adjust, overlay, preset): one output per input, same name (extension from --ext)
  look, montage: one sheet of the whole folder, written as <tool>.<ext> (default png)
  icons: one icon folder per input, named after it
  compare: each file against the file of the same name in --against DIR; a heatmap
      per pair is written into the output folder
"""
import glob
import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (  # noqa: E402
    ImageSkillError,
    JSONArgumentParser,
    succeed,
    wants_json,
    add_timeout_arg,
    fail_error,
    run_tool,
    timeout_fields,
)

PER_FILE_TOOLS = ("convert", "resize", "thumb", "strip", "trim", "crop", "pad", "rotate", "optimize",
                  "adjust", "overlay", "preset")
AGGREGATE_TOOLS = ("look", "montage")
PAIRED_TOOLS = ("compare",)
DIR_TOOLS = ("icons",)
TOOL_MODULES = {name: name for name in PER_FILE_TOOLS + AGGREGATE_TOOLS + PAIRED_TOOLS + DIR_TOOLS}

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff", ".bmp", ".webp", ".gif"}


def build_parser():
    parser = JSONArgumentParser(
        description="Run an imagemagick-skill tool over every image in a folder",
        epilog="Extra args after -- are forwarded to the tool, e.g.: "
        "batch.py resize -i ./photos -o ./out --json -- --width 1200 --height 1200 --mode fit",
    )
    parser.add_argument("tool", choices=sorted(TOOL_MODULES), help="tool to run on each file")
    parser.add_argument("-i", "--input-dir", required=True, help="folder of images to read (not recursive)")
    parser.add_argument("-o", "--output-dir", required=True, help="folder to write results into; must differ from --input-dir")
    parser.add_argument("--ext", default=None,
                        help="output extension, e.g. webp: required for convert, optional for the other tools")
    parser.add_argument("--against", default=None,
                        help="compare only: folder holding the second image of each pair (matched by file name)")
    parser.add_argument("--json", action="store_true", help="print one JSON object (ok:true/false) instead of text")
    parser.add_argument("--dry-run", action="store_true", help="print the backend command that would run, write nothing")
    add_timeout_arg(parser, scope="each file's run (forwarded to the tool; a --timeout after -- wins)")
    return parser


def parse_args(argv=None):
    """Split argv on a literal '--' so per-file tool flags (e.g. --width) can't be
    confused with batch's own flags; argparse.REMAINDER does not do this reliably
    when optionals are interspersed before the '--'."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--" in argv:
        idx = argv.index("--")
        own_args, tool_args = argv[:idx], argv[idx + 1 :]
    else:
        own_args, tool_args = argv, []
    args = build_parser().parse_args(own_args)
    args.tool_args = tool_args
    return args


def run_batch(args):
    tool_args = args.tool_args

    in_dir = os.path.realpath(args.input_dir)
    out_dir = os.path.realpath(args.output_dir)
    if not os.path.isdir(in_dir):
        raise ImageSkillError(f"input dir not found: {args.input_dir}")
    if in_dir == out_dir:
        raise ImageSkillError("output dir must differ from input dir")
    if args.tool == "convert" and not args.ext:
        raise ImageSkillError("--ext is required for batch convert (e.g. --ext webp)")

    if args.tool in PAIRED_TOOLS and not args.against:
        raise ImageSkillError("--against DIR is required for batch compare")
    if args.against and args.tool not in PAIRED_TOOLS:
        raise ImageSkillError("--against only applies to batch compare")

    os.makedirs(out_dir, exist_ok=True)

    module = importlib.import_module(TOOL_MODULES[args.tool])
    parser = module.build_parser()
    run_fn = getattr(module, f"run_{args.tool}")
    forwarded = (["--dry-run"] if args.dry_run else []) + ["--timeout", f"{args.timeout:g}"]

    files = sorted(
        f
        for f in glob.glob(os.path.join(in_dir, "*"))
        if os.path.isfile(f) and os.path.splitext(f)[1].lower() in IMAGE_EXTS
    )

    def attempt(entry, argv):
        try:
            entry["result"] = run_tool(run_fn, parser.parse_args(argv))
            entry["ok"] = True
        except ImageSkillError as e:
            entry["ok"] = False
            entry["reason"] = str(e)
            entry.update(timeout_fields(e))
            context = getattr(e, "payload", None) or getattr(e, "extra", None)
            if context:
                entry["result"] = context
        return entry

    results = []
    if args.tool in AGGREGATE_TOOLS:
        dest = os.path.join(out_dir, f"{args.tool}.{args.ext or 'png'}")
        if files:
            results.append(attempt({"files": files, "output": dest}, files + ["-o", dest] + forwarded + tool_args))
    elif args.tool in PAIRED_TOOLS:
        against = os.path.realpath(args.against)
        if not os.path.isdir(against):
            raise ImageSkillError(f"--against dir not found: {args.against}")
        for src in files:
            other = os.path.join(against, os.path.basename(src))
            dest = os.path.join(out_dir, f"{os.path.splitext(os.path.basename(src))[0]}.{args.ext or 'png'}")
            entry = {"file": src, "against": other, "output": dest}
            if not os.path.isfile(other):
                results.append(dict(entry, ok=False, reason=f"no file named {os.path.basename(src)} in {args.against}"))
                continue
            results.append(attempt(entry, [src, other, "-o", dest] + forwarded + tool_args))
    elif args.tool in DIR_TOOLS:
        for src in files:
            dest = os.path.join(out_dir, os.path.splitext(os.path.basename(src))[0])
            results.append(attempt({"file": src, "output": dest}, [src, "-o", dest] + forwarded + tool_args))
    else:
        for src in files:
            base = os.path.splitext(os.path.basename(src))[0]
            dest = os.path.join(out_dir, f"{base}.{args.ext}" if args.ext else os.path.basename(src))
            results.append(attempt({"file": src, "output": dest}, [src, "-o", dest] + forwarded + tool_args))

    all_ok = all(r["ok"] for r in results)
    return {"tool": args.tool, "count": len(results), "all_ok": all_ok, "results": results}


def main(argv=None):
    as_json = wants_json(argv)
    try:
        args = parse_args(argv)
        payload = run_batch(args)
    except ImageSkillError as e:
        fail_error(e, as_json)
        return
    succeed(payload, args.json)


if __name__ == "__main__":
    main()
