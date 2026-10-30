---
name: imagemagick-skill
description: Local ImageMagick image editing for files that land in a repo - iPhone HEIC/JPEG, screenshots, OG images, README assets. Use when asked to convert, resize, thumbnail, crop, pad, rotate, compress to a file size, make a WebP/OG/social-size image, add a logo or watermark text, adjust brightness/contrast/saturation/sharpness, put images side by side, make a favicon/icon set, strip GPS/EXIF, trim a border, compare two images, check an image's format/dimensions, or show/preview images. Not for video, GIF animation, frame extraction, face recognition, background removal, generative AI, or RAW/ICC color work.
---

# imagemagick-skill

Local, deterministic image editing for a coding agent. No CLI is invented
here - every operation goes through the scripts in `scripts/`, each of which
speaks JSON and never overwrites its input.

## When to use this

- A HEIC/JPEG photo (often from an iPhone) needs converting or resizing
- A screenshot needs a thumbnail or format change
- An OG/social image needs a specific size (e.g. 1200x630) as WebP
- A README image needs a smaller or converted copy
- GPS or personal EXIF data needs to be removed before an image goes public
- You need to confirm an image's actual width/height/format before deciding what to do

## When NOT to use this

- Video, GIF animation, or extracting frames from video - use a
  video/FFmpeg-based skill instead, not this one
- Face recognition, AI background removal, generative/AI image editing
- RAW development, print-grade ICC color management
- PDF conversion (out of scope for v0.1)

## Rules (do not deviate)

1. **Never write a raw `magick`, `convert`, `mogrify`, or `sips` command
   yourself.** Only call the scripts in `scripts/`. `mogrify` is banned
   everywhere in this skill because it overwrites in place.
2. **Never overwrite the input.** Every tool that writes a file requires
   `-o/--output` and refuses to run if it resolves to the same path as the
   input, or if the output already exists (unless `--overwrite` is passed).
3. **Probe first, check last, then look.** Run `probe.py` on the input before
   editing to know what you're actually working with (format, size, alpha, GPS).
   After writing an output, run `check.py` to confirm it opened correctly, matches
   what you promised (size/format), and didn't clobber the input. When the picture
   itself changed (crop, pad, rotate, resize fill, optimize), run `look.py` and open
   the PNG it writes before saying it's done - `check` proves the numbers, `look`
   lets you see the result. Use `look.py --pair before after` or `compare.py` for
   before/after questions.
4. **You don't choose sizes, crops or colours.** Target dimensions, aspect
   ratios, fill colours, file-size budgets and formats come from the user or the
   calling task - this skill executes, it doesn't design. If no size was given
   for a resize/thumbnail, or no colour for padding, ask instead of guessing.
   `preset.py` sizes (og, instagram-*, youtube-thumbnail, ...) are published
   platform sizes: use one only when the user names that platform or preset, and
   still let the user choose `--mode` (fill crops, pad letterboxes). `adjust.py`
   takes explicit values only - never invent "a bit brighter" numbers; ask.
