#!/usr/bin/env python3
"""preset.py - resize to a named, published size (e.g. og = 1200x630) by calling
resize.py (fill / fit) or resize.py + pad.py (pad). The sizes live in presets.json,
each with the platform documentation it comes from; `--list` prints them.

Use it only when the user names a preset or a platform's documented size - the skill
never picks a size on its own (SKILL.md rule 4). --mode is required: whether to crop
(fill), letterbox (pad, with --color) or just fit inside is the caller's decision.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pad  # noqa: E402
import resize  # noqa: E402
from _common import (  # noqa: E402
    ImageSkillError,
    JSONArgumentParser,
    add_output_args,
    color_arg,
    ext_of,
    oriented_dims,
    prepare_output,
    require_input,
    select_backend,
    succeed,
    wants_json,
    run_tool,
    fail_error,
)


def load_presets():
    with open(os.path.join(HERE, "presets.json"), encoding="utf-8") as f:
        data = json.load(f)
    return {name: spec for name, spec in data.items() if not name.startswith("_")}


def build_parser():
    parser = JSONArgumentParser(description="Resize to a named published size (Open Graph, Instagram, YouTube, ...)")
    parser.add_argument("input", nargs="?", help="image file to read (never modified); not needed with --list")
    add_output_args(parser, output_required=False,
                    output_help="file to write (required unless --list); must differ from the input")
    parser.add_argument("--preset", choices=sorted(load_presets()), help="named size from presets.json")
    parser.add_argument("--mode", choices=["fill", "fit", "pad"],
                        help="fill: cover and centre-crop to the exact size; fit: inside the size, no crop (may be "
                             "smaller); pad: fit inside, then pad to the exact size with --color")
    parser.add_argument("--color", type=color_arg, help="pad mode only: fill colour (none = transparent)")
    parser.add_argument("--list", action="store_true", help="print every preset with its size and source, write nothing")
    return parser


def run_preset(args):
    presets = load_presets()
    if args.list:
        return {"presets": presets}
    missing = [flag for flag, value in (("input", args.input), ("-o/--output", args.output),
                                        ("--preset", args.preset), ("--mode", args.mode)) if not value]
    if missing:
        raise ImageSkillError(f"missing {', '.join(missing)} (or pass --list)")
    if args.mode == "pad" and not args.color:
        raise ImageSkillError("--mode pad needs --color (none for transparent)")
    if args.mode != "pad" and args.color:
        raise ImageSkillError("--color only applies to --mode pad")
    require_input(args.input)
    prepare_output([args.input], args.output, args.overwrite)
    spec = presets[args.preset]
    width, height = spec["width"], spec["height"]

    common = ["--json"] + (["--overwrite"] if args.overwrite else []) + (["--dry-run"] if args.dry_run else [])
    if args.mode in ("fill", "fit"):
        steps = [resize.run_resize(resize.build_parser().parse_args(
            [args.input, "-o", args.output, "--width", str(width), "--height", str(height), "--mode", args.mode] + common))]
    elif args.dry_run:
        # Nothing may be written, so the pad step is planned against the size the fit step
        # would produce (the same proportional arithmetic resize.py uses for sips).
        first = resize.run_resize(resize.build_parser().parse_args(
            [args.input, "-o", args.output, "--width", str(width), "--height", str(height), "--mode", "fit"] + common))
        backend, binary = select_backend(True if re.fullmatch(r"#[0-9a-fA-F]{6}", args.color) else "sips pads only with #RRGGBB")
        in_w, in_h = oriented_dims(args.input)
        fit = resize._sips_fit_dims(in_w, in_h, width, height)
        pad_cmd, _ = pad.pad_command(backend, binary, args.output, args.output, fit, (width, height), args.color, "center")
        return {"dry_run": True, "would_run": [first["would_run"], pad_cmd]}
    else:
        out_dir = os.path.dirname(os.path.abspath(args.output))
        tmp = os.path.join(out_dir, f".{os.path.basename(args.output)}.preset-fit.{ext_of(args.output) or 'png'}")
        try:
            first = resize.run_resize(resize.build_parser().parse_args(
                [args.input, "-o", tmp, "--width", str(width), "--height", str(height), "--mode", "fit",
                 "--overwrite", "--json"]))
            second = pad.run_pad(pad.build_parser().parse_args(
                [tmp, "-o", args.output, "--width", str(width), "--height", str(height), "--color", args.color] + common))
            steps = [first, second]
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    if args.dry_run:
        return {"dry_run": True, "would_run": steps[0]["would_run"]}
    last = steps[-1]
    return {
        "input": args.input,
        "output": args.output,
        "preset": args.preset,
        "description": spec["description"],
        "source": spec["source"],
        "mode": args.mode,
        "requested": {"width": width, "height": height},
        "actual": last["actual"],
        "via": ["resize"] if len(steps) == 1 else ["resize", "pad"],
        "backend": last["backend"],
    }


def main(argv=None):
    as_json = wants_json(argv)
    try:
        args = build_parser().parse_args(argv)
        payload = run_tool(run_preset, args)
    except ImageSkillError as e:
        fail_error(e, as_json)
        return
    if not args.json and args.list:
        for name, spec in payload["presets"].items():
            print(f"{name:26} {spec['width']}x{spec['height']:<6} {spec['description']}  <{spec['source']}>")
        return
    succeed(payload, args.json)


if __name__ == "__main__":
    main()
