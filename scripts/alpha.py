#!/usr/bin/env python3
"""alpha.py - alpha hygiene for stills: report whether an image has an alpha channel and
uses it, convert between straight and premultiplied colour, remove the fringe a cut-out
picked up from its old background, and split an image into the key (matte) and fill
pair that key-and-fill deliveries take.

--mode report       has_alpha / alpha_used, how many pixels are opaque, transparent or
                    partial, and whether every colour is within its alpha (a
                    premultiplied image must be; a straight one usually is not). Writes
                    nothing; no -o.
--mode premultiply  straight -> premultiplied: colour = colour x alpha.
--mode unpremultiply premultiplied -> straight: colour = colour / alpha.
--mode defringe     edge pixels that were blended with --matte (e.g. white) get that
                    colour taken back out: colour = (colour - (1 - alpha) x matte) / alpha.
                    unpremultiply is the same with a black matte.
--mode key          a grey image whose every pixel is the input's alpha.
--mode fill         the colour channels with alpha switched off (straight fill;
                    premultiply first for a premultiplied fill).

Every mode but report needs an input with an alpha channel: an opaque image has no key,
fringe or premultiplication to fix, so it is refused rather than copied. Alpha is never
changed by premultiply, unpremultiply or defringe, and the tool checks that. ImageMagick
only.
"""
import os
import re
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
    fail_error,
    finish_output,
    magick_info,
    prepare_output,
    require_input,
    run,
    run_tool,
    select_backend,
    succeed,
    wants_json,
)

MODES = ("report", "premultiply", "unpremultiply", "defringe", "key", "fill")
# Modes whose output keeps the alpha channel and so needs a format that carries one.
KEEPS_ALPHA = ("premultiply", "unpremultiply", "defringe")
# Colour within alpha by at most this much (0..1) still counts as "within": one 8-bit step.
TOLERANCE = 1 / 255


def build_parser():
    parser = JSONArgumentParser(
        description="Report alpha, convert straight/premultiplied, remove an edge fringe, or write the key or fill of a still")
    parser.add_argument("input", help="image file to read (never modified)")
    add_output_args(parser, output_required=False,
                    output_help="file to write (required unless --mode report); must differ from the input")
    parser.add_argument("--mode", choices=MODES, required=True, help="what to do (see the script's docstring)")
    parser.add_argument("--matte", type=color_arg,
                        help="defringe only: the opaque colour the edges were blended with, e.g. white or #FFFFFF")
    return parser


def _alpha_present(magick, path):
    return magick_info(magick, path, "%A").strip().lower() not in ("false", "undefined", "")


def _matte_rgb(magick, color):
    """An opaque colour as three 0..1 numbers for -fx."""
    out = run([magick, "-size", "1x1", f"xc:{color}", "-format", "%[fx:r] %[fx:g] %[fx:b] %[fx:a]", "info:"])["stdout"]
    r, g, b, a = (float(v) for v in out.split())
    if a < 1:
        raise ImageSkillError(f"--matte {color} is not opaque; the colour the edges were blended with has no alpha")
    return r, g, b


def _alpha_histogram(magick, path):
    """{8-bit alpha level: pixel count} of the first frame, as displayed."""
    out = run([magick, f"{path}[0]", "-auto-orient", "-alpha", "extract", "-depth", "8",
               "-format", "%c", "histogram:info:"])["stdout"]
    levels = {}
    for line in out.splitlines():
        m = re.match(r"\s*(\d+):\s*\(\s*([\d.]+)", line)
        if m:
            level = int(round(float(m.group(2))))
            levels[level] = levels.get(level, 0) + int(m.group(1))
    if not levels:
        raise ImageSkillError(f"could not read the alpha histogram of {path}")
    return levels


def _alpha_max_difference(magick, a, b):
    """Largest per-pixel difference (0..1) between a's alpha and b's alpha-or-grey.
    b is read as its alpha when it has one, else as its grey level (a key image)."""
    b_args = [b, "-alpha", "extract"] if _alpha_present(magick, b) else [b, "-colorspace", "gray"]
    out = run([magick, f"{a}[0]", "-auto-orient", "-alpha", "extract", "(", *b_args, ")",
               "-compose", "difference", "-composite", "-format", "%[fx:maxima]", "info:"])["stdout"]
    return float(out.strip())


def report(magick, path):
    width, height = (int(v) for v in magick_info(magick, path, "%w %h").split())
    payload = {"input": path, "width": width, "height": height, "has_alpha": _alpha_present(magick, path)}
    if not payload["has_alpha"]:
        payload.update(alpha_used=False, pixels={"opaque": width * height, "transparent": 0, "partial": 0},
                       alpha_min=1.0, alpha_max=1.0, color_within_alpha=None)
        return payload
    levels = _alpha_histogram(magick, path)
    opaque, transparent = levels.get(255, 0), levels.get(0, 0)
    partial = sum(levels.values()) - opaque - transparent
    over = float(run([magick, f"{path}[0]", "-auto-orient", "-colorspace", "sRGB", "-alpha", "set", "-fx", "max(max(u.r,u.g),u.b)-u.a",
                      "-alpha", "off", "-format", "%[fx:maxima]", "info:"])["stdout"].strip())
    payload.update(
        alpha_used=opaque != width * height,
        pixels={"opaque": opaque, "transparent": transparent, "partial": partial},
        alpha_min=round(min(levels) / 255, 4),
        alpha_max=round(max(levels) / 255, 4),
        color_within_alpha=over <= TOLERANCE,
    )
    return payload


