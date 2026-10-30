#!/usr/bin/env python3
"""compare.py - measure how different two images are: SSIM, PSNR and the share of
changed pixels, plus an optional difference heatmap (-o). --fail-below turns it into a
check (ok:false when SSIM is under the threshold), for CI and before/after reviews.

Both images are compared as displayed (EXIF orientation applied), first frame only,
flattened onto white (alpha is not compared), and must have the same size.

- diff_ratio / diff_pixels and PSNR are measured by ImageMagick at full resolution,
  with plain pixel arithmetic that is identical on ImageMagick 6 and 7.
- SSIM is computed here in Python - the same on every backend and version (ImageMagick
  6 has no SSIM metric) - on Rec. 601 luma with a 7x7 uniform window, K1=0.01,
  K2=0.03 (scikit-image's defaults), after Wang et al.'s recommended downsampling so
  the shorter side is about 256 pixels (ssim_scale reports the factor).
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (  # noqa: E402
    ImageSkillError,
    JSONArgumentParser,
    add_output_args,
    fail,
    finish_output,
    magick_info,
    prepare_output,
    require_input,
    run,
    run_process,
    select_backend,
    succeed,
    wants_json,
    run_tool,
    fail_error,
)

FLATTEN = ["-auto-orient", "-background", "white", "-alpha", "remove", "-alpha", "off"]
HEAT_CLUT = [
    "(", "-size", "1x86", "gradient:black-blue", "gradient:blue-red", "gradient:red-yellow", "-append", ")",
]


def build_parser():
    parser = JSONArgumentParser(description="Measure the difference between two images (SSIM, PSNR, changed pixels)")
    parser.add_argument("a", help="first image, e.g. the original or the expected result (only read)")
    parser.add_argument("b", help="second image, e.g. the edited or the actual result (only read)")
    add_output_args(
        parser,
        output_required=False,
        output_help="optional: write a difference heatmap here (dimmed first image, changes from blue to yellow)",
    )
    parser.add_argument(
        "--fuzz",
        type=float,
        default=0.0,
        help="percent of full scale a channel may differ by and still count as unchanged in diff_ratio (default 0: exact)",
    )
    parser.add_argument(
        "--fail-below",
        type=float,
        default=None,
        help="report ok:false (exit 1) when SSIM is below this value (0-1), metrics still included",
    )
    return parser


def _gray_bytes(magick, path, width, height, factor):
    cmd = [magick, f"{path}[0]"] + FLATTEN
    if factor > 1:
        cmd += ["-filter", "box", "-resize", f"{max(1, width // factor)}x{max(1, height // factor)}!"]
    cmd += ["-depth", "8", "rgb:-"]
    returncode, rgb, stderr = run_process(cmd, text=False)
    if returncode != 0:
        raise ImageSkillError(f"could not read pixels of {path}: {stderr.decode(errors='replace').strip()}")
    return [(299 * rgb[i] + 587 * rgb[i + 1] + 114 * rgb[i + 2]) / 1000.0 for i in range(0, len(rgb), 3)]


def _integral(values, w, h):
    """(w+1) x (h+1) summed-area table as a flat list."""
    table = [0.0] * ((w + 1) * (h + 1))
    for y in range(h):
        row_sum = 0.0
        base = (y + 1) * (w + 1)
        prev = y * (w + 1)
        off = y * w
        for x in range(w):
            row_sum += values[off + x]
            table[base + x + 1] = table[prev + x + 1] + row_sum
    return table


def ssim(x, y, w, h, win=7, k1=0.01, k2=0.03, data_range=255.0):
    """Mean SSIM over every win x win window fully inside the image (sample covariance)."""
    if w < win or h < win:
        raise ImageSkillError(f"images are too small for SSIM ({w}x{h} after downsampling, need {win}x{win})")
    n = win * win
    cov_norm = n / (n - 1)
    c1 = (k1 * data_range) ** 2
    c2 = (k2 * data_range) ** 2
    sx = _integral(x, w, h)
    sy = _integral(y, w, h)
    sxx = _integral([v * v for v in x], w, h)
    syy = _integral([v * v for v in y], w, h)
    sxy = _integral([a * b for a, b in zip(x, y)], w, h)
    stride = w + 1
    total = 0.0
    count = 0
    for top in range(h - win + 1):
        r0 = top * stride
        r1 = (top + win) * stride
        for left in range(w - win + 1):
            a, b, c, d = r0 + left, r0 + left + win, r1 + left, r1 + left + win
            mx = (sx[d] - sx[b] - sx[c] + sx[a]) / n
            my = (sy[d] - sy[b] - sy[c] + sy[a]) / n
            vx = cov_norm * ((sxx[d] - sxx[b] - sxx[c] + sxx[a]) / n - mx * mx)
            vy = cov_norm * ((syy[d] - syy[b] - syy[c] + syy[a]) / n - my * my)
            vxy = cov_norm * ((sxy[d] - sxy[b] - sxy[c] + sxy[a]) / n - mx * my)
            total += ((2 * mx * my + c1) * (2 * vxy + c2)) / ((mx * mx + my * my + c1) * (vx + vy + c2))
            count += 1
    return total / count


def _fx(magick, args):
    out = run([magick] + args + ["-format", "%[fx:mean]", "info:"])["stdout"].strip()
    return float(out)


def heatmap_command(magick, a, b, output):
    return [
        magick,
        "(", f"{a}[0]", *FLATTEN, "-colorspace", "gray", "-evaluate", "multiply", "0.5", "-colorspace", "sRGB", ")",
        "(", f"{a}[0]", *FLATTEN, f"{b}[0]", *FLATTEN, "-compose", "difference", "-composite",
        "-separate", "-evaluate-sequence", "max", "-auto-level", *HEAT_CLUT, "-clut", ")",
        "-compose", "screen", "-composite", output,
    ]


def run_compare(args):
    require_input(args.a, "a")
    require_input(args.b, "b")
    if args.fail_below is not None and not 0 <= args.fail_below <= 1:
        raise ImageSkillError("--fail-below must be between 0 and 1")
    if args.fuzz < 0 or args.fuzz > 100:
        raise ImageSkillError("--fuzz must be between 0 and 100")
    if args.output:
        prepare_output([args.a, args.b], args.output, args.overwrite)
    backend, magick = select_backend("sips cannot compare images")

    if args.dry_run:
        return {"dry_run": True, "would_run": heatmap_command(magick, args.a, args.b, args.output) if args.output else []}

    wa, ha = (int(v) for v in magick_info(magick, args.a, "%w %h").split())
    wb, hb = (int(v) for v in magick_info(magick, args.b, "%w %h").split())
    if (wa, ha) != (wb, hb):
        raise ImageSkillError(
            f"images differ in size ({wa}x{ha} vs {wb}x{hb}); compare needs the same size - "
            "resize or crop one to match first"
        )

    diff = ["(", f"{args.a}[0]", *FLATTEN, ")", "(", f"{args.b}[0]", *FLATTEN, ")", "-compose", "difference", "-composite"]
    diff_ratio = _fx(magick, diff + ["-separate", "-evaluate-sequence", "max", "-threshold", f"{args.fuzz}%"])
    mse = _fx(magick, diff + ["-evaluate", "pow", "2", "-separate", "-evaluate-sequence", "mean"])
    identical = mse == 0.0
    psnr = None if identical else round(10 * math.log10(1.0 / mse), 4)

    factor = max(1, round(min(wa, ha) / 256))
    sw, sh = (max(1, wa // factor), max(1, ha // factor)) if factor > 1 else (wa, ha)
    ga = _gray_bytes(magick, args.a, wa, ha, factor)
    gb = _gray_bytes(magick, args.b, wa, ha, factor)
    score = 1.0 if identical else round(ssim(ga, gb, sw, sh), 6)

    payload = {
        "a": args.a,
        "b": args.b,
        "width": wa,
        "height": ha,
        "identical": identical,
        "ssim": score,
        "ssim_scale": factor,
        "psnr_db": psnr,
        "diff_ratio": round(diff_ratio, 6),
        "diff_pixels": int(round(diff_ratio * wa * ha)),
        "fuzz": args.fuzz,
        "backend": backend,
    }
    if args.output:
        run(heatmap_command(magick, args.a, args.b, args.output))
        finish_output(args.output, backend)
        payload["output"] = args.output
    if args.fail_below is not None:
        payload["fail_below"] = args.fail_below
        payload["passed"] = score >= args.fail_below
        if not payload["passed"]:
            raise CompareFailed(f"SSIM {score} is below --fail-below {args.fail_below}", payload)
    return payload


class CompareFailed(ImageSkillError):
    def __init__(self, message, payload):
        super().__init__(message)
        self.payload = payload


def main(argv=None):
    as_json = wants_json(argv)
    try:
        args = build_parser().parse_args(argv)
        payload = run_tool(run_compare, args)
    except CompareFailed as e:
        fail(str(e), as_json, **e.payload)
        return
    except ImageSkillError as e:
        fail_error(e, as_json)
        return
    succeed(payload, args.json)


if __name__ == "__main__":
    main()
