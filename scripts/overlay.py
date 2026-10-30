#!/usr/bin/env python3
"""overlay.py - put a logo/watermark image (--image) or a line of text (--text) on top of
an image, at a --position with a --margin and an --opacity. The base image keeps its
size; an overlay larger than the base is refused rather than cropped.

Text is rendered literally (ImageMagick's %-escapes, backslashes and "@file" reading are
escaped). Its font is --font, or the font doctor reports - a CJK-capable one when the
text contains Japanese, Chinese or Korean; with no suitable font the tool fails instead
of drawing empty boxes. Size and colour of text are required: how it should look is the
caller's call. ImageMagick only.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (  # noqa: E402
    GRAVITIES,
    ImageSkillError,
    JSONArgumentParser,
    add_output_args,
    color_arg,
    escape_magick_text,
    finish_output,
    identify_dims,
    magick_info,
    non_negative_int,
    oriented_dims,
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


def build_parser():
    parser = JSONArgumentParser(description="Overlay a logo image or a line of text onto an image")
    parser.add_argument("input", help="base image to read (never modified)")
    add_output_args(parser)
    what = parser.add_mutually_exclusive_group(required=True)
    what.add_argument("--image", help="overlay image, e.g. a logo PNG with transparency")
    what.add_argument("--text", help="overlay text (rendered literally, one line)")
    parser.add_argument("--position", choices=GRAVITIES, required=True, help="where the overlay sits")
    parser.add_argument("--margin", type=non_negative_int, default=0, help="distance from the edge(s) in pixels (default 0)")
    parser.add_argument("--opacity", type=float, default=1.0, help="0-1 (default 1 = opaque)")
    parser.add_argument("--scale", type=float, help="--image only: overlay width as a fraction of the base width, e.g. 0.2")
    parser.add_argument("--font-size", type=float, help="--text only (required): point size")
    parser.add_argument("--color", type=color_arg, help="--text only (required): text colour")
    parser.add_argument("--font", help="--text only: font file to use instead of the one doctor reports")
    return parser


def _offset(position, margin):
    """-geometry offset for a gravity: inward from the edges the gravity names."""
    x = margin if position.endswith("west") or position.endswith("east") else 0
    y = margin if position.startswith("north") or position.startswith("south") else 0
    return f"+{x}+{y}"


def _fade(opacity):
    return [] if opacity >= 1 else ["-alpha", "set", "-channel", "A", "-evaluate", "multiply", f"{opacity:g}", "+channel"]


def run_overlay(args):
    require_input(args.input)
    inputs = [args.input] + ([args.image] if args.image else [])
    if args.image:
        require_input(args.image, "--image")
    prepare_output(inputs, args.output, args.overwrite)
    if not 0 < args.opacity <= 1:
        raise ImageSkillError("--opacity must be greater than 0 and at most 1")
    if args.text is not None:
        if args.scale is not None:
            raise ImageSkillError("--scale applies to --image, not --text (use --font-size)")
        if args.font_size is None or args.color is None:
            raise ImageSkillError("--text needs --font-size and --color")
        if args.font_size <= 0:
            raise ImageSkillError("--font-size must be positive")
        if not args.text.strip():
            raise ImageSkillError("--text is empty")
    else:
        if args.font_size is not None or args.color is not None or args.font is not None:
            raise ImageSkillError("--font-size/--color/--font apply to --text only")
        if args.scale is not None and not 0 < args.scale <= 1:
            raise ImageSkillError("--scale must be greater than 0 and at most 1")
    backend, magick = select_backend("sips cannot composite images or render text")

    base_w, base_h = oriented_dims(args.input)
    font = None
    if args.text is not None:
        font = resolve_font(args.text, args.font)
        layer = ["-background", "none", "-font", font, "-pointsize", f"{args.font_size:g}", "-fill", args.color,
                 f"label:{escape_magick_text(args.text)}"]
        ow, oh = (int(v) for v in run([magick] + layer + ["-format", "%w %h", "info:"])["stdout"].split())
    else:
        ow, oh = (int(v) for v in magick_info(magick, args.image, "%w %h").split())
        layer = [f"{args.image}[0]", "-auto-orient"]
        if args.scale is not None:
            target_w = max(1, round(base_w * args.scale))
            oh = max(1, round(oh * target_w / ow))
            ow = target_w
            layer += ["-resize", f"{ow}x{oh}!"]
    if ow > base_w or oh > base_h:
        raise ImageSkillError(
            f"the overlay ({ow}x{oh}) is larger than the image ({base_w}x{base_h}); "
            + ("use --scale" if args.image else "use a smaller --font-size")
        )

    cmd = [magick, args.input, "-auto-orient", "("] + layer + _fade(args.opacity) + [")",
           "-gravity", args.position, "-geometry", _offset(args.position, args.margin),
           "-compose", "over", "-composite", args.output]
    run(cmd, dry_run=args.dry_run)
    if args.dry_run:
        return {"dry_run": True, "would_run": cmd}

    finish_output(args.output, backend)
    out_w, out_h = identify_dims(args.output)
    if (out_w, out_h) != (base_w, base_h):
        raise ImageSkillError(f"overlay changed the size from {base_w}x{base_h} to {out_w}x{out_h}")
    return {
        "input": args.input,
        "output": args.output,
        "kind": "text" if args.text is not None else "image",
        "position": args.position,
        "margin": args.margin,
        "opacity": args.opacity,
        "overlay": {"width": ow, "height": oh},
        "font": font,
        "actual": {"width": out_w, "height": out_h},
        "backend": backend,
    }


def main(argv=None):
    as_json = wants_json(argv)
    try:
        args = build_parser().parse_args(argv)
        payload = run_tool(run_overlay, args)
    except ImageSkillError as e:
        fail_error(e, as_json)
        return
    succeed(payload, args.json)


if __name__ == "__main__":
    main()