5. **Check the environment before relying on a format.** Run
   `python3 scripts/_contract.py doctor --json` once per session before
   using `convert`/`resize`/`thumb` for HEIC or WebP, or before `strip`/
   `trim` at all (magick-only, see doctor's `tools` and `heic`/`webp` fields).
6. **Every script supports `--json`; every script that writes a file also
   supports `--dry-run`** (`check.py` doesn't write anything, so it has no
   `--dry-run`). Use `--dry-run` to see the exact command that would run
   without executing it. Either run the command for real via the script, or
   don't - don't reconstruct it yourself from the dry-run output.
7. **A malformed invocation still returns `ok:false` JSON with `--json`.**
   Missing or invalid flags are reported the same way as any other failure -
   never assume you have to pre-validate flags yourself before calling a
   script.
8. **Every script takes `--timeout SECONDS` (default 300).** When it runs out,
   ImageMagick and everything it started are killed and the result is
   `ok:false` with `"code": "timeout"` (exit 124). For a huge image or a slow
   delegate, retry with a larger `--timeout` the user agrees to - don't loop.

## Typical flow

```bash
# 1. Know what you have
python3 scripts/probe.py hero.heic --json

# 2. Convert to a web format, resize to an exact OG box, then strip metadata
python3 scripts/convert.py hero.heic -o hero.jpg --json
python3 scripts/resize.py hero.jpg -o hero-og.jpg --width 1200 --height 630 --mode fill --json
python3 scripts/strip.py hero-og.jpg -o hero-og-clean.jpg --json

# 3. Confirm the result
python3 scripts/check.py hero-og-clean.jpg --input hero.heic \
  --expect-width 1200 --expect-height 630 --json
```

`hero.heic` is never touched by any of these steps - every output is a new file.

## Tools

See `python3 scripts/_contract.py contract --json` for the full
machine-readable spec (required/optional args per tool).

| Script | Purpose |
| --- | --- |
| `probe.py` | Width, height, format, colorspace, alpha, GPS presence |
| `convert.py` | Change format (HEIC->JPEG/PNG/WebP, PNG->WebP, ...) |
| `resize.py` | `fit` (default, no distortion), `fill` (cover+crop), `exact` (forced) |
| `thumb.py` | Thumbnail by long edge, aspect preserved, never upscales |
| `crop.py` | Exact rectangle (`--x --y --width --height`) or largest `--aspect W:H` region by `--gravity`; never clips |
| `pad.py` | Margins to an `--aspect` or exact canvas with a required `--color` (`none` = transparent); never shrinks |
| `rotate.py` | Clockwise `--degrees`, `--flip-horizontal/--flip-vertical`, or no flag = bake EXIF orientation |
| `optimize.py` | Fit a file-size budget (`--max-kb`) by searching quality; same dimensions; fails with the smallest size reached |
| `strip.py` | Remove GPS/EXIF, applying orientation first (magick only) |
| `trim.py` | Trim a solid-color border, fails instead of over-trimming (magick only) |
| `check.py` | Verify an output: opens, matches size/format, didn't overwrite input |
| `look.py` | Labelled preview sheet (or `--pair` before/after) to open and look at (magick only) |
| `compare.py` | SSIM / PSNR / changed-pixel share of two same-size images, optional heatmap (`-o`), `--fail-below` gate (magick only) |
| `overlay.py` | Logo (`--image`, `--scale`) or text (`--text`, `--font-size`, `--color`) at a `--position` with `--margin`/`--opacity`; Japanese text gets a CJK font (magick only) |
| `adjust.py` | Explicit `--levels`, `--brightness`, `--contrast`, `--saturation`, `--blur`, `--sharpen`; no "auto" (magick only) |
| `montage.py` | Row or `--cols` grid with a required `--background`, `--gap`, `--labels` - e.g. README comparisons (magick only) |
| `icons.py` | favicon.ico (16/32/48) + PNG icons (32/192/512) + apple-touch-icon.png and the HTML/manifest entries, from one square image (magick only) |
| `preset.py` | Named published sizes with their source (`--list`), `--mode fill\|fit\|pad` |
| `batch.py` | Run a tool over every image in a folder (`look`/`montage` make one sheet; `icons` one folder per image; `compare` pairs with `--against DIR`) |
| `_contract.py` | `contract` (tool spec) / `doctor` (environment check) |

The same tools are available over MCP (`mcp/server.py`, generated from the contract) for
clients that don't load skills.

Backend: ImageMagick first - `magick` (IM7), or IM6's `convert`/`identify` when there is
no `magick` (Ubuntu/Debian apt; you still only call the scripts); macOS `sips` covers a reduced subset when
`magick` isn't installed (`convert`, `resize` fit, `thumb`, centred `crop --aspect`,
centred `pad` with a `#RRGGBB` colour, a single 90-degree `rotate` or flip, JPEG/HEIC
`optimize`, `preset` fill/fit). `strip`, `trim`, `look`, `compare`, `overlay`,
`adjust`, `montage` and `icons` always require `magick` - doctor's
`tools` field says what this machine can run. No cloud calls, no API keys, no pip dependencies -
Python 3.9 standard library plus whichever binary is already on the machine.