def write_command(magick, mode, input_path, output_path, matte):
    head = [magick, f"{input_path}[0]", "-auto-orient"]
    if mode in KEEPS_ALPHA:
        # The pixel maths below is on R, G and B: a CMYK(A) input is converted first, or
        # its black channel would be left out (an sRGB input is unchanged by this).
        head += ["-colorspace", "sRGB"]
    if mode == "premultiply":
        ops = ["-alpha", "set", "-channel", "RGB", "-fx", "u*u.a", "+channel"]
    elif mode in ("unpremultiply", "defringe"):
        r, g, b = matte
        expr = f"u.a>0 ? min(1,max(0,(u-(1-u.a)*channel({r:.6f},{g:.6f},{b:.6f},0))/u.a)) : 0"
        ops = ["-alpha", "set", "-channel", "RGB", "-fx", expr, "+channel"]
    elif mode == "key":
        ops = ["-alpha", "extract", "-colorspace", "gray", "-type", "Grayscale"]
    else:  # fill
        ops = ["-alpha", "off"]
    return head + ops + [output_path]


def run_alpha(args):
    require_input(args.input)
    if args.matte is not None and args.mode != "defringe":
        raise ImageSkillError("--matte only applies to --mode defringe")
    if args.mode == "report":
        if args.output:
            raise ImageSkillError("--mode report writes nothing; drop -o/--output")
        if args.dry_run:
            raise ImageSkillError("--mode report writes nothing, so it has no --dry-run")
        _, magick = select_backend("sips cannot read alpha statistics")
        payload = report(magick, args.input)
        payload["backend"] = "magick"
        return payload

    if not args.output:
        raise ImageSkillError(f"--mode {args.mode} writes a file: give -o/--output")
    if args.mode == "defringe" and not args.matte:
        raise ImageSkillError("--mode defringe needs --matte: the colour the edges were blended with (e.g. white)")
    if args.mode == "defringe" and color_is_transparent(args.matte):
        raise ImageSkillError("--matte must be an opaque colour")
    prepare_output([args.input], args.output, args.overwrite)
    if args.mode in KEEPS_ALPHA and ext_of(args.output) not in ALPHA_CAPABLE_EXTS:
        raise ImageSkillError(
            f".{ext_of(args.output)} has no alpha channel, so --mode {args.mode} would lose the alpha it keeps; "
            "write PNG, WebP or TIFF")
    backend, magick = select_backend("sips cannot do alpha operations")
    if not _alpha_present(magick, args.input):
        raise ImageSkillError(
            f"{args.input} has no alpha channel, so there is nothing to {args.mode}; "
            "--mode report says what an image carries")
    matte = None
    if args.mode == "unpremultiply":
        matte = (0.0, 0.0, 0.0)
    elif args.mode == "defringe":
        matte = _matte_rgb(magick, args.matte)
    cmd = write_command(magick, args.mode, args.input, args.output, matte)
    run(cmd, dry_run=args.dry_run)
    if args.dry_run:
        return {"dry_run": True, "would_run": cmd}

    finish_output(args.output, backend)
    in_w, in_h = (int(v) for v in magick_info(magick, args.input, "%w %h").split())
    out_w, out_h = (int(v) for v in magick_info(magick, args.output, "%w %h", auto_orient=False).split())
    if (out_w, out_h) != (in_w, in_h):
        os.remove(args.output)
        raise ImageSkillError(f"{args.mode} produced {out_w}x{out_h}, expected {in_w}x{in_h}")
    out_alpha = _alpha_present(magick, args.output)
    if args.mode in KEEPS_ALPHA and not out_alpha:
        os.remove(args.output)
        raise ImageSkillError(f"{args.output} lost its alpha channel")
    if args.mode in ("key", "fill") and out_alpha:
        os.remove(args.output)
        raise ImageSkillError(f"{args.output} still carries an alpha channel")
    payload = {
        "input": args.input,
        "output": args.output,
        "mode": args.mode,
        "actual": {"width": out_w, "height": out_h},
        "has_alpha": out_alpha,
        "backend": backend,
    }
    if args.mode in KEEPS_ALPHA or args.mode == "key":
        diff = _alpha_max_difference(magick, args.input, args.output)
        if diff > TOLERANCE:
            os.remove(args.output)
            what = "key differs from the input's alpha" if args.mode == "key" else "alpha changed"
            raise ImageSkillError(f"{what} by up to {diff:.4f}; nothing was kept")
        payload["alpha_max_difference"] = round(diff, 6)
    if args.mode == "defringe":
        payload["matte"] = args.matte
    return payload


def main(argv=None):
    as_json = wants_json(argv)
    try:
        args = build_parser().parse_args(argv)
        payload = run_tool(run_alpha, args)
    except ImageSkillError as e:
        fail_error(e, as_json)
        return
    succeed(payload, args.json)


if __name__ == "__main__":
    main()
