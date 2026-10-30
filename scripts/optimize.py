#!/usr/bin/env python3
"""optimize.py - re-encode an image so the file fits a size budget (--max-kb), keeping its
dimensions. For lossy formats (JPEG, WebP, AVIF, HEIC) it binary-searches the highest
quality between --min-quality and --max-quality that fits; PNG is lossless, so it gets
one maximum-compression attempt. When nothing fits it reports ok:false with the smallest
size it reached, and writes nothing - resize first, lower --min-quality, or pick a
lossy format.

Some ImageMagick builds ignore -quality for WebP (Ubuntu 24.04's IM 6.9.12 does); when
the encoder's output does not change between the lowest and highest quality, WebP
falls back to libwebp's own size targeting (-define webp:target-size) and says so in
`method`.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (  # noqa: E402
    ImageSkillError,
    JSONArgumentParser,
    add_output_args,
    ext_of,
    fail,
    finish_output,
    identify_dims,
    oriented_dims,
    prepare_output,
    require_input,
    run,
    select_backend,
    succeed,
    wants_json,
    run_tool,
    fail_error,
)

LOSSY = {"jpg": "jpeg", "jpeg": "jpeg", "webp": "webp", "avif": "avif", "heic": "heic", "heif": "heic"}
LOSSLESS = {"png"}
SIPS_FORMATS = {"jpg": "jpeg", "jpeg": "jpeg", "heic": "heic", "heif": "heic"}


class OptimizeFailed(ImageSkillError):
    def __init__(self, message, extra):
        super().__init__(message)
        self.extra = extra


def build_parser():
    parser = JSONArgumentParser(description="Re-encode an image to fit a file-size budget without changing its dimensions")
    parser.add_argument("input", help="image file to read (never modified)")
    add_output_args(parser, output_help="file to write; its extension picks the format (jpg, webp, avif, heic, png)")
    parser.add_argument("--max-kb", type=float, required=True, help="size budget in kilobytes (1 KB = 1000 bytes)")
    parser.add_argument("--min-quality", type=int, default=40, help="lowest quality the search may use, 1-100 (default 40)")
    parser.add_argument("--max-quality", type=int, default=95, help="highest quality the search may use, 1-100 (default 95)")
    parser.add_argument("--strip", action="store_true", help="also drop metadata (EXIF/GPS/ICC comments) to save bytes; magick only")
    return parser


def _encode_cmd(backend, binary, src, dst, fmt, quality, strip, target_bytes=None):
    if backend == "sips":
        return [binary, "-s", "format", SIPS_FORMATS[ext_of(dst)], "-s", "formatOptions", str(quality), src, "--out", dst]
    cmd = [binary, src, "-auto-orient"]
    if strip:
        cmd.append("-strip")
    if target_bytes is not None:
        cmd += ["-define", f"webp:target-size={int(target_bytes)}"]
    elif fmt == "png":
        cmd += ["-define", "png:compression-level=9", "-define", "png:compression-filter=5"]
    else:
        cmd += ["-quality", str(quality)]
    return cmd + [dst]


def run_optimize(args):
    require_input(args.input)
    prepare_output([args.input], args.output, args.overwrite)
    ext = ext_of(args.output)
    if ext not in LOSSY and ext not in LOSSLESS:
        raise ImageSkillError(f"optimize writes jpg, webp, avif, heic or png - not .{ext or '(no extension)'}")
    if args.max_kb <= 0:
        raise ImageSkillError("--max-kb must be positive")
    if not (1 <= args.min_quality <= args.max_quality <= 100):
        raise ImageSkillError("need 1 <= --min-quality <= --max-quality <= 100")

    sips_ok = True if ext in SIPS_FORMATS and not args.strip else (
        "sips can only re-encode JPEG/HEIC at a quality, and cannot --strip"
    )
    backend, binary = select_backend(sips_ok)
    fmt = "png" if ext in LOSSLESS else LOSSY[ext]
    budget = int(args.max_kb * 1000)

    if args.dry_run:
        return {"dry_run": True, "would_run": _encode_cmd(backend, binary, args.input, args.output, fmt, args.max_quality, args.strip)}

    in_dims = oriented_dims(args.input)
    out_dir = os.path.dirname(os.path.abspath(args.output))
    base = os.path.basename(args.output)
    attempts = []
    temps = {}

    def encode(quality, target_bytes=None):
        key = f"t{target_bytes}" if target_bytes is not None else str(quality)
        tmp = os.path.join(out_dir, f".{base}.optimize-{key}.{ext}")
        run(_encode_cmd(backend, binary, args.input, tmp, fmt, quality, args.strip, target_bytes))
        size = os.path.getsize(tmp)
        temps[key] = tmp
        attempts.append({"quality": quality, "bytes": size} if target_bytes is None
                        else {"target_bytes": target_bytes, "bytes": size})
        return size, key

    chosen = None  # (key, quality, bytes, method)
    try:
        if fmt == "png":
            size, key = encode(None)
            if size <= budget:
                chosen = (key, None, size, "lossless")
            else:
                smallest = size
        else:
            size_hi, key_hi = encode(args.max_quality)
            if size_hi <= budget:
                chosen = (key_hi, args.max_quality, size_hi, "quality-search")
            else:
                size_lo, key_lo = encode(args.min_quality)
                smallest = size_lo
                if size_lo <= budget:
                    lo, hi = args.min_quality, args.max_quality - 1
                    chosen = (key_lo, args.min_quality, size_lo, "quality-search")
                    while lo < hi:
                        mid = (lo + hi + 1) // 2
                        size, key = encode(mid)
                        if size <= budget:
                            chosen = (key, mid, size, "quality-search")
                            lo = mid
                        else:
                            hi = mid - 1
                elif fmt == "webp" and backend == "magick" and size_lo == size_hi:
                    size, key = encode(None, target_bytes=budget)
                    smallest = min(smallest, size)
                    if size <= budget:
                        chosen = (key, None, size, "webp:target-size")

        if chosen is None:
            raise OptimizeFailed(
                f"could not get under {args.max_kb:g} KB: the smallest result was {smallest / 1000:.1f} KB"
                + (" (PNG is lossless) - resize first or write a lossy format (jpg/webp)" if fmt == "png"
                   else f" at quality {args.min_quality} - resize first or lower --min-quality"),
                {"smallest_bytes": smallest, "smallest_kb": round(smallest / 1000, 1), "attempts": attempts},
            )
        key, quality, size, method = chosen
        os.replace(temps.pop(key), args.output)
    finally:
        for tmp in temps.values():
            if os.path.exists(tmp):
                os.remove(tmp)

    finish_output(args.output, backend)
    out_dims = identify_dims(args.output)
    if tuple(out_dims) != tuple(in_dims):
        os.remove(args.output)
        raise ImageSkillError(f"dimensions changed from {in_dims[0]}x{in_dims[1]} to {out_dims[0]}x{out_dims[1]}")

    return {
        "input": args.input,
        "output": args.output,
        "format": fmt.upper(),
        "max_kb": args.max_kb,
        "bytes": size,
        "kb": round(size / 1000, 1),
        "original_bytes": os.path.getsize(args.input),
        "quality": quality,
        "method": method,
        "attempts": attempts,
        "stripped": bool(args.strip),
        "actual": {"width": out_dims[0], "height": out_dims[1]},
        "backend": backend,
    }


def main(argv=None):
    as_json = wants_json(argv)
    try:
        args = build_parser().parse_args(argv)
        payload = run_tool(run_optimize, args)
    except OptimizeFailed as e:
        fail(str(e), as_json, **e.extra)
        return
    except ImageSkillError as e:
        fail_error(e, as_json)
        return
    succeed(payload, args.json)


if __name__ == "__main__":
    main()
